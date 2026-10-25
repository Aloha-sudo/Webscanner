import os
import json
import sqlite3
import sys
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.reports.httpx_results import normalize_result
from app.core.web_discovery import extract_urls, target_hostname
from app.core.exclusions import allowed_targets, excluded_ports
from app.core.text import database_text, error_text
from app.core.process import ScanCancelled, execute
from app.core.ports import top_tcp_ports
from app.core.celery_app import celery_app
from app.core import dns_jobs  # Register the standalone DNS task on every worker startup.
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.scan import Scan, ScanStatus, Host, Port, Service, Screenshot


def expand_ports(ports_str: str) -> str:
    """
    Разворачивает диапазоны в список через запятую:
      "22-25,80,443" → "22,23,24,25,80,443"
    """
    if not ports_str:
        return ports_str
    parts = []
    for chunk in ports_str.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            try:
                a, b = chunk.split("-", 1)
                a, b = int(a), int(b)
                if a > b:
                    a, b = b, a
                parts.extend(str(p) for p in range(a, b + 1))
            except ValueError:
                parts.append(chunk)  # как есть
        else:
            parts.append(chunk)
    return ",".join(parts)


def resolve_ports(scan_type: str, custom_ports: str = None):
    """
    Резолвит профиль портов.
    Возвращает (ports_nmap, ports_rustscan, extra_nmap_args):
      - ports_nmap:     список/диапазон для `nmap -p` (range допустим)
      - ports_rustscan: раскрытый список для `rustscan -p` (без диапазонов),
                        либо None — тогда rustscan запускается с `-r`
      - extra_nmap_args: доп. флаги для nmap (для top1000)
    """
    profiles = settings.PORT_PROFILES

    if scan_type == "custom":
        if not custom_ports:
            raise ValueError("custom_ports required for custom scan")
        import re as _re
        if not _re.match(r'^[\d,\-]+$', custom_ports):
            raise ValueError(f"Invalid ports format: {custom_ports}")
        # rustscan не понимает диапазоны в -p → раскрываем
        if ',' not in custom_ports and '-' in custom_ports:
            return custom_ports, None, []
        return custom_ports, expand_ports(custom_ports), []

    if scan_type in ("top100", "top1000"):
        # Use the same frequency-based TCP list for both scanners.
        ports = top_tcp_ports(count=100 if scan_type == "top100" else 1000)
        return ports, ports, []

    if scan_type == "full":
        # nmap: -p 1-65535; rustscan: -r 1-65535
        return "1-65535", None, []

    if scan_type in profiles and profiles[scan_type]:
        # quick / web — списки через запятую, работают и в rustscan -p
        return profiles[scan_type], profiles[scan_type], []

    raise ValueError(f"Unknown scan_type: {scan_type}")


SPEED_PROFILES = {
    # normal — увеличенное ожидание для сетей с задержками
    "normal": {
        "label": "Normal",
        "rustscan": {"batch": "1000", "timeout": "5000", "tries": "2", "ulimit": "5000"},
        "nmap": {
            "version": "-sV --version-intensity 2",
            "timing": "-T4",
            "host_timeout": "90s",
            "extra": [],
        },
    },
    # fast — повышенная параллельность
    "fast": {
        "label": "Fast",
        "rustscan": {"batch": "2000", "timeout": "3000", "tries": "1", "ulimit": "5000"},
        "nmap": {
            "version": "-sV --version-intensity 1",
            "timing": "-T4",
            "host_timeout": "60s",
            "extra": ["--min-parallelism", "20", "--max-retries", "1"],
        },
    },
    # hard — высокая параллельность; точность зависит от сети
    "hard": {
        "label": "Hard",
        "rustscan": {"batch": "2500", "timeout": "2000", "tries": "2", "ulimit": "10000"},
        "nmap": {
            "version": "-sV --version-intensity 1",
            "timing": "-T4",
            "host_timeout": "45s",
            "extra": ["--min-parallelism", "40", "--max-retries", "1", "--min-rate", "200"],
        },
    },
}


def resolve_speed(speed: str) -> dict:
    """Возвращает параметры rustscan + nmap для заданной скорости."""
    if speed not in SPEED_PROFILES:
        print(f"[speed] неизвестная скорость '{speed}', fallback на normal")
        speed = "normal"
    cfg = SPEED_PROFILES[speed]
    r = cfg["rustscan"]
    n = cfg["nmap"]
    print(
        f"[speed] режим={speed} | "
        f"rustscan: -b {r['batch']} -t {r['timeout']} --tries {r['tries']} --ulimit {r['ulimit']} | "
        f"nmap: {n['version']} {n['timing']} --host-timeout {n['host_timeout']}"
    )
    return cfg


