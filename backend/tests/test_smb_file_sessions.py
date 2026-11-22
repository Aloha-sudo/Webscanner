import json
import re
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock,patch
from fastapi import HTTPException
from app.schemas.smb import SmbAction,SmbStart
import unittest
import test_smb_jobs as jobs_fixture
from test_smb import file_info
from app.reports import smb


class Store:
    def __init__(self):self.data={}
    def set(self,key,value,ex=None):self.data[key]=value
    def get(self,key):return self.data.get(key)
    def getdel(self,key):return self.data.pop(key,None)
    def delete(self,*keys):
        for key in keys:self.data.pop(key,None)


class SmbFileSessionTests(jobs_fixture.SmbJobFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.store=Store()
        self.file_task=Mock()
        actions=ModuleType('app.core.smb_actions')
        actions.SESSION_TTL=900;actions.ACTION_TTL=600
        actions.session_key=lambda token:f'session:{token}'
        actions.action_key=lambda token:f'action:{token}'
        actions.request_key=lambda token:f'request:{token}'
        actions.file_action=self.file_task;actions.cleanup=lambda:None
        actions.action_directory=lambda token:Path(self.temp.name)/'.smb-actions'/token
        self.actions=actions
        module=ModuleType('app.core.smb_jobs');module.now=self.jobs['now'];module.secret_store=lambda:self.store
        module.secret_key=self.jobs['secret_key'];module.scan_smb=self.broker
        self.file_modules=patch.dict('sys.modules',{'app.core.smb_actions':actions,'app.core.smb_jobs':module});self.file_modules.start()
        self.api.update(json=json,re=re)
        meta={'host':'192.0.2.1','account':'LAB\\reader','source':None,'author':None,'observed_at':None,'filename':'report.json'}
        self.report=smb.import_report(self.temp.name,self.scan_id,json.dumps({'Docs':{'hello.txt':file_info()}}).encode(),meta)

    def tearDown(self):self.file_modules.stop();super().tearDown()

    def test_session_action_scope_and_public_response_do_not_expose_credentials(self):
        with self.session() as db:
            session=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',mode='credentials',username='reader',password='private-secret'),db)
            self.assertNotIn('private-secret',json.dumps(session))
            authorization='Bearer '+session['token']
            action=self.api['create_action'](self.scan_id,self.report['id'],SmbAction(action='list',share='Docs'),authorization,db)
            self.assertEqual(action['status'],'queued')
            self.assertNotIn('private-secret',str(self.file_task.apply_async.call_args))
            status=self.api['get_action'](self.scan_id,self.report['id'],action['id'],authorization,db)
            self.assertNotIn('session',status)
            with self.assertRaises(HTTPException) as error:
                self.api['session_for'](999,self.report['id'],authorization)
            self.assertEqual(error.exception.status_code,401)
            with self.assertRaises(HTTPException):
                self.api['create_action'](self.scan_id,self.report['id'],SmbAction(action='list',share='Other'),authorization,db)
            self.api['disconnect_session'](self.scan_id,authorization,db)
            with self.assertRaises(HTTPException):self.api['session_for'](self.scan_id,self.report['id'],authorization)

    def test_session_created_by_scan_is_not_persisted_in_database(self):
        job=self.start(mode='credentials',username='reader',password='private-secret')
        self.assertIn('browse_session',job)
        self.assertNotIn('browse_session',self.state())
        self.assertNotIn('private-secret',json.dumps(self.state()))
        token=job['browse_session']['token']
        session=json.loads(self.store.get(self.actions.session_key(token)))
        self.assertEqual(session['hosts'],['192.0.2.1','192.0.2.2'])
        self.assertIsNone(session['report_id'])
        self.assertEqual(self.api['session_for'](self.scan_id,self.report['id'],'Bearer '+token)[1]['host'],'192.0.2.1')
        session['hosts']=['192.0.2.99'];self.store.set(self.actions.session_key(token),json.dumps(session))
        with self.assertRaises(HTTPException):self.api['session_for'](self.scan_id,self.report['id'],'Bearer '+token)

    def test_revoked_session_can_read_failure_but_not_start_another_operation(self):
        with self.session() as db:
            session=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1'),db)
            token=session['token'];authorization='Bearer '+token
            action=self.api['create_action'](self.scan_id,self.report['id'],SmbAction(action='list',share='Docs'),authorization,db)
            saved=json.loads(self.store.get(self.actions.session_key(token)));saved.update(secret='',revoked='authentication_failed')
            self.store.set(self.actions.session_key(token),json.dumps(saved))
            self.assertEqual(self.api['get_action'](self.scan_id,self.report['id'],action['id'],authorization,db)['id'],action['id'])
            with self.assertRaises(HTTPException):self.api['create_action'](self.scan_id,self.report['id'],SmbAction(action='list',share='Docs'),authorization,db)

    def test_one_password_connection_serves_other_reported_hosts_in_same_scan(self):
        meta={'host':'192.0.2.2','account':'reader','source':None,'author':None,'observed_at':None,'filename':'other.json'}
        other=smb.import_report(self.temp.name,self.scan_id,json.dumps({'Public':{}}).encode(),meta)
        with self.session() as db:
            connected=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',mode='credentials',username='reader',password='private-secret'),db)
            self.assertEqual(connected['hosts'],['192.0.2.1','192.0.2.2'])
            _,session=self.api['session_for'](self.scan_id,other['id'],'Bearer '+connected['token'])
            self.assertEqual(session['host'],'192.0.2.2')
            self.assertEqual(session['secret'],'private-secret')
            limited=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',browse_scope='host'),db)
            with self.assertRaises(HTTPException):self.api['session_for'](self.scan_id,other['id'],'Bearer '+limited['token'])

    def test_manual_kerberos_connection_preserves_explicit_spn_scope(self):
        with self.session() as db:
            connected=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',mode='credentials',username='reader',domain='lab.example',credential_type='kerberos',aes_key='b'*64,kdc_host='192.0.2.10',server_names={'192.0.2.1':'fs01.lab.example'}),db)
            self.assertEqual(connected['report_id'],self.report['id'])
            self.assertEqual(connected['hosts'],['192.0.2.1'])

    def test_collect_reuses_password_and_ntlm_without_exposing_secret(self):
        for credential_type,secret in [('password','private-secret'),('ntlm','a'*32)]:
            with self.subTest(method=credential_type),self.session() as db:
                from app.models.scan import Scan
                scan=db.get(Scan,self.scan_id);scan.smb_job=None;db.commit()
                payload=SmbStart(targets='192.0.2.1',mode='credentials',username='reader',credential_type=credential_type,
                                 **({'password':secret} if credential_type=='password' else {'nt_hash':secret}))
                session=self.api['open_session'](self.scan_id,self.report['id'],payload,db)
                job=self.api['collect_files'](self.scan_id,self.report['id'],{'targets':'192.0.2.1'},'Bearer '+session['token'],db)
                self.assertTrue(job['options']['spider']);self.assertEqual(job['options']['depth'],3)
                self.assertEqual(job['options']['username'],'reader')
                self.assertEqual(self.store.get(self.jobs['secret_key'](job['id'])),secret)
                self.assertNotIn(secret,json.dumps(job));self.assertNotIn(secret,json.dumps(self.state()))
                self.assertNotIn(secret,str(self.broker.apply_async.call_args))

    def test_collect_enforces_session_scope_revocation_and_expiry(self):
        with self.session() as db:
            session=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',browse_scope='host'),db)
            auth='Bearer '+session['token']
            with self.assertRaises(HTTPException) as error:
                self.api['collect_files'](self.scan_id,self.report['id'],{'targets':'192.0.2.99'},auth,db)
            self.assertEqual(error.exception.status_code,403)
            self.broker.apply_async.assert_not_called()
            saved=json.loads(self.store.get(self.actions.session_key(session['token'])))
            saved['revoked']='authentication_failed';self.store.set(self.actions.session_key(session['token']),json.dumps(saved))
            with self.assertRaises(HTTPException):self.api['collect_files'](self.scan_id,self.report['id'],{'targets':'192.0.2.1'},auth,db)
            self.store.delete(self.actions.session_key(session['token']))
            with self.assertRaises(HTTPException):self.api['collect_files'](self.scan_id,self.report['id'],{'targets':'192.0.2.1'},auth,db)

    def test_collect_reuses_explicit_kerberos_spn(self):
        with self.session() as db:
            session=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',mode='credentials',username='reader',domain='lab.test',credential_type='kerberos',aes_key='b'*64,kdc_host='192.0.2.10',server_names={'192.0.2.1':'fs.lab.test'}),db)
            job=self.api['collect_files'](self.scan_id,self.report['id'],{'targets':'192.0.2.1'},'Bearer '+session['token'],db)
            self.assertEqual(job['options']['server_names'],{'192.0.2.1':'fs.lab.test'})
            self.assertTrue(job['options']['spider']);self.assertNotIn('b'*64,json.dumps(job))

    def test_access_recheck_reuses_identity_without_spider(self):
        with self.session() as db:
            session=self.api['open_session'](self.scan_id,self.report['id'],SmbStart(targets='192.0.2.1',mode='credentials',username='reader',password='private-secret'),db)
            job=self.api['check_access'](self.scan_id,self.report['id'],{'targets':'192.0.2.1'},'Bearer '+session['token'],db)
            self.assertFalse(job['options']['spider']);self.assertEqual(job['options']['username'],'reader')
            self.assertNotIn('private-secret',json.dumps(job))
