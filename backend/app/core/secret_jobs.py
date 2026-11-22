"""Secret scans share SMB capabilities; queue arguments contain IDs only."""
import json
import os
import signal
import subprocess
import sys
import time
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.smb_jobs import secret_store
from app.core.smb_actions import session_key
from app.secrets import store


def request_key(token):return f'webscanner:secrets:request:{token}'

def run(scan_id,token):
    redis=secret_store();request=redis.getdel(request_key(token))
    if not request:return
    request=json.loads(request);path=store.directory(settings.SCANS_DIR,scan_id,token)
    proc=None;session=None
    try:
        state=store.read(settings.SCANS_DIR,scan_id,token)
        if state['status']!='queued':return
        raw=redis.get(session_key(request['session']))
        session=json.loads(raw) if raw else None
        if not session or session.get('revoked') or session['scan_id']!=scan_id:raise ValueError('session_expired')
        from app.reports import smb
        for choice in state['choices']:
            report=smb.get_report(settings.SCANS_DIR,scan_id,choice['report_id'])
            if session.get('report_id'):
                if choice['report_id']!=session['report_id']:raise ValueError('session_expired')
            elif report['host'] not in session['hosts']:raise ValueError('session_expired')
            if choice['share'] not in {share['name'] for share in report['shares']}:raise ValueError('secret_scan_failed')
        state.update(status='running',updated_at=store.now());store.write(path,state)
        proc=subprocess.Popen([sys.executable,'-m','app.core.secret_probe',str(path)],stdin=subprocess.PIPE,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
        proc.stdin.write(json.dumps({'parent_pid':os.getpid(),'root':settings.SCANS_DIR,'scan_id':scan_id,'choices':state['choices'],
                                     'options':session['options'],'secret':session['secret']}));proc.stdin.close()
        deadline=time.monotonic()+600
        while proc.poll() is None:
            current=store.read(settings.SCANS_DIR,scan_id,token)
            if (path/'cancel').exists() or current.get('cancel_requested'):raise ValueError('cancelled')
            if time.monotonic()>deadline:raise ValueError('secret_timeout')
            raw=redis.get(session_key(request['session']))
            if not raw or json.loads(raw).get('revoked'):raise ValueError('session_expired')
            progress=path/'progress.json'
            if progress.exists():state.update(json.loads(progress.read_text()))
            state['updated_at']=store.now();store.write(path,state);time.sleep(.25)
        if proc.returncode or not (path/'result.json').is_file():raise ValueError('secret_scan_failed')
        result=json.loads((path/'result.json').read_text());state.update(result)
        if (path/'cancel').exists():state.update(status='cancelled',error='cancelled')
        if result.get('error') in ('authentication_failed','account_locked','account_disabled'):
            redis.set(session_key(request['session']),json.dumps({**session,'secret':'','revoked':result['error']}),ex=60)
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and str(exc) in ('cancelled','session_expired','secret_timeout') else 'secret_scan_failed'
        try:state=store.read(settings.SCANS_DIR,scan_id,token)
        except FileNotFoundError:return
        state.update(status='cancelled' if code=='cancelled' else 'failed',error=code)
    finally:
        if proc and proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait()
        for name in ('content.bin','progress.json','progress.json.tmp','result.json','result.json.tmp'):
            (path/name).unlink(missing_ok=True)
        if session:session.clear()
    state.update(updated_at=store.now(),finished_at=store.now());store.write(path,state)

@celery_app.task(name='app.core.secret_jobs.scan_secrets',ignore_result=True)
def scan_secrets(scan_id,token):run(scan_id,token)
