"""DNS jobs run on the scan worker, never on the API host.

A job token prevents stale deliveries/results from overwriting a newer lookup.
"""
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.exclusions import excluded_ports
from app.core.process import execute, ScanCancelled
from app.models.scan import Scan, Host, NetworkPart


def new_dns_job(scan, options):
    scan.dns_options = options
    scan.dns_status = 'queued'
    scan.dns_job_id = uuid.uuid4().hex
    scan.dns_summary = {'queued_at': datetime.now(timezone.utc).isoformat()}
    return scan.dns_job_id


def run_dns_job(scan_id, token, check_cancelled=lambda: None):
    def active():
        check_cancelled()
        with SessionLocal() as db:
            scan = db.get(Scan, scan_id)
            if scan is None or scan.dns_job_id != token:
                raise ScanCancelled()
    try:
        with SessionLocal() as db:
            claimed = db.query(Scan).filter(Scan.id == scan_id, Scan.dns_job_id == token, Scan.dns_status == 'queued').update({Scan.dns_status: 'running'}, synchronize_session=False)
            db.commit()
            if not claimed:
                return
            scan = db.get(Scan, scan_id)
            part = db.get(NetworkPart, scan.network_part_id) if scan.network_part_id else None
            options = dict(scan.dns_options or {})
            payload = {'options': options, 'saved': part.dns_defaults if part else None, 'blocked_ports': sorted(excluded_ports(scan.exclude_ports)), 'hosts': [{'ip': h.ip, 'ports': [{'port': p.port, 'protocol': p.protocol} for p in h.ports]} for h in scan.hosts]}
            if not options.get('server') and part and part.dns_defaults and options.get('transport', 'auto') == 'auto':
                payload['options']['transport'] = part.dns_defaults.get('transport', 'auto')
        # Temporary files avoid command length limits, stdout truncation and stale
        # artifacts; persistent evidence lives in the DB and exports.
        os.makedirs(settings.SCANS_DIR, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.dns-', dir=settings.SCANS_DIR) as work:
            source, output = os.path.join(work, 'input.json'), os.path.join(work, 'output.json')
            with open(source, 'w') as stream:
                json.dump(payload, stream)
            execute([sys.executable, '-m', 'app.core.dns_resolution', source, output], timeout=70, check_cancelled=active)
            with open(output) as stream:
                result = json.load(stream)
        active()
        with SessionLocal() as db:
            scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
            if scan is None or scan.dns_job_id != token:
                return
            for host in scan.hosts:
                if host.ip in result['hosts']:
                    host.dns_result = result['hosts'][host.ip]
            scan.dns_summary = result['summary']
            scan.dns_status = 'partial' if result['summary'].get('budget_exceeded') or result['summary'].get('skipped') else 'completed'
            remembered = result['summary'].get('remember')
            if scan.network_part_id and remembered:
                part = db.get(NetworkPart, scan.network_part_id)
                if part:
                    part.dns_defaults = remembered
            db.commit()
    except ScanCancelled:
        with SessionLocal() as db:
            db.query(Scan).filter(Scan.id == scan_id, Scan.dns_job_id == token).update({Scan.dns_status: 'cancelled'}, synchronize_session=False)
            db.commit()
        raise
    except Exception:
        logging.getLogger(__name__).exception('DNS lookup failed for scan %s', scan_id)
        with SessionLocal() as db:
            db.query(Scan).filter(Scan.id == scan_id, Scan.dns_job_id == token).update({Scan.dns_status: 'failed', Scan.dns_summary: {'error': 'Не удалось выполнить DNS-проверку. Проверьте доступность worker и установку dnspython.'}}, synchronize_session=False)
            db.commit()
        # DNS failure must not turn a successful port scan into failed.


@celery_app.task(name='app.core.dns_jobs.resolve_scan_dns')
def resolve_scan_dns(scan_id, token):
    try:
        run_dns_job(scan_id, token)
    except ScanCancelled:
        return {'status': 'cancelled'}
