"""Import and browse offline NetExec spider_plus reports attached to an existing host."""
from datetime import datetime, timezone
import ipaddress
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.models.scan import Scan
from app.reports import smb

router = APIRouter(prefix='/api/scans/{scan_id}/smb', tags=['smb'])


def require_scan(scan_id: int, db: Session):
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, 'Скан не найден')
    return scan


def metadata_for(scan, host, account, source, author, observed_at, filename):
    try:
        address = ipaddress.ip_address(host)
        if address not in {ipaddress.ip_address(h.ip) for h in scan.hosts}:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, 'Выберите хост из текущего скана')
    values = {'account': account, 'source': source, 'author': author}
    if any(len(v) > 253 or any(ord(c) < 32 for c in v) for v in values.values()):
        raise HTTPException(422, 'Метаданные SMB: не более 253 символов в поле, без управляющих символов')
    timestamp = None
    if observed_at:
        try:
            dt = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError()
            timestamp = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            raise HTTPException(422, 'Укажите время SMB-проверки с часовым поясом')
    return {'host': str(address), **{k: v.strip() or None for k, v in values.items()},
            'observed_at': timestamp, 'filename': Path((filename or 'report.json').replace('\\', '/')).name[:255]}


def result(operation):
    try:
        return operation()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('')
def reports(scan_id: int, db: Session = Depends(get_db)):
    require_scan(scan_id, db)
    return result(lambda: smb.list_reports(settings.SCANS_DIR, scan_id))


@router.get('/search')
def search_files(scan_id: int, query: str = Query(..., min_length=1, max_length=200),
                 offset: int = Query(0, ge=0, le=50000), db: Session = Depends(get_db)):
    from app.reports.smb_search import search_files as search
    require_scan(scan_id, db)
    return result(lambda: search(settings.SCANS_DIR, scan_id, query, offset))