def update_scan(db: Session, scan_id: int, **kwargs):
    kwargs = {key: database_text(value) for key, value in kwargs.items()}
    # Conditional SQL keeps cancellation from being overwritten by a stale worker.
    query = db.query(Scan).filter(Scan.id == scan_id)
    if kwargs.get('status') != ScanStatus.CANCELLED:
        query = query.filter(Scan.status != ScanStatus.CANCELLED)
    updated = query.update(kwargs, synchronize_session=False)
    db.commit()
    db.expire_all()
    scan = db.get(Scan, scan_id)
    if not updated and (scan is None or scan.status == ScanStatus.CANCELLED):
        raise ScanCancelled()
    return scan


def get_scan(db: Session, scan_id: int):
    return db.query(Scan).filter(Scan.id == scan_id).first()


def ensure_active(scan_id):
    if scan_id is None:
        return
    with SessionLocal() as session:
        scan = session.get(Scan, scan_id)
        if scan is None or scan.status == ScanStatus.CANCELLED:
            raise ScanCancelled()


def run_command(cmd: list, timeout: int = 600, scan_id=None) -> tuple:
    print(f"[cmd] {' '.join(cmd)}")
    return execute(cmd, timeout=timeout, check_cancelled=lambda: ensure_active(scan_id))


# ============================================================
#  ПАРСЕРЫ
# ============================================================

def parse_rustscan_greppable(path: str) -> dict:
    """
    Парсим вывод rustscan (greppable).
    Формат: ip -> [port1,port2,...]
    Возвращает: {ip: [ports]}
    """
    result = {}
    if not os.path.exists(path):
        return result

    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or "->" not in line:
                    continue
                try:
                    ip, ports_str = line.split("->", 1)
                    ip = ip.strip()
                    ports_str = ports_str.strip().strip("[]")
                    ports = [int(p.strip()) for p in ports_str.split(",") if p.strip()]
                    if ports:
                        result[ip] = ports
                except Exception:
                    continue
    except Exception as e:
        print(f"[rustscan parse error] {e}")

    return result


def parse_nmap(path: str) -> list:
    """Парсим nmap XML, возвращаем список хостов с портами."""
    import xml.etree.ElementTree as ET

    hosts = []
    if not os.path.exists(path):
        raise RuntimeError('Nmap did not produce an XML report')

    try:
        tree = ET.parse(path)
        root = tree.getroot()

        for host_elem in root.findall("host"):
            status = host_elem.find("status")
            if status is None or status.get("state") != "up":
                continue

            ip = None
            for addr in host_elem.findall("address"):
                if addr.get("addrtype") in ("ipv4", "ipv6"):
                    ip = addr.get("addr")

            hostname = None
            hostnames = host_elem.find("hostnames")
            if hostnames is not None:
                hn = hostnames.find("hostname")
                if hn is not None:
                    hostname = hn.get("name")

            os_match = None
            os_elem = host_elem.find("os")
            if os_elem is not None:
                osmatch = os_elem.find("osmatch")
                if osmatch is not None:
                    os_match = osmatch.get("name")

            ports = []
            ports_elem = host_elem.find("ports")
            if ports_elem is not None:
                for port_elem in ports_elem.findall("port"):
                    state = port_elem.find("state")
                    if state is None or state.get("state") != "open":
                        continue

                    port_data = {
                        "port": int(port_elem.get("portid")),
                        "protocol": port_elem.get("protocol", "tcp"),
                        "state": "open",
                    }

                    service = port_elem.find("service")
                    if service is not None:
                        port_data["service"] = service.get("name")
                        product = service.get("product", "")
                        version = service.get("version", "")
                        port_data["version"] = f"{product} {version}".strip() or None

                    ports.append(port_data)

            if ip and ports:
                hosts.append({
                    "ip": ip,
                    "hostname": hostname,
                    "os": os_match,
                    "ports": ports,
                })
    except Exception as e:
        raise RuntimeError(f"Nmap XML parse error: {e}") from e

    return hosts


