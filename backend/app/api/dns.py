from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.dns_jobs import new_dns_job, resolve_scan_dns
from app.models.scan import Scan, ScanStatus
from app.schemas.dns import DnsOptions
from app.schemas.scan import ScanResponse

router = APIRouter(prefix='/api/scans', tags=['dns'])


@router.post('/{scan_id}/resolve-names', response_model=ScanResponse, status_code=202)
def resolve_names(scan_id: int, payload: DnsOptions, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
    if scan is None:
        raise HTTPException(404, 'Скан не найден')
    if scan.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(409, 'Дождитесь завершения скана')
    if not payload.enabled:
        raise HTTPException(422, 'Для запуска включите определение имён')
    if not scan.hosts:
        raise HTTPException(409, 'В отчёте нет хостов для определения имён')
    if scan.dns_status in ('queued', 'running'):
        queued = (scan.dns_summary or {}).get('queued_at')
        try:
            recent = datetime.fromisoformat(queued) > datetime.now(timezone.utc) - timedelta(minutes=5)
        except (TypeError, ValueError):
            recent = False
        if recent:
            raise HTTPException(409, 'Определение имён уже выполняется. Если worker недоступен, повтор будет доступен через 5 минут.')
    token = new_dns_job(scan, payload.model_dump())
    db.commit()
    try:
        resolve_scan_dns.delay(scan.id, token)
    except Exception:
        scan.dns_status = 'failed'
        scan.dns_summary = {'error': 'Очередь DNS-проверки недоступна. Можно повторить запрос.'}
        db.commit()
        raise HTTPException(503, 'Очередь DNS-проверки недоступна')
    db.refresh(scan)
    return scan
