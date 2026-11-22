"""Short-lived SMB file sessions/actions. All network IO runs in a worker child."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import os
import signal
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.smb_jobs import secret_store

SESSION_TTL=900
ACTION_TTL=600


def session_key(token): return f'webscanner:smb:session:{token}'
def action_key(token): return f'webscanner:smb:action:{token}'
def request_key(token): return f'webscanner:smb:action-request:{token}'


def action_directory(token):
    if not re.fullmatch('[a-f0-9]{32}',token): raise ValueError('invalid_action')
    root=Path(settings.SCANS_DIR)/'.smb-actions'
    if root.is_symlink(): raise ValueError('invalid_action')
    root.mkdir(exist_ok=True,parents=True,mode=0o700)
    path=root/token
    if path.is_symlink(): raise ValueError('invalid_action')
    return path


def cleanup():
    root=Path(settings.SCANS_DIR)/'.smb-actions'
    if not root.exists() or root.is_symlink(): return
    for directory in root.iterdir():
        if re.fullmatch('[a-f0-9]{32}',directory.name) and not directory.is_symlink() and directory.is_dir():
            if time.time()-directory.stat().st_mtime>ACTION_TTL+120:
                shutil.rmtree(directory,ignore_errors=True)


def run_action(scan_id, token):
    store=secret_store()
    # A redelivered message cannot run the same operation twice.
    value=store.getdel(request_key(token))
    if not value: return
    payload=json.loads(value)
    state_value=store.get(action_key(token))
    if not state_value: return
    state=json.loads(state_value)
    if state['scan_id']!=scan_id or payload['session']!=state['session']: return
    session_value=store.get(session_key(payload['session']))
    if not session_value:
        store.set(action_key(token),json.dumps({**state,'status':'failed','error':'session_expired'}),ex=ACTION_TTL)
        return
    session=json.loads(session_value)
    if session.get('revoked'):
        store.set(action_key(token),json.dumps({**state,'status':'failed','error':session['revoked']}),ex=ACTION_TTL)
        return
    if session['scan_id']!=scan_id: return
    if state.get('source') in ('ftp','local'):
        from app.secrets.sources import validate_file
        if session['options'].get('source')!=state['source']:return
        try:validate_file(session['options'],payload['location'])
        except (ValueError,OSError):
            store.set(action_key(token),json.dumps({**state,'status':'failed','error':'source_outside_scope'}),ex=ACTION_TTL)
            return
    elif session['report_id'] is None:
        if payload['host'] not in session['hosts']: return
    elif session['report_id']!=state['report_id'] or payload['host']!=session['host']:
        return
    proc=None
    directory=None
    try:
        cleanup()
        directory=action_directory(token)
        directory.mkdir(mode=0o700)
        store.set(action_key(token),json.dumps({**state,'status':'running'}),ex=ACTION_TTL)
        module='app.core.secret_file_ops' if state.get('source') in ('ftp','local') else 'app.core.smb_file_ops'
        proc=subprocess.Popen([sys.executable,'-m',module,str(directory)],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
        proc.stdin.write(json.dumps({**payload, 'host':payload['host'],'options':session['options'],'secret':session['secret']}))
        proc.stdin.close()
        deadline=time.monotonic()+60
        while proc.poll() is None:
            if time.monotonic()>deadline: raise TimeoutError()
            # Disconnect invalidates running requests as well as future ones.
            if not store.exists(session_key(payload['session'])): raise ValueError('session_expired')
            time.sleep(0.1)
        if proc.returncode!=0 or not (directory/'result.json').exists(): raise RuntimeError()
        result=json.loads((directory/'result.json').read_text())
        if result.get('error') in ('authentication_failed','account_locked','account_disabled'):
            store.set(session_key(payload['session']),json.dumps({**session,'secret':'','revoked':result['error']}),ex=60)
        store.set(action_key(token),json.dumps({**state,**result}),ex=ACTION_TTL)
        if result['status']=='failed' or state['action']!='download': shutil.rmtree(directory,ignore_errors=True)
    except Exception as exc:
        error='action_timeout' if isinstance(exc,TimeoutError) else 'session_expired' if str(exc)=='session_expired' else 'action_failed'
        store.set(action_key(token),json.dumps({**state,'status':'failed','error':error}),ex=ACTION_TTL)
        if directory: shutil.rmtree(directory,ignore_errors=True)
    finally:
        if proc and proc.poll() is None:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait()
        # No credentials are written to state or disk.
        session.clear()


@celery_app.task(name='app.core.smb_actions.file_action',ignore_result=True)
def file_action(scan_id,token): run_action(scan_id,token)