def extract_urls_from_nmap(path: str, target=None) -> list:
    return extract_urls(path, {int(p) for p in settings.PORT_PROFILES['web'].split(',')}, target=target)



def parse_httpx(db: Session, scan_id: int, path: str):
    if not os.path.exists(path):
        return 0

    matched_ports = set()
    scan = db.get(Scan, scan_id)
    hostname = target_hostname(scan.target) if scan else None
    target_addresses = {hostname: [h.ip for h in db.query(Host).filter(Host.scan_id == scan_id).all()]} if hostname else {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                normalized = normalize_result(data, target_addresses)
                if normalized is None:
                    continue
                url = normalized['url']
                host_ip = normalized['ip']
                port_num = normalized['port']

                host = db.query(Host).filter(
                    Host.scan_id == scan_id,
                    Host.ip == host_ip,
                ).first()
                if not host:
                    continue

                port = db.query(Port).filter(
                    Port.host_id == host.id,
                    Port.port == port_num,
                ).first()
                if not port:
                    continue

                service = db.query(Service).filter(Service.port_id == port.id).first()
                if not service:
                    service = Service(port_id=port.id)
                    db.add(service)

                service.url = url
                service.status_code = normalized["status_code"]
                service.title = normalized["title"]
                tech = normalized["technologies"]
                service.technologies = json.dumps(tech) if tech else None
                service.ssl = url.startswith("https://")

                matched_ports.add(port.id)

        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"HTTPX report parse failed: {e}") from e

    return len(matched_ports)


def save_screenshots_local(db: Session, scan_id: int, screenshots_dir: str):
    if not os.path.exists(screenshots_dir):
        return 0

    metadata = {}
    database_path = os.path.join(os.path.dirname(screenshots_dir), 'gowitness.sqlite3')
    if os.path.exists(database_path):
        with sqlite3.connect('file:' + database_path + '?mode=ro', uri=True) as conn:
            for url, title, status_code, filename in conn.execute('SELECT url,title,response_code,filename FROM results'):
                if filename:
                    metadata[os.path.basename(filename)] = (url, title, status_code)
    count = 0
    try:
        for filename in os.listdir(screenshots_dir):
            if not (filename.endswith(".png") or filename.endswith(".jpeg") or filename.endswith(".jpg")):
                continue

            base = filename
            for ext in (".png", ".jpeg", ".jpg"):
                if base.endswith(ext):
                    base = base[:-len(ext)]
                    break

            url, title, status_code = metadata.get(filename, (base, None, None))
            screenshot = Screenshot(
                scan_id=scan_id,
                url=url, title=title, status_code=status_code,
                minio_path=f"local://scan_{scan_id}/{filename}",
            )
            db.add(screenshot)
            count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Screenshot save failed: {e}") from e

    return count


# ============================================================
#  ОСНОВНАЯ ЗАДАЧА
# ============================================================