@router.post('/delete')
def delete_reports(scan_id: int, payload: dict, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
    if scan is None:
        raise HTTPException(404, 'Скан не найден')
    if (scan.smb_job or {}).get('status') in ('queued', 'running'):
        raise HTTPException(409, 'Сначала остановите SMB-проверку')
    if set(payload) != {'report_ids'}:
        raise HTTPException(422, 'Выберите SMB-результаты для удаления')
    from app.secrets.store import active
    if active(settings.SCANS_DIR,scan_id,payload['report_ids']):raise HTTPException(409,'Сначала остановите поиск секретов')
    deleted = result(lambda: smb.delete_reports(settings.SCANS_DIR, scan_id, payload['report_ids']))
    if scan.smb_job:
        scan.smb_job = {**scan.smb_job, 'report_ids': [value for value in scan.smb_job.get('report_ids', []) if value not in set(deleted)]}
    db.commit()
    return {'deleted': deleted}


@router.post('', status_code=201)
def upload(scan_id: int, host: str = Form(...), account: str = Form(''),
           source: str = Form(''), author: str = Form(''), observed_at: str = Form(''),
           file: UploadFile = File(...), db: Session = Depends(get_db)):
    scan = require_scan(scan_id, db)
    metadata = metadata_for(scan, host, account, source, author, observed_at, file.filename)
    content = file.file.read(smb.MAX_BYTES + 1)
    if len(content) > smb.MAX_BYTES:
        raise HTTPException(413, smb.LIMIT)
    return result(lambda: smb.import_report(settings.SCANS_DIR, scan_id, content, metadata))


@router.get('/{report_id}/entries')
def entries(scan_id: int, report_id: str, share: str = Query(..., max_length=256),
            parent: str = Query('', max_length=2048), query: str = Query('', max_length=200),
            offset: int = Query(0, ge=0, le=smb.MAX_ENTRIES), limit: int = Query(100, ge=1, le=200),
            db: Session = Depends(get_db)):
    require_scan(scan_id, db)
    return result(lambda: smb.browse(settings.SCANS_DIR, scan_id, report_id, share, parent, query, offset, limit))


@router.get('/{report_id}/original')
def original(scan_id: int, report_id: str, db: Session = Depends(get_db)):
    require_scan(scan_id, db)
    def download():
        report = smb.get_report(settings.SCANS_DIR, scan_id, report_id)
        path = smb.report_dir(settings.SCANS_DIR, scan_id, report_id) / 'original.json'
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(smb.MISSING)
        return FileResponse(path, media_type='application/json', filename='smb-inventory.json' if report['format'] == 'webscanner-smb' else 'spider_plus.json')
    return result(download)


from uuid import uuid4
from app.schemas.smb import SmbStart


@router.post('/jobs', status_code=202)
def start_job(scan_id: int, payload: SmbStart, db: Session = Depends(get_db)):
    from app.core.smb_jobs import now, scan_smb, secret_store, secret_key
    scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
    if scan is None:
        raise HTTPException(404, 'Скан не найден')
    if scan.proxy_options:
        raise HTTPException(409, 'Активные проверки старых прокси-отчётов отключены. Импортируйте готовый отчёт.')
    if (scan.smb_job or {}).get('status') in ('queued', 'running'):
        raise HTTPException(409, 'SMB-проверка уже выполняется')
    token = uuid4().hex
    browse_token = uuid4().hex
    job = {'id': token, 'status': 'queued', 'created_at': now(), 'updated_at': now(),
           'completed': 0, 'report_ids': [], 'options': payload.public(), 'error': None}
    try:
        if payload.mode == 'credentials':
            secret_store().set(secret_key(token), payload.credential(), ex=600)
        from app.core.smb_actions import SESSION_TTL,session_key
        secret_store().set(session_key(browse_token),json.dumps({'scan_id':scan_id,'report_id':None,
            'hosts':job['options']['targets'],'options':job['options'],'secret':payload.credential()}),ex=SESSION_TTL)
        scan.smb_job = job
        db.commit()
        scan_smb.apply_async(args=[scan_id, token], argsrepr=f'({scan_id}, <SMB job>)')
    except Exception:
        db.rollback()
        scan = db.get(Scan, scan_id)
        if scan and (scan.smb_job or {}).get('id') == token:
            scan.smb_job = {**job, 'status': 'failed', 'error': 'Очередь SMB недоступна'}
            db.commit()
        try:
            from app.core.smb_actions import session_key
            secret_store().delete(secret_key(token),session_key(browse_token))
        except Exception:
            pass
        raise HTTPException(503, 'Очередь SMB недоступна')
    return {**job,'browse_session':{'token':browse_token,'expires_in':900,
        'account':f'{payload.domain}\\{payload.username}'.lstrip('\\') if payload.mode=='credentials' else None,
        'hosts':job['options']['targets'],'report_id':None}}


@router.get('/jobs/current')
def current_job(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
    if scan is None:
        raise HTTPException(404, 'Скан не найден')
    job = dict(scan.smb_job or {})
    if job.get('status') in ('queued', 'running'):
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(job['updated_at'])).total_seconds()
        if elapsed > (660 if job['status'] == 'queued' else 120):
            scan.smb_job = {**job, 'status': 'failed', 'error': 'SMB: worker не отвечает, запустите проверку снова'}
            db.commit()
            job = scan.smb_job
    return job or None


@router.post('/jobs/{token}/cancel')
def cancel_job(scan_id: int, token: str, db: Session = Depends(get_db)):
    from app.core.smb_jobs import now, secret_store, secret_key
    scan = db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
    if scan is None or (scan.smb_job or {}).get('id') != token:
        raise HTTPException(404, 'SMB-задание не найдено')
    job = dict(scan.smb_job)
    if job['status'] in ('queued', 'running'):
        scan.smb_job = {**job, 'status': 'cancelled', 'finished_at': now(), 'updated_at': now()}
        db.commit()
        try:
            secret_store().delete(secret_key(token))
        except Exception:
            pass
    return scan.smb_job


from fastapi import Header
from app.schemas.smb import SmbAction
import json
import re
from starlette.background import BackgroundTask
import shutil


def session_for(scan_id, report_id, authorization, status_only=False):
    from app.core.smb_actions import session_key
    from app.core.smb_jobs import secret_store
    match=re.fullmatch(r'Bearer ([a-f0-9]{32})',authorization or '')
    if not match: raise HTTPException(401,'SMB: подключитесь для просмотра файлов')
    token=match.group(1)
    try: value=secret_store().get(session_key(token))
    except Exception: raise HTTPException(503,'Очередь SMB недоступна')
    session=json.loads(value) if value else None
    if not session or session['scan_id']!=scan_id:
        raise HTTPException(401,'SMB: сессия истекла, подключитесь снова')
    if session.get('revoked') and not status_only:
        raise HTTPException(401,'SMB: учётка отклонена, подключитесь снова')
    report=result(lambda:smb.get_report(settings.SCANS_DIR,scan_id,report_id))
    if session['report_id'] is None:
        if report['host'] not in session['hosts']:raise HTTPException(401,'SMB: подключитесь для просмотра файлов')
    elif session['report_id']!=report_id:
        raise HTTPException(401,'SMB: подключитесь для просмотра файлов')
    return token,{**session,'host':report['host']}


def start_from_session(scan_id,report_id,payload,authorization,db,spider):
    require_scan(scan_id,db)
    _,session=session_for(scan_id,report_id,authorization)
    if set(payload)!={'targets'} or not isinstance(payload['targets'],str):
        raise HTTPException(422,'SMB: укажите IP или подсеть')
    options=dict(session['options'])
    options.update(targets=payload['targets'],spider=spider,depth=3,max_entries=10000)
    if options.get('credential_type')=='kerberos':
        from app.schemas.smb import targets
        try: addresses=targets(payload['targets'])
        except ValueError: raise HTTPException(422,'SMB: укажите IP или подсеть')
        options['server_names']={host:name for host,name in options.get('server_names',{}).items() if host in addresses}
    field={'password':'password','ntlm':'nt_hash','kerberos':'aes_key'}[options.get('credential_type','password')]
    options[field]=session['secret']
    try: request=SmbStart(**options)
    except ValueError: raise HTTPException(422,'SMB: проверьте цели сбора файлов')
    allowed={session['host']} if session.get('report_id') else set(session['hosts'])
    if not set(request.public()['targets']).issubset(allowed):
        raise HTTPException(403,'SMB: цели вне текущего подключения')
    return start_job(scan_id,request,db)


@router.post('/{report_id}/collect',status_code=202)
def collect_files(scan_id:int,report_id:str,payload:dict,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    return start_from_session(scan_id,report_id,payload,authorization,db,True)


@router.post('/{report_id}/check',status_code=202)
def check_access(scan_id:int,report_id:str,payload:dict,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    return start_from_session(scan_id,report_id,payload,authorization,db,False)


@router.post('/{report_id}/session',status_code=201)
def open_session(scan_id:int,report_id:str,payload:SmbStart,db:Session=Depends(get_db)):
    from app.core.smb_actions import SESSION_TTL,session_key,cleanup
    from app.core.smb_jobs import secret_store
    scan=require_scan(scan_id,db)
    if scan.proxy_options: raise HTTPException(409,'Активные проверки старых прокси-отчётов отключены. Импортируйте готовый отчёт.')
    report=result(lambda:smb.get_report(settings.SCANS_DIR,scan_id,report_id))
    options=payload.public()
    if options['targets']!=[report['host']]:raise HTTPException(422,'SMB: адрес должен совпадать с хостом отчёта')
    token=uuid4().hex
    hosts=[report['host']]
    shared=payload.browse_scope=='scan' and payload.credential_type!='kerberos'
    if shared:
        hosts=sorted({report['host'],*(r['host'] for r in result(lambda:smb.list_reports(settings.SCANS_DIR,scan_id)))})
    session={'scan_id':scan_id,'report_id':None if shared else report_id,'host':report['host'],'hosts':hosts,
             'options':options,'secret':payload.credential()}
    try:
        cleanup()
        secret_store().set(session_key(token),json.dumps(session),ex=SESSION_TTL)
    except Exception:raise HTTPException(503,'Очередь SMB недоступна')
    return {'token':token,'expires_in':SESSION_TTL,'hosts':hosts,'report_id':session['report_id'],
            'account':f"{payload.domain}\\{payload.username}".lstrip('\\') if payload.mode=='credentials' else None}


@router.delete('/{report_id}/session',status_code=204)
def close_session(scan_id:int,report_id:str,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from app.core.smb_actions import session_key
    from app.core.smb_jobs import secret_store
    require_scan(scan_id,db)
    token,_=session_for(scan_id,report_id,authorization)
    secret_store().delete(session_key(token))


@router.post('/{report_id}/actions',status_code=202)
def create_action(scan_id:int,report_id:str,payload:SmbAction,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from app.core.smb_actions import ACTION_TTL,action_key,request_key,file_action
    from app.core.smb_jobs import secret_store
    require_scan(scan_id,db)
    token,session=session_for(scan_id,report_id,authorization)
    report=result(lambda:smb.get_report(settings.SCANS_DIR,scan_id,report_id))
    if payload.share not in {s['name'] for s in report['shares']}:
        raise HTTPException(422,'Шара отсутствует в SMB-отчёте')
    action_id=uuid4().hex
    state={'id':action_id,'scan_id':scan_id,'report_id':report_id,'session':token,'status':'queued','action':payload.action}
    try:
        store=secret_store()
        store.set(action_key(action_id),json.dumps(state),ex=ACTION_TTL)
        store.set(request_key(action_id),json.dumps({**payload.model_dump(),'session':token,'host':session['host']}),ex=ACTION_TTL)
        file_action.apply_async(args=[scan_id,action_id],argsrepr=f'({scan_id}, <SMB file action>)')
    except Exception:
        try:
            store.delete(action_key(action_id),request_key(action_id))
        except Exception:pass
        raise HTTPException(503,'Очередь SMB недоступна')
    return {'id':action_id,'status':'queued'}


@router.get('/{report_id}/actions/{action_id}')
def get_action(scan_id:int,report_id:str,action_id:str,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from app.core.smb_actions import action_key
    from app.core.smb_jobs import secret_store
    require_scan(scan_id,db)
    token,_=session_for(scan_id,report_id,authorization,status_only=True)
    if not re.fullmatch('[a-f0-9]{32}',action_id):raise HTTPException(404,'SMB: операция не найдена')
    value=secret_store().get(action_key(action_id))
    state=json.loads(value) if value else None
    if not state or state['scan_id']!=scan_id or state['report_id']!=report_id or state['session']!=token:
        raise HTTPException(404,'SMB: операция не найдена')
    return {key:value for key,value in state.items() if key not in ('session','scan_id','report_id')}


@router.get('/{report_id}/actions/{action_id}/download')
def download_action(scan_id:int,report_id:str,action_id:str,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from app.core.smb_actions import action_directory
    state=get_action(scan_id,report_id,action_id,authorization,db)
    if state['status']!='completed' or state['action']!='download':raise HTTPException(409,'SMB: скачивание ещё не готово')
    directory=action_directory(action_id)
    path=directory/'download.bin'
    if not path.is_file() or path.is_symlink():raise HTTPException(404,'SMB: файл уже скачан или истёк срок хранения')
    filename=state['result']['filename']
    return FileResponse(path,media_type='application/octet-stream',filename=filename,
        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'},
        background=BackgroundTask(shutil.rmtree,directory,ignore_errors=True))


@router.delete('/sessions/current',status_code=204)
def disconnect_session(scan_id:int,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from app.core.smb_actions import session_key
    from app.core.smb_jobs import secret_store
    require_scan(scan_id,db)
    match=re.fullmatch(r'Bearer ([a-f0-9]{32})',authorization or '')
    if not match:raise HTTPException(401,'SMB: подключитесь для просмотра файлов')
    store=secret_store();value=store.get(session_key(match.group(1)))
    if value and json.loads(value)['scan_id']==scan_id:store.delete(session_key(match.group(1)))
