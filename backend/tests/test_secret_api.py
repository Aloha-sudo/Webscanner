import ast,json
from pathlib import Path
import shutil
from types import ModuleType
from unittest.mock import Mock,patch
from uuid import uuid4
import unittest
from pydantic import BaseModel,ConfigDict,Field,SecretStr
from fastapi import HTTPException
from app.secrets import store
from app.schemas.smb import SmbStart
import test_smb_file_sessions as session_fixture
from test_smb_jobs import load_functions

class SecretApiTests(unittest.TestCase):
 def setUp(self):
  self.f=session_fixture.SmbFileSessionTests(methodName='runTest');self.f.setUp()
  ns=dict(self.f.api,store=store,available=lambda:True,BaseModel=BaseModel,ConfigDict=ConfigDict,Field=Field,SecretStr=SecretStr,shutil=shutil,uuid4=uuid4)
  source=Path(__file__).parents[1]/'app/api/secrets.py'
  nodes=[node for node in ast.parse(source.read_text()).body if isinstance(node,ast.ClassDef)]
  exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(source),'exec'),ns)
  self.api=load_functions('app/api/secrets.py',ns)
  self.task=Mock();module=ModuleType('app.core.secret_jobs');module.scan_secrets=self.task;module.request_key=lambda token:'secret-request:'+token
  self.modules=patch.dict('sys.modules',{'app.core.secret_jobs':module});self.modules.start()
  with self.f.session() as db:self.session=self.f.api['open_session'](self.f.scan_id,self.f.report['id'],SmbStart(targets='192.0.2.1',mode='credentials',username='reader',password='PRIVATE_PASSWORD'),db)
  self.auth='Bearer '+self.session['token'];self.payload=ns['Start'](choices=[{'report_id':self.f.report['id'],'share':'Docs'}])
 def tearDown(self):self.modules.stop();self.f.tearDown()
 def start(self):
  with self.f.session() as db:return self.api['start'](self.f.scan_id,self.payload,self.auth,db)
 def test_start_scoped_queue_ids_only_and_single_active_job(self):
  job=self.start();self.assertNotIn('PRIVATE_PASSWORD',json.dumps(job));self.assertNotIn(self.session['token'],json.dumps(job))
  self.assertNotIn('PRIVATE_PASSWORD',str(self.task.apply_async.call_args));self.assertEqual(job['choices'],[{'report_id':self.f.report['id'],'share':'Docs'}])
  with self.assertRaises(HTTPException) as raised:self.start()
  self.assertEqual(raised.exception.status_code,409)
 def test_missing_engine_and_wrong_share_do_not_enqueue(self):
  self.api['available']=lambda:False
  with self.assertRaises(HTTPException) as raised:self.start()
  self.assertEqual(raised.exception.status_code,503)
  self.api['available']=lambda:True;self.payload.choices[0].share='Other'
  with self.assertRaises(HTTPException) as raised:self.start()
  self.assertEqual(raised.exception.status_code,422);self.task.apply_async.assert_not_called()
 def test_expired_session_blocks_start(self):
  self.f.store.delete(self.f.actions.session_key(self.session['token']))
  with self.assertRaises(HTTPException) as raised:self.start()
  self.assertEqual(raised.exception.status_code,401);self.task.apply_async.assert_not_called()
 def test_cancel_delete_and_scan_isolation(self):
  job=self.start()
  with self.f.session() as db:
   with self.assertRaises(HTTPException):self.api['delete'](self.f.scan_id,job['id'],db)
   state=self.api['cancel'](self.f.scan_id,job['id'],db);self.assertEqual(state['status'],'cancelled')
   self.assertTrue((store.directory(self.f.temp.name,self.f.scan_id,job['id'])/'cancel').exists())
   with self.assertRaises(HTTPException):self.api['get_job'](999,job['id'],db)
   self.api['delete'](self.f.scan_id,job['id'],db)
   with self.assertRaises(FileNotFoundError):store.read(self.f.temp.name,self.f.scan_id,job['id'])
 def test_queue_failure_is_visible(self):
  self.task.apply_async.side_effect=RuntimeError('queue')
  with self.assertRaises(HTTPException) as raised:self.start()
  self.assertEqual(raised.exception.status_code,503);jobs=store.jobs(self.f.temp.name,self.f.scan_id);self.assertEqual(jobs[0]['status'],'failed')

 def test_standalone_context_requires_no_project_or_port_scan(self):
  with self.f.session() as db:
   value=self.api['create_workspace']({'targets':'192.0.2.0/29'},db)
   from app.models.scan import Scan
   context=db.get(Scan,value['id']);self.assertIsNone(context.project_id);self.assertIsNone(context.network_part_id)
   self.assertEqual(context.scope_targets,'192.0.2.0/29');self.assertEqual(context.scan_type,'smb_workspace')
   self.task.apply_async.assert_not_called()
   with self.assertRaises(HTTPException):self.api['create_workspace']({'targets':'not-a-target'},db)

 def native_module(self):
  module=ModuleType('app.core.secret_workflow');module.native_search=Mock();module.WORKFLOW_TTL=4020;module.cleanup_request=Mock()
  return module
 def native_start(self,**kwargs):
  payload=self.api['WorkflowStart'](options=SmbStart(targets='192.0.2.1',mode='credentials',username='reader',password='FICTIONAL_NATIVE_PASSWORD'),**kwargs)
  with self.f.session() as db:return self.api['start_workflow'](payload,None,db)
 def test_native_search_is_one_task_without_prior_catalog_or_project(self):
  module=self.native_module()
  with patch.dict('sys.modules',{'app.core.secret_workflow':module}):value=self.native_start()
  job=value['job'];self.assertEqual(job['engine'],'snaffler-ng');self.assertEqual(job['choices'],[])
  self.assertEqual(job['phase'],'discovering');module.native_search.apply_async.assert_called_once()
  self.assertNotIn('FICTIONAL_NATIVE_PASSWORD',json.dumps(value));self.assertNotIn('FICTIONAL_NATIVE_PASSWORD',str(module.native_search.apply_async.call_args))
  self.assertNotIn('FICTIONAL_NATIVE_PASSWORD',(store.directory(self.f.temp.name,job['scan_id'],job['id'])/'state.json').read_text())
  self.f.broker.apply_async.assert_not_called()
 def test_native_queue_failure_cleans_private_and_browser_connections(self):
  module=self.native_module();module.native_search.apply_async.side_effect=RuntimeError('queue')
  keys=set(self.f.store.data)
  with patch.dict('sys.modules',{'app.core.secret_workflow':module}):
   with self.assertRaises(HTTPException) as raised:self.native_start()
  self.assertEqual(raised.exception.status_code,503);self.assertEqual(set(self.f.store.data),keys)
 def test_native_findings_preview_uses_saved_id_and_scoped_session(self):
  import sqlite3
  module=self.native_module()
  with patch.dict('sys.modules',{'app.core.secret_workflow':module}):value=self.native_start()
  job=value['job'];path=store.directory(self.f.temp.name,job['scan_id'],job['id']);identifier='c'*40
  with sqlite3.connect(path/'engine.sqlite3') as db:
   db.execute('CREATE TABLE finding(finding_id TEXT,file_path TEXT,rule_name TEXT,triage TEXT,context TEXT,size INTEGER)')
   db.execute('INSERT INTO finding VALUES(?,?,?,?,?,?)',[identifier,'//192.0.2.1/Docs/id_rsa','Key','Black','name',1])
  auth='Bearer '+value['session']['token']
  with self.f.session() as db:
   page=self.api['findings'](job['scan_id'],job['id'],'id_rsa',0,100,db);self.assertEqual(page['total'],1)
   action=self.api['finding_action'](job['scan_id'],job['id'],self.api['FindingAction'](finding_id=identifier,action='preview'),auth,db)
   request=json.loads(self.f.store.get(self.f.actions.request_key(action['id'])))
   self.assertEqual(request['path'],'id_rsa');self.assertEqual(request['host'],'192.0.2.1');self.assertNotIn('FICTIONAL_NATIVE_PASSWORD',json.dumps(request))
   with self.assertRaises(HTTPException):self.api['finding_action_status'](job['scan_id'],job['id'],action['id'],self.auth,db)
   status=self.api['finding_action_status'](job['scan_id'],job['id'],action['id'],auth,db);self.assertNotIn('session',status)
   session=json.loads(self.f.store.get(self.f.actions.session_key(value['session']['token'])));session['hosts']=['192.0.2.2'];self.f.store.set(self.f.actions.session_key(value['session']['token']),json.dumps(session))
   with self.assertRaises(HTTPException) as raised:self.api['finding_action'](job['scan_id'],job['id'],self.api['FindingAction'](finding_id=identifier,action='preview'),auth,db)
   self.assertEqual(raised.exception.status_code,403)

 def test_ftp_starts_without_smb_options_and_password_stays_private(self):
  payload=self.api['WorkflowStart'](source='ftp',locations=['ftp://192.0.2.1:2121/docs'],ftp_username='reader',ftp_password='FICTIONAL_FTP_PASSWORD',ftp_tls=True)
  module=self.native_module()
  with self.f.session() as db,patch.dict('sys.modules',{'app.core.secret_workflow':module}):value=self.api['start_workflow'](payload,None,db)
  self.assertEqual(value['job']['source'],'ftp');self.assertTrue(value['job']['ftp_tls']);self.assertEqual(value['job']['targets'],'ftp://192.0.2.1:2121/docs')
  self.assertNotIn('FICTIONAL_FTP_PASSWORD',json.dumps(value));self.assertNotIn('FICTIONAL_FTP_PASSWORD',str(module.native_search.apply_async.call_args))
  session=json.loads(self.f.store.get(self.f.actions.session_key(value['session']['token'])));self.assertEqual(session['options']['source'],'ftp');self.assertEqual(session['secret'],'FICTIONAL_FTP_PASSWORD')
 def test_local_starts_scoped_to_configured_input_and_reconnect_cannot_expand(self):
  root=Path(self.f.temp.name)/'inputs';root.mkdir();(root/'client').mkdir();(root/'other').mkdir()
  self.f.settings.SECRET_LOCAL_ROOT=str(root)
  payload=self.api['WorkflowStart'](source='local',locations=['client'])
  with self.f.session() as db,patch.dict('sys.modules',{'app.core.secret_workflow':self.native_module()}):value=self.api['start_workflow'](payload,None,db)
  job=value['job'];self.assertEqual(job['source'],'local');self.assertEqual(job['locations'],['client']);self.assertIsNone(value['session']['account'])
  with self.f.session() as db:
   session=self.api['reconnect_source'](job['scan_id'],job['id'],payload,db);self.assertEqual(session['hosts'],[str(root/'client')])
   with self.assertRaises(HTTPException):self.api['reconnect_source'](job['scan_id'],job['id'],self.api['WorkflowStart'](source='local',locations=['other']),db)
   with self.assertRaises(HTTPException):self.api['reconnect_source'](job['scan_id'],job['id'],self.api['WorkflowStart'](source='ftp',locations=['ftp://192.0.2.1']),db)
 def test_ftp_file_actions_and_reconnect_keep_endpoint_and_folder_scope(self):
  import sqlite3
  payload=self.api['WorkflowStart'](source='ftp',locations=['ftp://192.0.2.1:2121/docs'])
  with self.f.session() as db,patch.dict('sys.modules',{'app.core.secret_workflow':self.native_module()}):value=self.api['start_workflow'](payload,None,db)
  job=value['job'];path=store.directory(self.f.temp.name,job['scan_id'],job['id']);identifier='d'*40
  with sqlite3.connect(path/'engine.sqlite3') as db:
   db.execute('CREATE TABLE finding(finding_id TEXT,file_path TEXT,rule_name TEXT,triage TEXT,context TEXT,size INTEGER)')
   db.execute('INSERT INTO finding VALUES(?,?,?,?,?,?)',[identifier,'ftp://192.0.2.1:2121/docs/id_rsa','Key','Black','name',1])
  auth='Bearer '+value['session']['token']
  with self.f.session() as db:
   action=self.api['finding_action'](job['scan_id'],job['id'],self.api['FindingAction'](finding_id=identifier,action='preview'),auth,db)
   request=json.loads(self.f.store.get(self.f.actions.request_key(action['id'])));self.assertEqual(request['location'],'ftp://192.0.2.1:2121/docs/id_rsa')
   self.api['reconnect_source'](job['scan_id'],job['id'],payload,db)
   with self.assertRaises(HTTPException):self.api['reconnect_source'](job['scan_id'],job['id'],self.api['WorkflowStart'](source='ftp',locations=['ftp://192.0.2.1:2121/']),db)
 def test_missing_local_directory_and_invalid_ftp_do_not_queue(self):
  module=self.native_module()
  for payload in [self.api['WorkflowStart'](source='local',locations=['../app']),self.api['WorkflowStart'](source='ftp',locations=['ftp://user:PRIVATE@192.0.2.1'])]:
   with self.f.session() as db,patch.dict('sys.modules',{'app.core.secret_workflow':module}):
    with self.assertRaises(HTTPException) as raised:self.api['start_workflow'](payload,None,db)
   self.assertEqual(raised.exception.status_code,422)
  module.native_search.apply_async.assert_not_called()

 def test_tuning_is_persisted_and_inconsistent_sizes_rejected(self):
  module=self.native_module()
  with patch.dict('sys.modules',{'app.core.secret_workflow':module}):
   value=self.native_start(max_depth=0,time_limit=14400,max_file_mb=64,read_mb=8,total_read_mb=512,max_reads=100,threads=12,exclude_paths=['*/Temp'])
  state=store.read(self.f.temp.name,value['job']['scan_id'],value['job']['id'])
  self.assertEqual(state['max_depth'],0);self.assertEqual(state['time_limit'],14400);self.assertEqual(state['limits']['total_read_mb'],512);self.assertEqual(state['limits']['exclude_paths'],['*/Temp'])
  with patch.dict('sys.modules',{'app.core.secret_workflow':module}):
   with self.assertRaises(HTTPException) as raised:self.native_start(max_file_mb=1,read_mb=2)
  self.assertEqual(raised.exception.status_code,422)
