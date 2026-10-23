"""SQLite/API fixture for real enqueue/retry functions, with Celery mocked.
No production config, Docker, multipart parser or actual network scan is needed.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import ast
import asyncio
import functools
from types import ModuleType, SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI, Depends, HTTPException
import httpx
engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
Db=sessionmaker(bind=engine)
module=ModuleType('app.core.db');module.Base=declarative_base();module.engine=engine;module.SessionLocal=Db
async def get_db():
    with Db() as db:yield db
module.get_db=get_db;sys.modules['app.core.db']=module
from app.models.scan import Project, NetworkPart, Scan, ScanStatus, Host, Port
from app.schemas.scan import ScanCreate, ScanResponse, TeamMetadata
from app.core.catalog import resolve_context
from app.core.migrations import migrate
module.Base.metadata.create_all(engine);migrate(engine);migrate(engine)
source=Path(__file__).resolve().parents[1]/'backend/app/api/scans.py'
nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('create_scan','enqueue_scan','retry_scan')]
for node in nodes:node.decorator_list=[]
run_scan=SimpleNamespace(delay=Mock())
namespace=dict(globals())
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(source),'exec'),namespace)
app=FastAPI()
# Async adapters avoid the sandbox's unsupported cross-thread test portal.
for path,name in [('/api/scans','create_scan'),('/api/scans/{scan_id}/retry','retry_scan')]:
    original=namespace[name]
    @functools.wraps(original)
    async def adapter(_call=original,**kwargs):return _call(**kwargs)
    app.add_api_route(path,adapter,methods=['POST'],response_model=ScanResponse,status_code=201)
async def check():
    with Db() as db:
        db.add(Project(id=1,name='Lab',name_key='lab'));db.add(NetworkPart(id=2,project_id=1,name='Office',name_key='office'));db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        created=await client.post('/api/scans',json={'target':'10.0.0.0/24','project_id':1,'network_part_id':2,'scan_type':'custom','ports':'22,445','source_host':'10.0.0.1','exclude_ips':'10.0.0.9','exclude_ports':'23'})
        assert created.status_code==201,created.text
        original=created.json();original_id=original['id']
        assert (await client.post(f'/api/scans/{original_id}/retry',json={})).status_code==409
        with Db() as db:
            scan=db.get(Scan,original_id);scan.status=ScanStatus.FAILED;scan.stage='failed';scan.error_message='Tunnel not switched';scan.scope_confirmed=True;db.add(Host(scan_id=original_id,ip='10.0.0.5'));db.commit()
        run_scan.delay.reset_mock()
        result=await client.post(f'/api/scans/{original_id}/retry',json={});assert result.status_code==201,result.text
        new=result.json();assert new['id']!=original_id and new['retry_of_id']==original_id
        for name in ('target','project_id','network_part_id','ports','source_host','exclude_ips','exclude_ports'):assert new[name]==original[name],name
        assert new['observed_at'] is None and new['scope_confirmed'] is False
        run_scan.delay.assert_called_once()
        assert run_scan.delay.call_args.kwargs['exclusions']=={'exclude_ips':'10.0.0.9','exclude_ports':'23'}
        with Db() as db:
            old=db.get(Scan,original_id);assert old.status==ScanStatus.FAILED and old.error_message=='Tunnel not switched';assert db.query(Host).count()==1
        assert (await client.post(f'/api/scans/{original_id}/retry',json={'target':'invalid target'})).status_code==422
        assert (await client.post(f'/api/scans/{original_id}/retry',json={'project_id':999})).status_code==422
        with Db() as db:
            imported=Scan(target='report.xml',scan_type='import-nmap',status=ScanStatus.COMPLETED);db.add(imported);db.commit();import_id=imported.id
        assert (await client.post(f'/api/scans/{import_id}/retry',json={})).status_code==409
        run_scan.delay.side_effect=RuntimeError('queue offline')
        response=await client.post(f'/api/scans/{original_id}/retry',json={});assert response.status_code==503
        with Db() as db:
            failed=db.query(Scan).order_by(Scan.id.desc()).first();assert failed.retry_of_id==original_id and failed.status==ScanStatus.FAILED
        print('PASS: enqueue, terminal-only retry, context/exclusion preservation, new evidence timestamps, original history, invalid input, imports and queue failure')
asyncio.run(check())
