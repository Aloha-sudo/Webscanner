"""One queued native snaffler search, independent of SMB catalog preparation."""
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
from app.core.secret_jobs import request_key
from app.secrets import store

WORKFLOW_TTL=15120

def cleanup_request(scan_id,token):
    redis=secret_store();raw=redis.getdel(request_key(token))
    if raw:
        private=json.loads(raw)
        if private.get('owned'):redis.delete(session_key(private['session']))

def run_search(scan_id,token):
    redis=secret_store();raw=redis.getdel(request_key(token))
    if not raw:return
    private=json.loads(raw);private_token=private['session'];path=store.directory(settings.SCANS_DIR,scan_id,token)
    proc=None;session=None
    try:
        state=store.read(settings.SCANS_DIR,scan_id,token)
        if state['status']!='queued':return
        raw=redis.get(session_key(private_token));session=json.loads(raw) if raw else None
        if not session or session.get('revoked') or session['scan_id']!=scan_id:raise ValueError('session_expired')
        state.update(status='running',phase='discovering',updated_at=store.now());store.write(path,state)
        proc=subprocess.Popen([sys.executable,'-m','app.core.secret_native_probe',str(path)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
        proc.stdin.write(json.dumps({'parent_pid':os.getpid(),'options':session['options'],'secret':session['secret'],
                                     'tuning':state.get('limits',{}),'fast':state.get('fast',True),'max_depth':state.get('max_depth'),'share_names':state.get('share_names',[]),'exclude_shares':state.get('exclude_shares',[])}));proc.stdin.close()
        deadline=time.monotonic()+state.get('time_limit',1800)
        while proc.poll() is None:
            current=store.read(settings.SCANS_DIR,scan_id,token)
            if (path/'cancel').exists() or current.get('cancel_requested'):raise ValueError('cancelled')
            if time.monotonic()>deadline:raise ValueError('secret_timeout')
            raw=redis.get(session_key(private_token))
            if not raw or json.loads(raw).get('revoked'):raise ValueError('session_expired')
            if (path/'progress.json').is_file():state.update(json.loads((path/'progress.json').read_text()))
            state.update(status='running',updated_at=store.now());store.write(path,state);time.sleep(.25)
        if proc.returncode or not (path/'result.json').is_file():raise ValueError('secret_scan_failed')
        state.update(json.loads((path/'result.json').read_text()))
    except Exception as exc:
        try:state=store.read(settings.SCANS_DIR,scan_id,token)
        except FileNotFoundError:return
        code=str(exc) if isinstance(exc,ValueError) and str(exc) in ('cancelled','session_expired','secret_timeout') else 'secret_scan_failed'
        if (path/'progress.json').is_file():state.update(json.loads((path/'progress.json').read_text()))
        state.update(status='cancelled' if code=='cancelled' else 'partial' if code=='secret_timeout' else 'failed',error=code,partial=True)
    finally:
        if proc and proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait()
        if private.get('owned'):
            try:redis.delete(session_key(private_token))
            except Exception:pass
        if session:session.clear()
        for name in ('progress.json','result.json'):(path/name).unlink(missing_ok=True)
    state.update(updated_at=store.now(),finished_at=store.now());store.write(path,state)

@celery_app.task(name='app.core.secret_workflow.native_search',ignore_result=True,soft_time_limit=14520,time_limit=14580)
def native_search(scan_id,token):run_search(scan_id,token)
