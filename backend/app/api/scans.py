import os
import shutil
from datetime import datetime, timezone
import io
import csv
import json
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session

from app.core.scan_lifecycle import expire_overdue_scans
from app.core.catalog import resolve_context
from app.core.db import get_db
from app.core.config import settings
from app.models.scan import Scan, ScanStatus, Screenshot, Host, Port, Service, Project, NetworkPart
from app.schemas.scan import (
    ScanCreate,
    ScanResponse,
    ScanListResponse,
    ScanDetailResponse,
    ScanUpdate,
    TeamMetadata,
    ProjectDelete,
)
from app.tasks.scan_tasks import run_scan, parse_httpx


router = APIRouter(prefix="/api/scans", tags=["scans"])


# ============================================================
#  СПРАВОЧНИК ПРОФИЛЕЙ
# ============================================================

@router.get("/speed-profiles")
def get_speed_profiles():
    """Возвращает доступные режимы скорости и их параметры."""
    from app.tasks.scan_tasks import SPEED_PROFILES
    return SPEED_PROFILES


@router.get("/port-profiles")
def get_port_profiles():
    """Возвращает доступные профили портов."""
    from app.core.config import settings
    result = {}
    for name, ports in settings.PORT_PROFILES.items():
        result[name] = {
            "ports": ports if ports else "dynamic",
            "count": 100 if name == "top100" else 1000 if name == "top1000" else len(ports.split(",")) if ports and "-" not in ports else None,
        }
    return result


@router.post("", response_model=ScanResponse, status_code=201)
def create_scan(payload: ScanCreate, db: Session = Depends(get_db)):
    return enqueue_scan(payload, db)


