"""SMB queue orchestration. Only scan ID and opaque token reach the broker."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.process import ScanCancelled
from app.core.smb_discovery import discover_targets
from app.models.scan import Scan
from app.reports.smb import store_report


def now():
    return datetime.now(timezone.utc).isoformat()


def secret_store():
    from redis import Redis
    return Redis.from_url(settings.REDIS_URL, socket_timeout=5, socket_connect_timeout=5)


def secret_key(token):
    return f'webscanner:smb:credential:{token}'


def update_job(scan_id, token, **changes):
    with SessionLocal() as db:
        scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
        job = dict(scan.smb_job or {}) if scan else {}
        if job.get('id') != token or job.get('status') not in ('queued', 'running'):
            raise ScanCancelled()
        scan.smb_job = {**job, **changes, 'updated_at': now()}
        db.commit()
        return scan.smb_job


def probe_process(host, options, password, check_cancelled):
    with tempfile.TemporaryDirectory(prefix='webscanner-smb-') as temporary:
        output = Path(temporary) / 'result.json'
        proc = subprocess.Popen([sys.executable, '-m', 'app.core.smb_probe', str(output)],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                text=True, start_new_session=True)
        try:
            proc.stdin.write(json.dumps({'host': host, 'options': options, 'password': password}))
            proc.stdin.close()
            deadline = time.monotonic() + 70
            while proc.poll() is None:
                check_cancelled()
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait()
        if not output.exists():
            if proc.returncode != 0:
                raise RuntimeError('SMB probe failed')
            raise RuntimeError('SMB probe produced no report')
        result = json.loads(output.read_text())
        if result['status'] == 'running':
            result.update(status='partial', partial=True)
            result['limits'].append('time')
        return result


def run_job(scan_id, token):
    password = ''
    claimed = False
    try:
        # Claim under row lock: redeliveries cannot run the same credentials again.
        with SessionLocal() as db:
            scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
            if scan is None or (scan.smb_job or {}).get('id') != token or scan.smb_job.get('status') != 'queued':
                return
            job = dict(scan.smb_job)
            scan.smb_job = {**job, 'status': 'running', 'updated_at': now()}
            db.commit()
        claimed = True
        options = job['options']
        if options['mode'] == 'credentials':
            value = secret_store().getdel(secret_key(token))
            if value is None:
                update_job(scan_id, token, status='failed', error='SMB: данные входа истекли в очереди, запустите проверку снова')
                return
            password = value.decode()
        deadline = time.monotonic() + 900
        reports = []
        auth_stop = False
        heartbeat = [0.0]
        def active():
            tick = time.monotonic()
            if tick >= heartbeat[0]:
                update_job(scan_id, token)
                heartbeat[0] = tick + 1
            if tick >= deadline:
                raise TimeoutError()
        update_job(scan_id, token, phase='discovery')
        available = discover_targets(options['targets'], active)
        skipped = len(options['targets']) - len(available)
        completed = skipped
        update_job(scan_id, token, phase='files' if options['spider'] else 'shares',
                   reachable=len(available), skipped=skipped, completed=completed)
        for host in available:
            if time.monotonic() >= deadline:
                break
            update_job(scan_id, token, current_host=host)
            try:
                data = probe_process(host, options, password, active)
            except TimeoutError:
                break
            # Keep the row lock through publication: deletion/cancellation cannot resurrect files.
            with SessionLocal() as db:
                scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
                state = dict(scan.smb_job or {}) if scan else {}
                if state.get('id') != token or state.get('status') != 'running':
                    raise ScanCancelled()
                metadata = {'format': 'webscanner-smb', 'host': host,
                            'account': f"{options['domain']}\\{options['username']}".lstrip('\\') if options['mode'] == 'credentials' else None,
                            'auth_method': options['credential_type'] if options['mode'] == 'credentials' else 'anonymous',
                            'source': 'worker', 'author': scan.author, 'observed_at': data['observed_at'],
                            'filename': f'{host}-smb.json', 'server': data['server'], 'status': data['status'],
                            'authentication': data.get('authentication', 'failed' if data['status'] == 'login_failed' else None),
                            'coverage': data.get('coverage'), 'job_id': token,
                            'error': data['error'], 'partial': data['partial'], 'limits': data['limits'],
                            'options': {k: options[k] for k in ('spider','depth','max_entries','include_admin')}}
                report = store_report(settings.SCANS_DIR, scan_id, json.dumps(data, ensure_ascii=False).encode(), metadata,
                                      data['shares'], data['entries'])
                reports.append(report['id'])
                completed += 1
                scan.smb_job = {**state, 'report_ids': reports, 'completed': completed, 'updated_at': now()}
                db.commit()
            if options['mode'] == 'credentials' and data['status'] == 'login_failed' and data['error'] in ('authentication_failed', 'account_locked', 'account_disabled', 'kerberos_principal_unknown', 'kerberos_key_expired'):
                auth_stop = True
                break
        update_job(scan_id, token, status='partial' if auth_stop or completed < len(options['targets']) else 'completed',
                   current_host=None, finished_at=now(),
                   error='SMB: вход отклонён, остальные адреса не проверены' if auth_stop else None)
    except ScanCancelled:
        pass
    except Exception:
        # Never log exceptions/locals or credentials supplied to network libraries.
        try:
            update_job(scan_id, token, status='failed', current_host=None, finished_at=now(),
                       error='SMB: ошибка worker. Проверьте установку Impacket и доступность Redis')
        except ScanCancelled:
            pass
    finally:
        password = ''
        if claimed:
            try:
                secret_store().delete(secret_key(token))
            except Exception:
                pass


@celery_app.task(name='app.core.smb_jobs.scan_smb', ignore_result=True)
def scan_smb(scan_id, token):
    run_job(scan_id, token)
