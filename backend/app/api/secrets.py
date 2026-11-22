"""Explicit, scoped secret scans using saved SMB file catalogs."""
import json
import shutil
from uuid import uuid4
from fastapi import APIRouter,Depends,Header,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,SecretStr
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.config import settings
from app.models.scan import Scan
from app.api.smb import require_scan,session_for,result
from app.reports import smb
from app.secrets import store
from app.secrets.engine import available
from app.schemas.smb import SmbStart,targets

router=APIRouter(prefix='/api/scans/{scan_id}/secrets',tags=['secrets'])
workspace_router=APIRouter(prefix='/api/secrets',tags=['secrets'])

@workspace_router.post('/workspaces',status_code=201)
def create_workspace(payload:dict,db:Session=Depends(get_db)):
    from app.schemas.smb import targets
    if set(payload)!={'targets'} or not isinstance(payload['targets'],str) or len(payload['targets'])>4000:raise HTTPException(422,'SMB: укажите IP или подсеть')
    try:targets(payload['targets'])
    except ValueError:raise HTTPException(422,'SMB: укажите IP или подсеть')
    scope=payload['targets'].strip()
    scan=Scan(target=scope[:255],scope_targets=scope,scope_ports='445',scan_type='smb_workspace',status='completed',stage='completed',progress=100,comment='Самостоятельный поиск секретов',project_id=None,network_part_id=None)
    db.add(scan);db.commit();db.refresh(scan)
    return {'id':scan.id,'targets':scope}

class WorkflowStart(BaseModel):
    model_config=ConfigDict(extra='forbid')
    options:SmbStart|None=None
    source:str=Field("smb",pattern="^(smb|ftp|local)$")
    locations:list[str]=Field(default_factory=list,max_length=256)
    ftp_username:str=Field("",max_length=253)
    ftp_password:SecretStr=Field(default_factory=lambda:SecretStr(""),max_length=1024)
    ftp_tls:bool=False
    scan_id:int|None=Field(None,ge=1)
    use_session:bool=False
    share_names:list[str]=Field(default_factory=list,max_length=32)
    exclude_shares:list[str]=Field(default_factory=lambda:["IPC$"],max_length=32)
    fast:bool=True
    max_depth:int|None=Field(None,ge=0,le=100)
    time_limit:int=Field(1800,ge=60,le=14400)
    max_file_mb:int=Field(10,ge=1,le=1024)
    read_mb:int=Field(2,ge=1,le=64)
    total_read_mb:int|None=Field(None,ge=1,le=102400)
    max_reads:int|None=Field(None,ge=1,le=1000000)
    threads:int=Field(60,ge=3,le=60)
    exclude_paths:list[str]=Field(default_factory=list,max_length=100)