def enqueue_scan(payload: ScanCreate, db: Session, retry_of_id=None):
    """Создать новый скан."""
    # Валидация scan_type
    valid_types = {"quick", "top100", "top1000", "web", "full", "custom"}
    if payload.scan_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scan_type. Use: {sorted(valid_types)}",
        )

    if payload.scan_type == "custom" and not payload.ports:
        raise HTTPException(
            status_code=400,
            detail="ports required for custom scan_type",
        )

    if payload.speed not in {"normal", "fast", "hard"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid speed. Use: normal, fast, hard",
        )

    try:
        context=resolve_context(db,payload,Project,NetworkPart)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    scan = Scan(
        retry_of_id=retry_of_id,
        dns_options=payload.dns_options.model_dump() if payload.dns_options else None,
        **{k:context[k] for k in TeamMetadata.model_fields},
        target=payload.target,
        scan_type=payload.scan_type,
        ports=payload.ports,
        comment=payload.comment,
        speed=payload.speed,
        exclude_ips=payload.exclude_ips,
        exclude_hosts=payload.exclude_hosts,
        exclude_ports=payload.exclude_ports,
        status=ScanStatus.QUEUED,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    # Запускаем Celery-задачу с параметрами профиля + скорости
    try:
        exclusions = {name: getattr(payload, name) for name in ('exclude_ips','exclude_hosts','exclude_ports') if getattr(payload,name)}
        # An old worker rejects this keyword rather than silently ignoring exclusions.
        task_options = {'exclusions': exclusions} if exclusions else {}
        if payload.dns_options and payload.dns_options.enabled:
            task_options['dns_requested'] = True
        run_scan.delay(scan.id, payload.scan_type, payload.ports, payload.speed, **task_options)
    except Exception:
        scan.status = ScanStatus.FAILED
        scan.error_message = 'Не удалось поставить задачу в очередь'
        scan.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(503, f'Очередь сканирования недоступна. Неудачный запуск сохранён как #{scan.id}')

    return scan


@router.post('/{scan_id}/retry', response_model=ScanResponse, status_code=201)
def retry_scan(scan_id: int, overrides: dict | None = None, db: Session = Depends(get_db)):
    from app.core.retry import retry_payload
    from pydantic import ValidationError
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(404, 'Скан не найден')
    if scan.scan_type.startswith('import-'):
        raise HTTPException(409, 'Импорт нельзя повторить как скан: создайте новое обследование с явной целью')
    if scan.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(409, 'Дождитесь завершения или отмените текущий скан')
    allowed = {'target', 'scan_type', 'ports', 'speed', 'source_host', 'comment', 'exclude_ips', 'exclude_hosts', 'exclude_ports', 'dns_options'}
    if overrides and set(overrides) - allowed:
        raise HTTPException(422, 'Неподдерживаемые параметры повтора')
    try:
        payload = retry_payload(scan, overrides)
    except ValidationError as exc:
        raise HTTPException(422, str(exc))
    return enqueue_scan(payload, db, retry_of_id=scan.id)


@router.get("", response_model=ScanListResponse)
def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    project_id: int | None = Query(None, ge=1),
    network_part_id: int | None = Query(None, ge=1),
    project: str | None = None,
    network: str | None = None,
    db: Session = Depends(get_db),
):
    """Список всех сканов."""
    expire_overdue_scans(db, Scan, ScanStatus)
    query = db.query(Scan)
    if project_id is not None:
        query=query.filter(Scan.project_id==project_id)
    if network_part_id is not None:
        query=query.filter(Scan.network_part_id==network_part_id)
    if project is not None:
        query = query.filter(Scan.project == project)
    if network is not None:
        query = query.filter(Scan.network == network)
    total = query.count()
    scans = (
        query
        .order_by(Scan.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "scans": scans}


def ip_sort_key(ip: str):
    """Ключ для сортировки IP по числовым октетам."""
    try:
        return tuple(int(x) for x in ip.split("."))
    except Exception:
        return (0, 0, 0, 0)


@router.post('/import', response_model=ScanDetailResponse, status_code=201)
async def import_report(file: UploadFile = File(...), comment: str = Form('', max_length=1000), metadata: str = Form('{}', max_length=12000), db: Session = Depends(get_db)):
    from app.reports.parser import parse_report
    from pydantic import ValidationError
    try:
        team = TeamMetadata.model_validate_json(metadata)
        team = TeamMetadata(**resolve_context(db,team,Project,NetworkPart))
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    try:
        content = await file.read(20 * 1024 * 1024 + 1)
        report = parse_report(content, file.filename or '')
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        await file.close()
    now = datetime.now(timezone.utc)
    scan = Scan(**team.model_dump(), target=(os.path.basename(file.filename or 'Отчёт')[:255]),
                scan_type='import-' + report['source'], comment=comment or None,
                status=ScanStatus.COMPLETED, stage='imported', progress=100,
                started_at=now, finished_at=now, total_hosts=len(report['hosts']),
                total_ports=sum(len(h['ports']) for h in report['hosts']),
                total_services=sum(bool(p.get('service')) for h in report['hosts'] for p in h['ports']),
                total_web=0, total_screenshots=0)
    db.add(scan)
    import_dir = None
    import_dir_created = False
    try:
        db.flush()
        import_dir = os.path.join(settings.SCANS_DIR, str(scan.id))
        os.makedirs(import_dir, exist_ok=False)
        import_dir_created = True
        with open(os.path.join(import_dir, 'original.report'), 'wb') as out:
            out.write(content)
        with open(os.path.join(import_dir, 'import.json'), 'w') as out:
            json.dump({'filename': os.path.basename(file.filename or 'report'), 'source': report['source'], 'warnings': report['warnings']}, out, ensure_ascii=False)
        for h in report['hosts']:
            host = Host(scan_id=scan.id, ip=h['ip'], hostname=h['hostname'], os=h['os'], dns_result=h.get('dns_result'))
            db.add(host); db.flush()
            for port in h['ports']:
                web = port.get('web')
                record = Port(host_id=host.id, **{k:v for k,v in port.items() if k != 'web'})
                db.add(record)
                if web and web.get('url'):
                    db.flush()
                    db.add(Service(port_id=record.id, url=str(web['url'])[:500],
                                   status_code=web.get('status_code'), title=str(web['title'])[:500] if web.get('title') else None,
                                   technologies=json.dumps(web['technologies']) if isinstance(web.get('technologies'),list) else web.get('technologies'),
                                   ssl=bool(web.get('ssl', str(web['url']).startswith('https://')))))
                    scan.total_web += 1
        db.commit()
        db.refresh(scan)
    except Exception:
        db.rollback()
        if import_dir_created:
            shutil.rmtree(import_dir, ignore_errors=True)
        raise
    return scan


@router.get('/{scan_id}/original')
def original_report(scan_id: int, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if scan is None or not scan.scan_type.startswith('import-'):
        raise HTTPException(404, 'Исходный импортированный отчёт не найден')
    path = os.path.join(settings.SCANS_DIR, str(scan_id), 'original.report')
    if not os.path.isfile(path):
        raise HTTPException(404, 'Файл отчёта не найден')
    return FileResponse(path, media_type='application/octet-stream', filename=scan.target)


@router.get('/team-contexts')
def team_contexts(db: Session = Depends(get_db)):
    rows = db.query(Scan.project, Scan.network).filter(Scan.project.isnot(None), Scan.network.isnot(None)).distinct().all()
    return [{'project':p,'network':n} for p,n in sorted(rows)]


@router.get('/project-summary')
def project_summary(project: str = Query(..., min_length=1, max_length=120), db: Session = Depends(get_db)):
    rows=db.query(Scan).filter(Scan.project==project).all()
    if not rows:
        raise HTTPException(404, 'Проект не найден или в нём нет отчётов')
    return {'project':project,'report_count':len(rows),'networks':sorted({r.network or 'Без сети' for r in rows}),
            'active_count':sum(r.status in (ScanStatus.RUNNING,ScanStatus.QUEUED) for r in rows)}


@router.delete('/project')
def delete_project(payload: ProjectDelete, db: Session = Depends(get_db)):
    # Legacy endpoint follows the same safe default as the catalog.
    from app.api.catalog import delete_project as delete_catalog_project, DeleteProject
    project=db.query(Project).filter(Project.name==payload.project).first()
    if project is None:
        raise HTTPException(404,'Проект не найден')
    return delete_catalog_project(project.id,DeleteProject(expected_count=payload.expected_count,delete_reports=payload.delete_reports),db)


@router.get('/visibility')
def visibility(report_ids: str = Query(..., max_length=2000), project_id: int | None = Query(None, ge=1), network_part_id: int | None = Query(None, ge=1), project: str | None = None, network: str | None = None, whole_project: bool = False, merge_parts: bool = False, db: Session = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    from app.reports.visibility import build_visibility
    try:
        ids=list(dict.fromkeys(int(i) for i in report_ids.split(',')))
    except ValueError:
        raise HTTPException(422,'Некорректные номера отчётов')
    if not ids or len(ids)>50:
        raise HTTPException(422,'Выберите от 1 до 50 отчётов')
    query=db.query(Scan).options(selectinload(Scan.hosts).selectinload(Host.ports)).filter(Scan.id.in_(ids))
    if project_id is not None:
        query=query.filter(Scan.project_id==project_id)
    elif project:
        query=query.filter(Scan.project==project)
    else:
        raise HTTPException(422,'Выберите проект')
    if not whole_project:
        if network_part_id is not None:
            query=query.filter(Scan.network_part_id==network_part_id)
        elif network:
            query=query.filter(Scan.network==network)
        else:
            raise HTTPException(422,'Выберите часть сети или режим «Весь проект»')
    scans=query.all()
    if len(scans)!=len(ids):
        raise HTTPException(422,'Выбранные отчёты не соответствуют проекту или фильтру части сети')
    if any(s.status in (ScanStatus.RUNNING,ScanStatus.QUEUED) for s in scans):
        raise HTTPException(409,'Дождитесь завершения выбранных сканов или остановите их')
    if any(not s.source_host for s in scans):
        raise HTTPException(422,'Укажите точку сканирования для каждого отчёта')
    lookup={s.id:s for s in scans}
    reports=[]
    total_ports=sum(len(h.ports) for s in scans for h in s.hosts)
    if total_ports>50000:
        raise HTTPException(422,'В выбранных отчётах больше 50000 портов. Выберите меньше отчётов')
    for id in ids:
        s=lookup[id]
        reports.append({'id':s.id,'target':s.target, **{k:getattr(s,k) for k in TeamMetadata.model_fields},'created_at':s.created_at,'exclude_ips':s.exclude_ips,'exclude_ports':s.exclude_ports,'exclude_hosts':s.exclude_hosts,
                        'scope_confirmed':s.scope_confirmed and s.status==ScanStatus.COMPLETED,
                        'hosts':[{'ip':h.ip,'hostname':h.hostname,'ports':[{'port':p.port,'protocol':p.protocol,'service':p.service,'version':p.version} for p in h.ports]} for h in s.hosts]})
    try:
        return build_visibility(reports,whole_project=whole_project,merge_parts=whole_project and merge_parts)
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@router.get('/compare')
def compare_scans(before: int, after: int, db: Session = Depends(get_db)):
    from app.reports.compare import compare_reports
    if before == after:
        raise HTTPException(422, 'Выберите два разных отчёта')
    scans = [db.get(Scan, scan_id) for scan_id in (before, after)]
    if any(s is None for s in scans):
        raise HTTPException(404, 'Отчёт не найден')
    if any(s.status != ScanStatus.COMPLETED for s in scans):
        raise HTTPException(409, 'Сравнивать можно только завершённые отчёты')
    result = compare_reports(*[_scan_to_dict(s) for s in scans])
    if any(getattr(scans[0],name) != getattr(scans[1],name) for name in ('exclude_ips','exclude_hosts','exclude_ports')):
        result['warnings'].append('У отчётов разные исключения адресов или портов. Это может объяснять различия результатов.')
    result['before'] = {'id': before, 'target': scans[0].target}
    result['after'] = {'id': after, 'target': scans[1].target}
    return result


@router.get("/{scan_id}", response_model=ScanDetailResponse)
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    """Детали скана."""
    expire_overdue_scans(db, Scan, ScanStatus)
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    scan.hosts.sort(key=lambda h: ip_sort_key(h.ip))

    for host in scan.hosts:
        host.ports.sort(key=lambda p: p.port)

    return scan


@router.patch("/{scan_id}", response_model=ScanResponse)
def update_scan_meta(
    scan_id: int,
    payload: ScanUpdate,
    db: Session = Depends(get_db),
):
    """Обновляет мета-информацию скана (комментарий)."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    context_fields={'project_id','network_part_id','project','network'}
    if context_fields & payload.model_fields_set:
        try:
            resolved=resolve_context(db,payload,Project,NetworkPart)
        except ValueError as exc:
            raise HTTPException(422,str(exc))
        for name in context_fields:
            setattr(scan,name,resolved[name])
    for name in TeamMetadata.model_fields:
        if name not in context_fields and name in payload.model_fields_set:
            setattr(scan, name, getattr(payload, name))
    if payload.comment is not None:
        scan.comment = payload.comment

    db.commit()
    db.refresh(scan)
    return scan


@router.delete("/{scan_id}", status_code=204)
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    """Удалить скан."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(409, 'Сначала отмените скан')
    db.delete(scan)
    db.commit()
    shutil.rmtree(os.path.join(settings.SCANS_DIR, str(scan_id)), ignore_errors=True)
    return None


@router.post('/{scan_id}/recover-web-results', response_model=ScanDetailResponse)
def recover_web_results(scan_id: int, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, 'Скан не найден')
    if scan.status in (ScanStatus.RUNNING, ScanStatus.QUEUED):
        raise HTTPException(409, 'Сначала остановите скан')
    path = os.path.join(settings.SCANS_DIR, str(scan_id), 'httpx.json')
    if not os.path.isfile(path):
        raise HTTPException(404, 'Сохранённый файл веб-результатов отсутствует')
    try:
        scan.total_web = parse_httpx(db, scan_id, path)
        db.commit()
        db.refresh(scan)
    except Exception:
        db.rollback()
        raise HTTPException(500, 'Не удалось восстановить веб-результаты')
    return scan


@router.post("/{scan_id}/cancel")
def cancel_scan(scan_id: int, db: Session = Depends(get_db)):
    """Отменить скан."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status in [ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Scan already finished")

    scan.status = ScanStatus.CANCELLED
    scan.stage = 'cancelled'
    scan.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "cancelled"}


# ============================================================
#  СКРИНШОТЫ
# ============================================================

@router.get("/screenshots/{screenshot_id}/image")
def get_screenshot_image(screenshot_id: int, db: Session = Depends(get_db)):
    """
    Отдаёт файл скриншота по id.
    Путь хранится в minio_path в формате:
        local://scan_<scan_id>/<filename>
    Реальный файл: <SCANS_DIR>/<scan_id>/screenshots/<filename>
    """
    screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
    if not screenshot:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    mp = screenshot.minio_path or ""
    if not mp.startswith("local://scan_"):
        raise HTTPException(status_code=400, detail=f"Unsupported path: {mp}")

    # Парсим "local://scan_17/http---192.168.1.1-80.jpeg"
    rest = mp[len("local://scan_"):]           # "17/http---192.168.1.1-80.jpeg"
    parts = rest.split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Malformed path")

    scan_id_str, filename = parts
    filename = os.path.basename(filename)      # защита от path traversal

    path = os.path.join(
        settings.SCANS_DIR,
        scan_id_str,
        "screenshots",
        filename,
    )

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if filename.lower().endswith(".png"):
        media_type = "image/png"
    elif filename.lower().endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    else:
        media_type = "application/octet-stream"

    return FileResponse(path, media_type=media_type)


# ============================================================
#  ЭКСПОРТ ОТЧЁТА
# ============================================================

def _scan_to_dict(scan: Scan) -> dict:
    """Сериализует скан в dict для JSON/CSV/XML."""
    hosts = []
    for host in scan.hosts:
        ports = []
        for port in host.ports:
            svc = port.service_obj
            ports.append({
                "port": port.port,
                "protocol": port.protocol,
                "state": port.state,
                "service": port.service,
                "version": port.version,
                "banner": port.banner,
                "url": svc.url if svc else None,
                "status_code": svc.status_code if svc else None,
                "title": svc.title if svc else None,
                "technologies": svc.technologies if svc else None,
                "ssl": svc.ssl if svc else False,
            })
        hosts.append({
            "ip": host.ip,
            "hostname": host.hostname,
            "dns_result": host.dns_result,
            "os": host.os,
            "ports": ports,
        })

    screenshots = [
        {
            "id": s.id,
            "url": s.url,
            "path": s.minio_path,
            "status_code": s.status_code,
            "title": s.title,
        }
        for s in scan.screenshots
    ]

    return {
        "scan": {
            "id": scan.id,
            "target": scan.target,
            "scan_type": scan.scan_type,
            "dns_options": scan.dns_options,
            "dns_status": scan.dns_status,
            "dns_summary": scan.dns_summary,
            "speed": scan.speed,
            **{k: (getattr(scan,k).isoformat() if k == "observed_at" and getattr(scan,k) else getattr(scan,k)) for k in TeamMetadata.model_fields},
            "exclude_ips": scan.exclude_ips,
            "exclude_hosts": scan.exclude_hosts,
            "exclude_ports": scan.exclude_ports,
            "ports": scan.ports,
            "comment": scan.comment,
            "status": scan.status.value if hasattr(scan.status, "value") else str(scan.status),
            "stage": scan.stage,
            "progress": scan.progress,
            "total_hosts": scan.total_hosts,
            "total_ports": scan.total_ports,
            "total_web": scan.total_web,
            "total_screenshots": scan.total_screenshots,
            "error_message": scan.error_message,
            "created_at": scan.created_at.isoformat() if scan.created_at else None,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        },
        "hosts": hosts,
        "screenshots": screenshots,
    }


@router.get("/{scan_id}/export")
def export_scan(
    scan_id: int,
    format: str = Query("json", pattern="^(json|xml|csv)$"),
    db: Session = Depends(get_db),
):
    """
    Экспорт отчёта по скану.
    format: json | xml | csv
    """
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    data = _scan_to_dict(scan)

    # === JSON ===
    if format == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="scan_{scan_id}.json"',
            },
        )

    if format in ('xml', 'csv'):
        for host in data['hosts']:
            names = (host.get('dns_result') or {}).get('names') or []
            host['hostname'] = host['hostname'] or (names[0] if names else None)

    # === XML (в стиле nmap) ===
    if format == "xml":
        root = Element("webscanner-scan")
        root.set("scanner", "webscanner")
        root.set("version", "0.1.0")

        s = SubElement(root, "scan")
        s.set("id", str(scan.id))
        s.set("target", scan.target or "")
        s.set("scan_type", scan.scan_type or "")
        s.set("status", data["scan"]["status"])
        for name in ("exclude_ips", "exclude_hosts", "exclude_ports"):
            if getattr(scan, name):
                SubElement(s, name).text = getattr(scan, name)
        if scan.comment:
            c = SubElement(s, "comment")
            c.text = scan.comment
        if scan.started_at:
            s.set("started_at", scan.started_at.isoformat())
        if scan.finished_at:
            s.set("finished_at", scan.finished_at.isoformat())

        hosts_el = SubElement(root, "hosts")
        for h in data["hosts"]:
            h_el = SubElement(hosts_el, "host")
            h_el.set("ip", h["ip"])
            if h["hostname"]:
                hn = SubElement(h_el, "hostname")
                hn.text = h["hostname"]
            if h["os"]:
                os_el = SubElement(h_el, "os")
                os_el.text = h["os"]
            ports_el = SubElement(h_el, "ports")
            for p in h["ports"]:
                p_el = SubElement(ports_el, "port")
                p_el.set("protocol", p["protocol"] or "tcp")
                p_el.set("portid", str(p["port"]))
                state_el = SubElement(p_el, "state")
                state_el.set("state", p["state"] or "open")
                if p["service"]:
                    svc_el = SubElement(p_el, "service")
                    svc_el.set("name", p["service"])
                    if p["version"]:
                        svc_el.set("version", p["version"])
                if p["url"]:
                    url_el = SubElement(p_el, "url")
                    url_el.text = p["url"]
                if p["status_code"] is not None:
                    sc = SubElement(p_el, "status-code")
                    sc.text = str(p["status_code"])
                if p["title"]:
                    t = SubElement(p_el, "title")
                    t.text = p["title"]

        screens_el = SubElement(root, "screenshots")
        for sc in data["screenshots"]:
            s_el = SubElement(screens_el, "screenshot")
            s_el.set("url", sc["url"])
            s_el.set("path", sc["path"])

        # Pretty print
        rough = tostring(root, encoding="utf-8")
        pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")

        return Response(
            content=pretty,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="scan_{scan_id}.xml"',
            },
        )

    # === CSV ===
    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "scan_id", "target", "scan_type", "host_ip", "hostname",
            "port", "protocol", "state", "service", "version",
            "url", "status_code", "title", "technologies", "ssl",
        ])
        for h in data["hosts"]:
            if not h["ports"]:
                writer.writerow([
                    scan.id, scan.target, scan.scan_type, h["ip"], h["hostname"],
                    "", "", "", "", "", "", "", "", "", "",
                ])
                continue
            for p in h["ports"]:
                writer.writerow([
                    scan.id, scan.target, scan.scan_type, h["ip"], h["hostname"],
                    p["port"], p["protocol"], p["state"], p["service"] or "", p["version"] or "",
                    p["url"] or "", p["status_code"] if p["status_code"] is not None else "",
                    p["title"] or "", p["technologies"] or "", "yes" if p["ssl"] else "no",
                ])

        content = buf.getvalue()
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="scan_{scan_id}.csv"',
            },
        )


