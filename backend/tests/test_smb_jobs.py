"""SQLite queue lifecycle fixture: no real broker, credentials or network traffic."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
try:
    import pydantic_settings
except ModuleNotFoundError:
    config = ModuleType('app.core.config')
    config.settings = SimpleNamespace(DATABASE_URL='postgresql://scanner:scanner@localhost/scanner')
    sys.modules.setdefault('app.core.config', config)
from app.core.db import Base
from app.core.process import ScanCancelled
from app.models.scan import Scan
from app.reports import smb
from app.schemas.smb import SmbStart, SmbAction


def load_functions(relative, namespace):
    source = Path(__file__).parents[1] / relative
    nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef)]
    for node in nodes: node.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(source),'exec'),namespace)
    return namespace


class SmbJobFixture:
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)
        self.temp = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(SCANS_DIR=self.temp.name)
        with self.session() as db:
            scan = Scan(target='192.0.2.0/24',status='completed'); db.add(scan); db.commit(); self.scan_id=scan.id
        self.secret = Mock(); self.secret.getdel.return_value = b'private-secret'
        self.probe = Mock(return_value={'observed_at':'2026-11-06T12:00:00Z','server':{},'shares':[],
            'entries':[],'error':None,'status':'completed','partial':False,'limits':[]})
        self.jobs = load_functions('app/core/smb_jobs.py',dict(datetime=datetime,timezone=timezone,
            SessionLocal=self.session,Scan=Scan,settings=self.settings,ScanCancelled=ScanCancelled,
            json=json,store_report=smb.store_report,time=time))
        self.jobs.update(secret_store=lambda:self.secret,probe_process=self.probe,discover_targets=lambda hosts,check:hosts)
        self.broker=Mock()
        self.api = load_functions('app/api/smb.py',dict(datetime=datetime,timezone=timezone,uuid4=uuid4,
            Scan=Scan,Session=Session,Depends=Depends,get_db=lambda:None,SmbStart=SmbStart,
            File=File,Form=Form,Header=Header,SmbAction=SmbAction,Query=Query,UploadFile=UploadFile,HTTPException=HTTPException,
            FileResponse=FileResponse,settings=self.settings,smb=smb,json=json))
        module=ModuleType('app.core.smb_jobs')
        module.now=self.jobs['now'];module.secret_store=lambda:self.secret
        module.secret_key=self.jobs['secret_key'];module.scan_smb=self.broker
        actions=ModuleType('app.core.smb_actions');actions.SESSION_TTL=900;actions.session_key=lambda token:f'webscanner:smb:session:{token}'
        self.modules=patch.dict(sys.modules,{'app.core.smb_jobs':module,'app.core.smb_actions':actions});self.modules.start()

    def tearDown(self):
        self.modules.stop();self.engine.dispose();self.temp.cleanup()

    def start(self, **kwargs):
        with self.session() as db:
            return self.api['start_job'](self.scan_id,SmbStart(targets='192.0.2.1,192.0.2.2',**kwargs),db)

    def state(self):
        with self.session() as db: return db.get(Scan,self.scan_id).smb_job



class SmbJobsTests(SmbJobFixture, unittest.TestCase):
    def test_queue_secret_is_not_in_broker_or_database_and_duplicate_delivery_noop(self):
        job=self.start(mode='credentials',username='reader',password='private-secret')
        self.secret.set.assert_any_call(self.jobs['secret_key'](job['id']),'private-secret',ex=600)
        self.assertNotIn('private-secret',json.dumps(job))
        self.assertNotIn('private-secret',str(self.broker.apply_async.call_args))
        self.jobs['run_job'](self.scan_id,job['id'])
        self.assertEqual(self.state()['status'],'completed')
        self.assertEqual(self.probe.call_count,2)
        self.assertEqual(len(smb.list_reports(self.temp.name,self.scan_id)),2)
        self.secret.getdel.assert_called_once()
        self.jobs['run_job'](self.scan_id,job['id'])
        self.assertEqual(self.probe.call_count,2)

    def test_nt_hash_enqueue_cancel_and_stale_worker_cannot_publish(self):
        hashed='1'*32
        job=self.start(mode='credentials',username='reader',credential_type='ntlm',nt_hash=hashed)
        self.assertNotIn(hashed,json.dumps(job))
        self.secret.set.assert_any_call(self.jobs['secret_key'](job['id']),hashed,ex=600)
        with self.session() as db:
            cancelled=self.api['cancel_job'](self.scan_id,job['id'],db)
        self.assertEqual(cancelled['status'],'cancelled')
        self.jobs['run_job'](self.scan_id,job['id'])
        self.probe.assert_not_called()
        self.assertEqual(smb.list_reports(self.temp.name,self.scan_id),[])

    def test_bad_credentials_stop_remaining_targets_and_expired_secret_fails(self):
        self.probe.return_value={**self.probe.return_value,'status':'login_failed','error':'authentication_failed'}
        job=self.start(mode='credentials',username='reader',password='private-secret')
        self.jobs['run_job'](self.scan_id,job['id'])
        self.assertEqual(self.probe.call_count,1)
        self.assertEqual(self.state()['status'],'partial')
        self.secret.getdel.return_value=None
        job=self.start(mode='credentials',username='reader',password='private-secret')
        self.jobs['run_job'](self.scan_id,job['id'])
        self.assertEqual(self.state()['status'],'failed')
        self.assertEqual(self.probe.call_count,1)

    def test_queue_failure_cleans_secret_and_allows_retry(self):
        self.broker.apply_async.side_effect=RuntimeError('private-secret')
        with self.assertRaises(HTTPException) as raised:
            self.start(mode='credentials',username='reader',password='private-secret')
        self.assertEqual(raised.exception.status_code,503)
        self.assertNotIn('private-secret',raised.exception.detail)
        self.assertEqual(self.state()['status'],'failed')
        self.secret.delete.assert_called()

    def test_cancel_during_probe_prevents_publication(self):
        job=self.start()
        def cancel(*args):
            with self.session() as db:self.api['cancel_job'](self.scan_id,job['id'],db)
            return self.probe.return_value
        self.probe.side_effect=cancel
        self.jobs['run_job'](self.scan_id,job['id'])
        self.assertEqual(self.state()['status'],'cancelled')
        self.assertEqual(smb.list_reports(self.temp.name,self.scan_id),[])

    def test_running_delivery_does_not_destroy_credentials_of_claimed_job(self):
        job = self.start(mode='credentials',username='reader',password='private-secret')
        with self.session() as db:
            scan = db.get(Scan,self.scan_id)
            scan.smb_job = {**scan.smb_job,'status':'running'}; db.commit()
        self.jobs['run_job'](self.scan_id,job['id'])
        self.secret.delete.assert_not_called()
        self.probe.assert_not_called()

    def test_kerberos_key_is_one_time_and_not_in_public_job(self):
        key = 'b' * 64
        job = self.start(mode='credentials',credential_type='kerberos',username='reader',domain='lab.example',
                         aes_key=key,kdc_host='192.0.2.10',server_names={'192.0.2.1':'fs01.lab.example','192.0.2.2':'fs02.lab.example'})
        self.secret.set.assert_any_call(self.jobs['secret_key'](job['id']),key,ex=600)
        self.assertNotIn(key,json.dumps(job))
        self.assertNotIn(key,str(self.broker.apply_async.call_args))

    def test_unreachable_targets_count_as_checked_without_empty_reports(self):
        self.jobs['discover_targets'] = lambda hosts,check: hosts[:1]
        job = self.start()
        self.jobs['run_job'](self.scan_id,job['id'])
        self.assertEqual(self.probe.call_count,1)
        self.assertEqual(self.state()['status'],'completed')
        self.assertEqual(self.state()['completed'],2)
        self.assertEqual(self.state()['skipped'],1)
        self.assertEqual(len(smb.list_reports(self.temp.name,self.scan_id)),1)