@workspace_router.post('/search',status_code=202)
def start_workflow(payload:WorkflowStart,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    if not available():raise HTTPException(503,'Поиск секретов: движок не установлен, пересоберите backend и worker')
    from app.core.smb_jobs import secret_store,now
    from app.core.smb_actions import session_key
    from app.core.secret_jobs import request_key
    from app.core.secret_workflow import native_search,WORKFLOW_TTL
    from app.secrets.sources import prepare
    try:request=prepare(payload,getattr(settings,"SECRET_LOCAL_ROOT","/data/secret-inputs"))
    except ValueError as exc:raise HTTPException(422,str(exc))
    if payload.use_session:
        if not payload.scan_id:raise HTTPException(401,'Подключение истекло. Введите учётку на этой странице.')
        import re
        match=re.fullmatch(r'Bearer ([a-f0-9]{32})',authorization or '')
        raw=secret_store().get(session_key(match.group(1))) if match else None
        session=json.loads(raw) if raw else None
        if not session or session.get('revoked') or session['scan_id']!=payload.scan_id:raise HTTPException(401,'Подключение истекло. Введите учётку на этой странице.')
        if session.get('report_id'):raise HTTPException(403,'Для поиска по всем шарам введите учётку заново.')
        allowed=set(session.get('hosts',[]))
        if not set(request.public()['targets']).issubset(allowed):raise HTTPException(403,'Для новых целей введите учётку заново.')
        options={**session['options'],'targets':request.targets,'spider':True,'depth':request.depth,
                 'max_entries':request.max_entries,'include_admin':request.include_admin}
        field={'password':'password','ntlm':'nt_hash','kerberos':'aes_key'}[options.get('credential_type','password')]
        options[field]=session['secret']
        if options.get('credential_type')=='kerberos':options['server_names']={host:name for host,name in options.get('server_names',{}).items() if host in request.public()['targets']}
        try:request=SmbStart(**options)
        except ValueError:raise HTTPException(422,"Проверьте параметры учётки")
    request.spider=True
    if any(not name or len(name)>256 or any(ord(char)<32 or char in '/\\' for char in name) for name in [*payload.share_names,*payload.exclude_shares]):raise HTTPException(422,'Некорректное имя шары')
    if payload.read_mb>payload.max_file_mb:raise HTTPException(422,'Объём чтения не должен превышать максимальный размер файла')
    if any(not value or len(value)>2048 or any(ord(char)<32 for char in value) for value in payload.exclude_paths):raise HTTPException(422,'Некорректная маска исключения папок')
    if payload.scan_id:
        scan=db.query(Scan).filter(Scan.id==payload.scan_id).with_for_update().first()
        if not scan:raise HTTPException(404,'Скан не найден')
        if scan.proxy_options:raise HTTPException(409,'Активные проверки старых прокси-отчётов отключены. Импортируйте готовый отчёт.')
        if scan.status in ('queued','running') or (scan.smb_job or {}).get('status') in ('queued','running') or store.active(settings.SCANS_DIR,scan.id):raise HTTPException(409,'Дождитесь завершения текущей проверки')
    else:
        scope=request.targets.strip()
        scan=Scan(target=scope[:255],scope_targets=scope,scope_ports='445' if payload.source=='smb' else '21' if payload.source=='ftp' else '',scan_type='smb_workspace',status='completed',stage='completed',progress=100,comment='Самостоятельный поиск секретов')
        db.add(scan);db.flush()
    token=uuid4().hex;private_token=uuid4().hex;browser_token=uuid4().hex
    options=request.public();account=(request.domain+'\\'+request.username).strip('\\') or None
    state={'id':token,'scan_id':scan.id,'status':'queued','phase':'discovering','engine':'snaffler-ng',
           'created_at':now(),'updated_at':now(),'account':account,'source':payload.source,'locations':payload.locations,'ftp_tls':payload.ftp_tls,'targets':request.targets,'choices':[],
           'fast':payload.fast,'max_depth':payload.max_depth,'time_limit':payload.time_limit,
           'limits':{key:getattr(payload,key) for key in ('max_file_mb','read_mb','total_read_mb','max_reads','threads','exclude_paths')},
           'share_names':payload.share_names,'exclude_shares':payload.exclude_shares,'findings':[],'stats':{},'error':None}
    session={'scan_id':scan.id,'report_id':None,'hosts':options['targets'],'options':options,'secret':request.credential()}
    path=store.directory(settings.SCANS_DIR,scan.id,token);redis=secret_store()
    try:
        store.write(path,state)
        redis.set(session_key(private_token),json.dumps(session),ex=WORKFLOW_TTL)
        redis.set(session_key(browser_token),json.dumps(session),ex=900)
        redis.set(request_key(token),json.dumps({'session':private_token,'owned':True}),ex=600)
        db.commit()
        native_search.apply_async(args=[scan.id,token],argsrepr=f'({scan.id}, <secret search>)')
    except Exception:
        db.rollback()
        state.update(status='failed',error='secret_queue_unavailable',updated_at=now());store.write(path,state)
        try:redis.delete(session_key(private_token),session_key(browser_token),request_key(token))
        except Exception:pass
        raise HTTPException(503,'Очередь поиска секретов недоступна')
    return {'job':state,'session':{'token':browser_token,'account':account,'expires_in':900,'hosts':options['targets'],'report_id':None}}

@workspace_router.get('/history')
def global_history(db:Session=Depends(get_db)):
    result=[]
    for scan in db.query(Scan).order_by(Scan.id.desc()).limit(200).all():
        for job in store.jobs(settings.SCANS_DIR,scan.id):
            result.append({key:value for key,value in job.items() if key!='findings'}|{'finding_count':job.get('finding_count',len(job.get('findings',[]))),'targets':job.get('targets') or scan.scope_targets or scan.target})
    return sorted(result,key=lambda job:job['created_at'],reverse=True)[:100]

class Choice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    report_id:str=Field(pattern='^[a-f0-9]{32}$')
    share:str=Field(min_length=1,max_length=256)
class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    choices:list[Choice]=Field(min_length=1,max_length=32)

@router.get('')
def list_jobs(scan_id:int,db:Session=Depends(get_db)):
    require_scan(scan_id,db)
    jobs=result(lambda:store.jobs(settings.SCANS_DIR,scan_id))
    return [{key:value for key,value in job.items() if key!='findings'}|{'finding_count':job.get('finding_count',len(job.get('findings',[])))} for job in jobs]

@router.get('/{token}')
def get_job(scan_id:int,token:str,db:Session=Depends(get_db)):
    scan=require_scan(scan_id,db)
    state=result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    return state

@router.post('',status_code=202)
def start(scan_id:int,payload:Start,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    scan=db.query(Scan).filter(Scan.id==scan_id).with_for_update().first()
    if not scan:raise HTTPException(404,'Скан не найден')
    if scan.proxy_options:raise HTTPException(409,'Активные проверки старых прокси-отчётов отключены. Импортируйте готовый отчёт.')
    if not available():raise HTTPException(503,'Поиск секретов: движок не установлен, пересоберите backend и worker')
    if store.active(settings.SCANS_DIR,scan_id):raise HTTPException(409,'Поиск секретов уже выполняется')
    seen=set();has_files=False;identity=None;session_token=None
    choices=[]
    for choice in payload.choices:
        key=(choice.report_id,choice.share)
        if key in seen:continue
        seen.add(key)
        session_token,identity=session_for(scan_id,choice.report_id,authorization)
        report=result(lambda:smb.get_report(settings.SCANS_DIR,scan_id,choice.report_id))
        if choice.share not in {item['name'] for item in report['shares']}:raise HTTPException(422,'Шара отсутствует в SMB-отчёте')
        with smb.catalog(settings.SCANS_DIR,scan_id,choice.report_id) as catalog:
            has_files=has_files or bool(catalog.execute('SELECT 1 FROM entries WHERE share=? AND kind=? LIMIT 1',[choice.share,'file']).fetchone())
        choices.append(choice.model_dump())
    if not has_files:raise HTTPException(422,'Сначала соберите список файлов выбранных шар в SMB')
    from app.core.secret_jobs import scan_secrets,request_key
    from app.core.smb_jobs import secret_store
    token=uuid4().hex
    account=(identity['options'].get('domain','')+'\\'+identity['options'].get('username','')).strip('\\') or None
    state={'id':token,'scan_id':scan_id,'status':'queued','created_at':store.now(),'updated_at':store.now(),
           'account':account,'choices':choices,'findings':[],'stats':{},'error':None}
    path=store.directory(settings.SCANS_DIR,scan_id,token);store.write(path,state)
    try:
        secret_store().set(request_key(token),json.dumps({'session':session_token}),ex=600)
        db.commit()
        scan_secrets.apply_async(args=[scan_id,token],argsrepr=f'({scan_id}, <secret scan>)')
    except Exception:
        db.rollback();state.update(status='failed',error='secret_queue_unavailable');store.write(path,state)
        try:secret_store().delete(request_key(token))
        except Exception:pass
        raise HTTPException(503,'Очередь поиска секретов недоступна')
    return state

@router.post('/{token}/cancel')
def cancel(scan_id:int,token:str,db:Session=Depends(get_db)):
    require_scan(scan_id,db);state=result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    if state['status'] in ('queued','running'):
        (store.directory(settings.SCANS_DIR,scan_id,token)/'cancel').touch(mode=0o600)
        if state.get('engine')=='snaffler-ng':
            from app.core.secret_workflow import cleanup_request
            cleanup_request(scan_id,token)
        state['cancel_requested']=True
        if state['status']=='queued':state['status']='cancelled'
        state['updated_at']=store.now();store.write(store.directory(settings.SCANS_DIR,scan_id,token),state)
    return state

@router.delete('/{token}',status_code=204)
def delete(scan_id:int,token:str,db:Session=Depends(get_db)):
    require_scan(scan_id,db);state=result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    if state['status'] in ('queued','running'):raise HTTPException(409,'Сначала остановите поиск секретов')
    shutil.rmtree(store.directory(settings.SCANS_DIR,scan_id,token))


@router.get('/{token}/findings')
def findings(scan_id:int,token:str,query:str=Query('',max_length=200),offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),db:Session=Depends(get_db)):
    require_scan(scan_id,db)
    state=result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    if state.get('engine')=='snaffler-ng':
        from app.secrets.native import read_findings
        return result(lambda:read_findings(store.directory(settings.SCANS_DIR,scan_id,token),query,offset,limit))
    items=[item for item in state.get('findings',[]) if query.casefold() in (item.get('path','')+' '+item.get('rule','')).casefold()]
    return {'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit}


def native_session(scan_id,authorization):
    import re
    from app.core.smb_actions import session_key
    from app.core.smb_jobs import secret_store
    match=re.fullmatch(r'Bearer ([a-f0-9]{32})',authorization or '')
    raw=secret_store().get(session_key(match.group(1))) if match else None
    session=json.loads(raw) if raw else None
    if not session or session.get('revoked') or session['scan_id']!=scan_id:raise HTTPException(401,'Подключение истекло. Введите учётку на этой странице.')
    return match.group(1),session


class FindingAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    finding_id:str=Field(pattern='^[a-f0-9]{40}$')
    action:str=Field(pattern='^(preview|download)$')


@router.post('/{token}/files',status_code=202)
def finding_action(scan_id:int,token:str,payload:FindingAction,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from app.secrets.native import finding
    from app.schemas.smb import SmbAction
    from app.core.smb_actions import ACTION_TTL,action_key,request_key,file_action
    from app.core.smb_jobs import secret_store
    require_scan(scan_id,db);result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    session_token,session=native_session(scan_id,authorization)
    item=result(lambda:finding(store.directory(settings.SCANS_DIR,scan_id,token),payload.finding_id))
    source=session['options'].get('source','smb')
    report_id=session.get('report_id')
    if source!='smb':
        from app.secrets.sources import validate_file
        if source!=item.get('source'):raise HTTPException(403,'Цель вне области подключения')
        location=item['location'].split('→',1)[0]
        try:validate_file(session['options'],location)
        except (ValueError,OSError):raise HTTPException(403,'Цель вне области подключения')
        action_data={'action':payload.action,'location':location,'host':item['host']}
    else:
        if item['host'] not in session['hosts']:raise HTTPException(403,'Цель вне области подключения')
        if report_id:
            report=result(lambda:smb.get_report(settings.SCANS_DIR,scan_id,report_id))
            if report['host']!=item['host'] or item['share'] not in {share['name'] for share in report['shares']}:raise HTTPException(403,'Цель вне области подключения')
        try:action=SmbAction(action=payload.action,share=item['share'],path=item['path'].split('→',1)[0])
        except ValueError:raise HTTPException(422,'Некорректный путь файла')
        action_data={**action.model_dump(),'host':item['host']}
    action_id=uuid4().hex
    state={'id':action_id,'scan_id':scan_id,'secret_job':token,'source':source,'report_id':report_id,'session':session_token,'status':'queued','action':payload.action}
    redis=secret_store()
    try:
        redis.set(action_key(action_id),json.dumps(state),ex=ACTION_TTL)
        redis.set(request_key(action_id),json.dumps({**action_data,'session':session_token}),ex=ACTION_TTL)
        file_action.apply_async(args=[scan_id,action_id],argsrepr=f'({scan_id}, <secret file action>)')
    except Exception:
        redis.delete(action_key(action_id),request_key(action_id))
        raise HTTPException(503,'Очередь SMB недоступна')
    return {'id':action_id,'status':'queued'}


@router.get('/{token}/files/{action_id}')
def finding_action_status(scan_id:int,token:str,action_id:str,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    import re
    from app.core.smb_actions import action_key
    from app.core.smb_jobs import secret_store
    require_scan(scan_id,db);result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    session_token,_=native_session(scan_id,authorization)
    if not re.fullmatch('[a-f0-9]{32}',action_id):raise HTTPException(404,'SMB: операция не найдена')
    raw=secret_store().get(action_key(action_id));state=json.loads(raw) if raw else None
    if not state or state.get('scan_id')!=scan_id or state.get('secret_job')!=token or state.get('session')!=session_token:raise HTTPException(404,'SMB: операция не найдена')
    return {key:value for key,value in state.items() if key not in ('session','scan_id','report_id','secret_job')}


@router.get('/{token}/files/{action_id}/download')
def finding_download(scan_id:int,token:str,action_id:str,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from app.core.smb_actions import action_directory
    state=finding_action_status(scan_id,token,action_id,authorization,db)
    if state['status']!='completed' or state['action']!='download':raise HTTPException(409,'SMB: скачивание ещё не готово')
    directory=action_directory(action_id);path=directory/'download.bin'
    if not path.is_file() or path.is_symlink():raise HTTPException(404,'SMB: файл уже скачан или истёк срок хранения')
    return FileResponse(path,media_type='application/octet-stream',filename=state['result']['filename'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'},background=BackgroundTask(shutil.rmtree,directory,ignore_errors=True))


@router.post('/connection',status_code=201)
def reconnect(scan_id:int,payload:SmbStart,db:Session=Depends(get_db)):
    from app.core.smb_actions import session_key
    from app.core.smb_jobs import secret_store
    scan=require_scan(scan_id,db)
    if scan.proxy_options:raise HTTPException(409,'Активные проверки старых прокси-отчётов отключены. Импортируйте готовый отчёт.')
    allowed=set(targets(scan.scope_targets or scan.target));options=payload.public()
    if not set(options['targets']).issubset(allowed):raise HTTPException(403,'Цель вне области подключения')
    token=uuid4().hex
    secret_store().set(session_key(token),json.dumps({'scan_id':scan_id,'report_id':None,'hosts':options['targets'],'options':options,'secret':payload.credential()}),ex=900)
    return {'token':token,'expires_in':900,'hosts':options['targets'],'report_id':None,'account':(payload.domain+'\\'+payload.username).strip('\\') or None}


@router.post('/{token}/connection',status_code=201)
def reconnect_source(scan_id:int,token:str,payload:WorkflowStart,db:Session=Depends(get_db)):
    from app.secrets.sources import prepare,ftp_in_scope,local_relative,local_directory
    from app.core.smb_actions import session_key
    from app.core.smb_jobs import secret_store
    scan=require_scan(scan_id,db);job=result(lambda:store.read(settings.SCANS_DIR,scan_id,token))
    if scan.proxy_options or payload.source!=job.get('source','smb'):raise HTTPException(403,'Цель вне области подключения')
    try:
        request=prepare(payload,getattr(settings,'SECRET_LOCAL_ROOT','/data/secret-inputs'));options=request.public()
        if payload.source=='ftp':
            original={'targets':job['targets'].splitlines()}
            for location in options['targets']:ftp_in_scope(original,location)
        elif payload.source=='local':
            roots=[local_directory(getattr(settings,'SECRET_LOCAL_ROOT','/data/secret-inputs'),value) for value in job['locations']]
            for location in options['local_paths']:local_relative({'local_paths':roots},location)
        elif not set(options['targets']).issubset(set(targets(job.get('targets') or scan.scope_targets or scan.target))):raise ValueError('source_outside_scope')
    except (ValueError,OSError):raise HTTPException(422,'Проверьте источник и область подключения')
    token=uuid4().hex
    secret_store().set(session_key(token),json.dumps({'scan_id':scan_id,'report_id':None,'hosts':options['targets'],'options':options,'secret':request.credential()}),ex=900)
    return {'token':token,'expires_in':900,'hosts':options['targets'],'report_id':None,'account':(request.domain+'\\'+request.username).strip('\\') or None}
