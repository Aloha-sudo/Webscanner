"""Offline report adapters. Never execute uploaded reports or their contents."""
from app.core.text import database_text
import ast
import csv
import io
import ipaddress
import json
import re
import xml.etree.ElementTree as ET

MAX_HOSTS = 100000
MAX_PORTS = 500000


def parse_report(content: bytes, filename: str = '') -> dict:
    if not content or len(content) > 20 * 1024 * 1024:
        raise ValueError('Отчёт должен быть непустым и не больше 20 МБ')
    text = None
    for encoding in ('utf-8-sig', 'utf-16', 'cp1251'):
        try:
            text = content.decode(encoding)
            break
        except UnicodeError:
            pass
    if text is None:
        raise ValueError('Не удалось прочитать кодировку отчёта')
    text = text.strip()
    hosts = {}
    warnings = []
    port_count = 0

    def add(ip, port=None, protocol='tcp', state='open', service=None, version=None, hostname=None, os=None, web=None, banner=None):
        nonlocal port_count
        try:
            ip = str(ipaddress.ip_address(str(ip).strip()))
        except ValueError:
            raise ValueError(f'Некорректный IP в отчёте: {str(ip)[:80]}')
        h = hosts.setdefault(ip, {'ip': ip, 'hostname': None, 'os': None, 'ports': {}})
        if len(hosts) > MAX_HOSTS:
            raise ValueError('Слишком много хостов')
        if hostname:
            h['hostname'] = str(hostname)[:255]
        if os:
            h['os'] = str(os)[:255]
        if port is None or port == '':
            return
        try:
            port = int(port)
        except (ValueError, TypeError):
            raise ValueError(f'Некорректный порт: {port}')
        if not 1 <= port <= 65535:
            raise ValueError(f'Порт вне диапазона 1–65535: {port}')
        protocol = str(protocol or 'tcp').lower()
        if protocol not in ('tcp', 'udp', 'sctp'):
            raise ValueError(f'Неизвестный протокол: {protocol}')
        if state and str(state).lower() not in ('open', 'открыт', 'открыто'):
            return
        key = (protocol, port)
        old = h['ports'].get(key, {})
        h['ports'][key] = {'port': port, 'protocol': protocol, 'state': 'open',
                           'service': str(service)[:100] if service else old.get('service'),
                           'version': str(version)[:255] if version else old.get('version')}
        if banner is not None:
            h['ports'][key]['banner'] = database_text(banner)[:8192]
        elif 'banner' in old:
            h['ports'][key]['banner'] = old['banner']
        if web:
            h['ports'][key]['web'] = web
        if not old:
            port_count += 1
        if port_count > MAX_PORTS:
            raise ValueError('Слишком много портов')

    source = 'unknown'
    if text.startswith('<'):
        text = re.sub(r'<!DOCTYPE\s+(?:nmaprun|webscanner-scan)\s*>', '', text, flags=re.I)
        if re.search(r'<!\s*(DOCTYPE|ENTITY)', text, re.I):
            raise ValueError('DTD и XML entities запрещены')
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError('Повреждённый XML') from exc
        if root.tag not in ('nmaprun', 'webscanner-scan'):
            raise ValueError('Поддерживается XML Nmap/Masscan и WebScanner')
        source = root.get('scanner', 'nmap')
        elements = root.findall('host') if root.tag == 'nmaprun' else root.findall('hosts/host')
        for h in elements:
            status = h.find('status')
            if status is not None and status.get('state') != 'up':
                continue
            address = next((a.get('addr') for a in h.findall('address') if a.get('addrtype') in ('ipv4', 'ipv6')), h.get('ip'))
            if not address:
                continue
            hostname = h.find('hostnames/hostname')
            osmatch = h.find('os/osmatch')
            add(address, hostname=hostname.get('name') if hostname is not None else h.findtext('hostname'),
                os=osmatch.get('name') if osmatch is not None else h.findtext('os'))
            for p in h.findall('ports/port'):
                st, svc = p.find('state'), p.find('service')
                add(address, p.get('portid'), p.get('protocol', 'tcp'),
                    st.get('state', 'open') if st is not None else 'open',
                    svc.get('name') if svc is not None else None,
                    ' '.join(filter(None, (svc.get('product'), svc.get('version')))) if svc is not None else None)
    elif text.startswith(('[', '{')):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError('Повреждённый JSON') from exc
        source = 'webscanner' if isinstance(data, dict) and 'hosts' in data else 'masscan'
        rows = data.get('hosts', []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError('JSON должен содержать список хостов')
        for row in rows:
            if not isinstance(row, dict) or not row.get('ip'):
                raise ValueError('В JSON отсутствует IP хоста')
            add(row['ip'], hostname=row.get('hostname'), os=row.get('os'))
            if row.get('dns_result') is not None:
                from app.schemas.dns import DnsEvidence
                try:
                    evidence = DnsEvidence.model_validate(row['dns_result'])
                except ValueError as exc:
                    raise ValueError('Некорректные DNS-данные в JSON') from exc
                hosts[str(ipaddress.ip_address(row['ip']))]['dns_result'] = evidence.model_dump(exclude_none=True)

            if not isinstance(row.get('ports', []), list):
                raise ValueError('JSON: ports должен быть списком')
            for p in row.get('ports', []):
                if not isinstance(p, dict):
                    raise ValueError('JSON: некорректная запись порта')
                add(row['ip'], p.get('port'), p.get('proto', p.get('protocol', 'tcp')), p.get('status', p.get('state', 'open')), p.get('service'), p.get('version'), web={k:p[k] for k in ('url','status_code','title','technologies','ssl') if k in p}, banner=p.get('banner'))
    else:
        matched = 0
        source = 'text'
        for line in text.splitlines():
            # Go's slogger writes: timestamp SUCCESS host:port "quoted banner".
            m = re.fullmatch(r'(?:\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+)?SUCCESS\s+(\S+)\s+("(?:[^"\\]|\\.)*")\s*', line.strip())
            if m:
                endpoint = m[1]
                if endpoint.startswith('['):
                    address = re.fullmatch(r'\[([^]]+)\]:(\d+)', endpoint)
                    if not address:
                        raise ValueError('FastScan: некорректный адрес IPv6')
                    ip, port = address.groups()
                else:
                    try:
                        ip, port = endpoint.rsplit(':', 1)
                    except ValueError:
                        raise ValueError('FastScan: ожидается IP:порт')
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    raise ValueError('FastScan: отчёт содержит имя хоста вместо IP. Сохраните результат сканирования IP-адреса; импорт не выполняет DNS-запросы.')
                try:
                    banner = ast.literal_eval(m[2])
                except (ValueError, SyntaxError):
                    raise ValueError('FastScan: повреждённая строка баннера')
                add(ip, port, banner=banner)
                matched += 1
                source = 'fastscan'
                continue
            m = re.search(r'^\s*(\S+)\s*->\s*\[([\d,\s]*)\]', line)
            if m:
                source = 'rustscan'
                add(m[1])
                for port in m[2].split(','):
                    if port.strip():
                        add(m[1], port.strip())
                matched += 1
                continue
            m = re.search(r'Discovered open port (\d+)/(tcp|udp) on (\S+)', line)
            if m:
                add(m[3], m[1], m[2]); matched += 1; source = 'masscan'
                continue
            m = re.match(r'open\s+(tcp|udp)\s+(\d+)\s+(\S+)', line)
            if m:
                add(m[3], m[2], m[1]); matched += 1; source = 'masscan'
                continue
            m = re.match(r'Host:\s+(\S+)\s+\((.*?)\).*Ports:\s*(.*)', line)
            if m:
                add(m[1], hostname=m[2])
                for item in m[3].split(','):
                    fields = item.strip().split('/')
                    if len(fields) >= 3:
                        add(m[1], fields[0], fields[2], fields[1], fields[4] if len(fields)>4 else None, fields[6] if len(fields)>6 else None)
                matched += 1; source = 'nmap'
        if not matched:
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
                aliases = {'ip': ('ip','ip address','ip-address','host_ip','ip-адрес','ip адрес'),
                           'port': ('port','portid','порт'), 'protocol': ('protocol','proto','протокол'),
                           'hostname': ('hostname','name','host name','имя','имя компьютера'),
                           'state': ('state','status','состояние'), 'service': ('service','служба'),
                           'version': ('version','версия')}
                headers = {str(k).strip().lower(): k for k in reader.fieldnames or []}
                columns = {k: next((headers[a] for a in v if a in headers), None) for k,v in aliases.items()}
                if not columns['ip']:
                    raise ValueError('CSV: требуется колонка IP или IP address / IP-адрес')
                for row in reader:
                    value = lambda key: row.get(columns[key]) if columns[key] else None
                    if not value('ip'):
                        continue
                    # Advanced IP Scanner exports host availability, not port state.
                    add(value('ip'), value('port'), value('protocol') or 'tcp',
                        (value('state') or 'open') if columns['port'] else 'open',
                        value('service'), value('version'), value('hostname'))
                source = 'csv'
            except csv.Error as exc:
                raise ValueError('Формат не распознан. Используйте XML, JSON, CSV, greppable RustScan/Nmap Masscan list или FastScan TXT') from exc
    if not hosts:
        raise ValueError('В отчёте нет распознанных хостов; пустой отчёт нельзя использовать для сравнения')
    warnings.append('Область сканирования неизвестна: отсутствие в отчёте не доказывает, что хост недоступен или порт закрыт.')
    result = []
    for h in sorted(hosts.values(), key=lambda h: (ipaddress.ip_address(h['ip']).version, int(ipaddress.ip_address(h['ip'])))):
        h['ports'] = sorted(h['ports'].values(), key=lambda p: (p['protocol'], p['port']))
        result.append(h)
    return {'source': source, 'hosts': result, 'warnings': warnings}