@celery_app.task(bind=True, name="run_scan")
def run_scan(self, scan_id: int, scan_type: str = "quick", custom_ports: str = None, speed: str = "normal", exclusions: dict = None, dns_requested: bool = False):
    """
    Пайплайн: rustscan -> nmap -> httpx -> gowitness.
    rustscan быстро находит порты, nmap делает глубокий анализ.
    """
    db = SessionLocal()
    try:
        scan = get_scan(db, scan_id)
        if not scan:
            return {"error": "Scan not found"}

        if scan.status == ScanStatus.CANCELLED:
            return {"status": "cancelled"}

        update_scan(
            db, scan_id,
            status=ScanStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            observed_at=datetime.now(timezone.utc),
            stage="starting",
            progress=0,
        )

        scan_dir = os.path.join(settings.SCANS_DIR, str(scan_id))
        os.makedirs(scan_dir, exist_ok=True)
        target = scan.target
        allowed_ips = None
        blocked_ports = excluded_ports(scan.exclude_ports)
        if scan.exclude_ips or scan.exclude_hosts:
            allowed_ips = set(allowed_targets(target, scan.exclude_ips, scan.exclude_hosts))
            target_file = os.path.join(scan_dir, 'allowed_targets.txt')
            with open(target_file,'w') as f:
                f.write('\n'.join(sorted(allowed_ips)))
            target = target_file

        # === ЭТАП 1: rustscan ===
        print(f"[{scan_id}] ЭТАП 1: rustscan")
        update_scan(db, scan_id, stage="rustscan", progress=10)

        rustscan_output = os.path.join(scan_dir, "rustscan.txt")

        # Резолвим порты по профилю:
        #   ports_nmap     — для `nmap -p` (range допустим)
        #   ports_rustscan — для `rustscan -p` (раскрытый список, без диапазонов)
        #   extra_nmap_args — доп. флаги для nmap
        try:
            ports_nmap, ports_rustscan, extra_nmap_args = resolve_ports(scan_type, custom_ports)
        except ValueError as e:
            print(f"[{scan_id}] ERROR resolve_ports: {e}")
            update_scan(
                db, scan_id,
                status=ScanStatus.FAILED,
                error_message=error_text(e),
                finished_at=datetime.utcnow(),
            )
            return {"error": str(e)}

        print(
            f"[{scan_id}] профиль={scan_type}, "
            f"nmap_ports={str(ports_nmap)[:60]}, "
            f"rustscan_ports={str(ports_rustscan)[:60] if ports_rustscan else None}"
        )

        selected = {int(p) for p in expand_ports(ports_nmap or ports_rustscan).split(',')}
        if not selected - blocked_ports:
            raise ValueError('Все порты выбранного профиля исключены: скан не запущен')
        speed_cfg = resolve_speed(speed)
        rcfg = speed_cfg["rustscan"]
        ncfg = speed_cfg["nmap"]

        rustscan_common = [
            "-b", rcfg["batch"],
            "-t", rcfg["timeout"],
            "--tries", rcfg["tries"],
            "--ulimit", rcfg["ulimit"],
            "--scripts", "none", "--no-banner", "-g", "--accessible",
        ]

        if ports_rustscan is None:
            # full or a single custom range: use -r without expanding argv.
            rustscan_cmd = ["rustscan", "-a", target, "-r", ports_nmap] + rustscan_common
        elif ports_rustscan:
            # quick/web/custom/top1000 — через -p (список)
            rustscan_cmd = ["rustscan", "-a", target, "-p", ports_rustscan] + rustscan_common
        else:
            rustscan_cmd = ["rustscan", "-a", target, "-r", "1-1000"] + rustscan_common

        if blocked_ports:
            rustscan_cmd += ['--exclude-ports', ','.join(str(p) for p in sorted(blocked_ports))]
        stdout, stderr, rc = run_command(rustscan_cmd, timeout=settings.RUSTSCAN_TIMEOUT, scan_id=scan_id)

        with open(rustscan_output, "w") as f:
            f.write(stdout)

        if rc != 0:
            print(f"[{scan_id}] rustscan rc={rc}, stderr: {stderr[:500]}")

        rustscan_hosts = parse_rustscan_greppable(rustscan_output)
        rustscan_hosts = {ip: [p for p in ports if p not in blocked_ports] for ip, ports in rustscan_hosts.items() if allowed_ips is None or ip in allowed_ips}
        rustscan_hosts = {ip: ports for ip, ports in rustscan_hosts.items() if ports}
        total_ports_found = sum(len(ports) for ports in rustscan_hosts.values())
        print(f"[{scan_id}] rustscan: {len(rustscan_hosts)} хостов, {total_ports_found} портов")

        if not rustscan_hosts:
            print(f"[{scan_id}] rustscan не нашёл хостов. stderr: {stderr[:500]}")
            update_scan(
                db, scan_id,
                status=ScanStatus.COMPLETED,
                stage="completed",
                progress=100,
                finished_at=datetime.utcnow(),
                error_message=None,
            )
            return {"status": "completed", "hosts": 0, "ports": 0}

        # Собираем все уникальные порты для nmap
        all_ports = set()
        for ports in rustscan_hosts.values():
            all_ports.update(ports)

        if not all_ports:
            print(f"[{scan_id}] rustscan: портов не найдено, пропускаем nmap")
            update_scan(
                db, scan_id,
                status=ScanStatus.COMPLETED,
                stage="completed",
                progress=100,
                finished_at=datetime.utcnow(),
            )
            return {"status": "completed", "hosts": 0, "ports": 0}

        ports_str = ",".join(str(p) for p in sorted(all_ports))
        print(f"[{scan_id}] rustscan нашёл порты: {ports_str[:200]}")

        # === ЭТАП 2a: nmap — ВЕРИФИКАЦИЯ кандидатов (отсеиваем фейки) ===
        print(f"[{scan_id}] ЭТАП 2a: nmap верификация")
        update_scan(db, scan_id, stage="verifying", progress=35)

        nmap_verify_output = os.path.join(scan_dir, "nmap_verify.xml")

        # Список кандидатов от rustscan
        candidates_file = os.path.join(scan_dir, "candidates.txt")
        with open(candidates_file, "w") as f:
            f.write("\n".join(rustscan_hosts.keys()))

        print(f"[{scan_id}] верифицируем {len(rustscan_hosts)} кандидатов")

        # nmap -sS --open --defeat-rst-ratelimit — быстро отсеивает фейки
        # (в твоём скрипте test_scan_v9.py именно это работает)
        run_command([
            "nmap",
            "-sS",
            "-T4",
            "-n",
            "-Pn",
            "--open",
            "--reason",
            "--defeat-rst-ratelimit",
            "-iL", candidates_file,
            "-p", ports_str,
            "-oX", nmap_verify_output,
        ], timeout=settings.NMAP_TIMEOUT, scan_id=scan_id)

        # Парсим — только те хосты, где реально есть открытые порты
        verified_hosts = parse_nmap(nmap_verify_output)
        verified_ips = [h["ip"] for h in verified_hosts]

        print(f"[{scan_id}] верификация: {len(verified_ips)} реальных хостов из {len(rustscan_hosts)}")

        if not verified_ips:
            print(f"[{scan_id}] после верификации не осталось живых хостов")
            update_scan(
                db, scan_id,
                status=ScanStatus.COMPLETED,
                stage="completed",
                progress=100,
                finished_at=datetime.utcnow(),
                error_message=None,
            )
            return {"status": "completed", "hosts": 0, "ports": 0}

        # === ЭТАП 2b: nmap — детальный скан только живых хостов ===
        print(f"[{scan_id}] ЭТАП 2b: nmap детально по {len(verified_ips)} хостам")
        update_scan(db, scan_id, stage="nmap", progress=50)

        nmap_output = os.path.join(scan_dir, "nmap.xml")
        verified_file = os.path.join(scan_dir, "verified_ips.txt")
        with open(verified_file, "w") as f:
            f.write("\n".join(verified_ips))

        nmap_version_args = ncfg["version"].split()
        nmap_extra = ncfg.get("extra", [])
        nmap_cmd = [
            "nmap",
            *nmap_version_args,
            ncfg["timing"],
            "-Pn",
            "-n",
            "--open",
            "--host-timeout", ncfg["host_timeout"],
            *nmap_extra,
            "-iL", verified_file,
            "-p", ports_str,
            "-oX", nmap_output,
        ]
        run_command(nmap_cmd, timeout=settings.NMAP_TIMEOUT, scan_id=scan_id)

        # Парсим детальный nmap
        update_scan(db, scan_id, stage="parsing_nmap", progress=60)
        hosts_data = parse_nmap(nmap_output)
        print(f"[{scan_id}] nmap: {len(hosts_data)} хостов")

        total_hosts = 0
        total_ports = 0

        for host_data in hosts_data:
            host = Host(
                scan_id=scan_id,
                ip=host_data["ip"],
                hostname=host_data.get("hostname"),
                os=host_data.get("os"),
            )
            db.add(host)
            db.flush()
            total_hosts += 1

            for port_data in host_data["ports"]:
                port = Port(
                    host_id=host.id,
                    port=port_data["port"],
                    protocol=port_data.get("protocol", "tcp"),
                    state=port_data.get("state", "open"),
                    service=port_data.get("service"),
                    version=port_data.get("version"),
                )
                db.add(port)
                total_ports += 1

        db.commit()
        update_scan(db, scan_id, total_hosts=total_hosts, total_ports=total_ports)
        print(f"[{scan_id}] nmap: {total_hosts} хостов, {total_ports} портов")

        if scan.dns_options and scan.dns_options.get('enabled'):
            from app.core.dns_jobs import new_dns_job, run_dns_job
            scan = update_scan(db, scan_id, stage='dns', progress=65)
            token = new_dns_job(scan, scan.dns_options)
            db.commit()
            run_dns_job(scan_id, token, check_cancelled=lambda: ensure_active(scan_id))
            db.expire_all()

        # === ЭТАП 3: httpx ===
        print(f"[{scan_id}] ЭТАП 3: httpx")
        update_scan(db, scan_id, stage="httpx", progress=75)

        urls = extract_urls_from_nmap(nmap_output, target=scan.target)
        total_web = 0

        if urls:
            urls_file = os.path.join(scan_dir, "urls.txt")
            with open(urls_file, "w") as f:
                f.write("\n".join(urls))

            httpx_output = os.path.join(scan_dir, "httpx.json")

            run_command([
                "httpx",
                "-l", urls_file,
                "-json",
                "-o", httpx_output,
                "-status-code",
                "-title",
                "-tech-detect",
                "-silent",
            ], timeout=settings.HTTX_TIMEOUT, scan_id=scan_id)

            total_web = parse_httpx(db, scan_id, httpx_output)
            update_scan(db, scan_id, total_web=total_web, stage='web_fallback', progress=80)
            try:
                output, _, _ = run_command([
                    sys.executable, '-m', 'app.core.web_discovery', httpx_output, urls_file,
                ], timeout=30, scan_id=scan_id)
                urls = json.loads(output)
            except RuntimeError as exc:
                if 'timeout after 30s' not in str(exc):
                    raise
                print(f'[{scan_id}] Web fallback time limit; keeping discovered services')
                urls = []
                if os.path.exists(httpx_output):
                    with open(httpx_output) as f:
                        for line in f:
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if record.get('url'):
                                urls.append(record['url'])
                urls = list(dict.fromkeys(urls))
            with open(urls_file, 'w') as f:
                f.write('\n'.join(urls))
            total_web = parse_httpx(db, scan_id, httpx_output)
            update_scan(db, scan_id, total_web=total_web)
            print(f"[{scan_id}] httpx: {total_web} веб-сервисов")

        update_scan(db, scan_id, total_services=sum(bool(p.get("service")) for h in hosts_data for p in h["ports"]))
        # === ЭТАП 4: gowitness ===
        print(f"[{scan_id}] ЭТАП 4: gowitness")
        update_scan(db, scan_id, stage="gowitness", progress=90)

        total_screenshots = 0

        if urls:
            screenshots_dir = os.path.join(scan_dir, "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)

            urls_file = os.path.join(scan_dir, "urls.txt")
            gowitness_db = os.path.join(scan_dir, "gowitness.sqlite3")

            # The wrapper adds Chrome's certificate tolerance for scan screenshots.
            chrome_wrapper = os.path.join(scan_dir, 'scan-chromium')
            with open(chrome_wrapper, 'w') as f:
                f.write('#!/bin/sh\nexec /usr/bin/chromium --ignore-certificate-errors "$@"\n')
            os.chmod(chrome_wrapper, 0o700)
            run_command([
                "gowitness", "scan", "file",
                "-f", urls_file,
                "--screenshot-path", screenshots_dir,
                "--chrome-path", chrome_wrapper,
                "--write-db",
                "--write-db-uri", f"sqlite:///{gowitness_db}",
            ], timeout=settings.GOWITNESS_TIMEOUT, scan_id=scan_id)

            total_screenshots = save_screenshots_local(db, scan_id, screenshots_dir)
            update_scan(db, scan_id, total_screenshots=total_screenshots)
            print(f"[{scan_id}] gowitness: {total_screenshots} скриншотов")

        ensure_active(scan_id)
        # === ЗАВЕРШЕНИЕ ===
        update_scan(
            db, scan_id,
            status=ScanStatus.COMPLETED,
            stage="completed",
            progress=100,
            finished_at=datetime.utcnow(),
        )

        print(f"[{scan_id}] ✅ Завершено: {total_hosts}h / {total_ports}p / {total_web}w / {total_screenshots}s")
        return {
            "status": "completed",
            "scan_id": scan_id,
            "hosts": total_hosts,
            "ports": total_ports,
            "web": total_web,
            "screenshots": total_screenshots,
        }

    except ScanCancelled:
        db.rollback()
        if db.get(Scan, scan_id) is not None:
            update_scan(db, scan_id, status=ScanStatus.CANCELLED, stage='cancelled', finished_at=datetime.utcnow())
        return {'status': 'cancelled'}
    except Exception as e:
        db.rollback()
        print(f"[{scan_id}] ❌ ERROR: {e}")
        try:
            update_scan(db, scan_id, status=ScanStatus.FAILED, error_message=error_text(e), finished_at=datetime.utcnow())
        except ScanCancelled:
            return {'status': 'cancelled'}
        raise
    finally:
        db.close()
