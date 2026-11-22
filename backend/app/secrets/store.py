"""Local, credential-free job manifests. No document bytes or secret values here."""
import json
import re
import tempfile
from pathlib import Path
from datetime import datetime,timezone


def now():return datetime.now(timezone.utc).isoformat()

def root_for(root,scan_id):
    base=Path(root)/str(int(scan_id))/'secret-jobs'
    if base.is_symlink() or base.parent.is_symlink():raise ValueError('invalid_job')
    return base

def directory(root,scan_id,token):
    if not re.fullmatch('[a-f0-9]{32}',token):raise FileNotFoundError('secret_job_missing')
    path=root_for(root,scan_id)/token
    if path.is_symlink():raise FileNotFoundError('secret_job_missing')
    return path

def write(path,value,name='state.json'):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=path/name
    if target.is_symlink():raise ValueError('invalid_job')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path,prefix='.'+name+'.',delete=False) as stream:
            temporary=Path(stream.name);json.dump(value,stream,ensure_ascii=False)
        temporary.replace(target)
    finally:
        if temporary:temporary.unlink(missing_ok=True)

def read(root,scan_id,token):
    path=directory(root,scan_id,token)/'state.json'
    if path.is_symlink() or not path.is_file():raise FileNotFoundError('secret_job_missing')
    state=json.loads(path.read_text())
    if state['status'] in ('queued','running') and (datetime.now(timezone.utc)-datetime.fromisoformat(state['updated_at'])).total_seconds()>(1800 if state.get('phase')=='preparing' else 720):
        state.update(status='failed',error='secret_timeout',updated_at=now());write(path.parent,state)
        for name in ('content.bin','progress.json','result.json'):(path.parent/name).unlink(missing_ok=True)
    return state

def jobs(root,scan_id):
    base=root_for(root,scan_id)
    if not base.exists():return []
    return sorted((read(root,scan_id,path.name) for path in base.iterdir() if re.fullmatch('[a-f0-9]{32}',path.name)),key=lambda item:item['created_at'],reverse=True)

def active(root,scan_id,report_ids=None):
    for job in jobs(root,scan_id):
        if job['status'] in ('queued','running'):
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(job['updated_at'])).total_seconds()
            if age<(1800 if job.get('phase')=='preparing' else 720) and (report_ids is None or any(choice['report_id'] in report_ids for choice in job['choices'])):return True
    return False
