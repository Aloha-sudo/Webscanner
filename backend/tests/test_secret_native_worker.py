"""Native process lifecycle: scoped one-use request and ephemeral credentials."""
import json,signal,sys,time
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import test_secret_api as api_fixture
from test_smb_jobs import load_functions
from app.secrets import store

class NativeWorkerTests(unittest.TestCase):
 def setUp(self):
  self.f=api_fixture.SecretApiTests(methodName='runTest');self.f.setUp()
  with patch.dict('sys.modules',{'app.core.secret_workflow':self.f.native_module()}):self.value=self.f.native_start()
  self.job=self.value['job'];self.root=self.f.f.temp.name;self.redis=self.f.f.store
  self.path=store.directory(self.root,self.job['scan_id'],self.job['id'])
  self.request_key=lambda token:'secret-request:'+token
  self.private=json.loads(self.redis.get(self.request_key(self.job['id'])))['session']
  self.proc=Mock();self.proc.pid=99999;self.proc.returncode=0;self.proc.poll.return_value=0
  self.os=SimpleNamespace(getpid=lambda:123,killpg=Mock());self.spawn=Mock(side_effect=self.process)
  self.worker=load_functions('app/core/secret_workflow.py',dict(json=json,os=self.os,signal=signal,sys=sys,time=time,
   subprocess=SimpleNamespace(Popen=self.spawn,PIPE=-1,DEVNULL=-3),settings=self.f.f.settings,secret_store=lambda:self.redis,
   session_key=self.f.f.actions.session_key,request_key=self.request_key,store=store))
 def tearDown(self):self.f.tearDown()
 def process(self,*args,**kwargs):
  store.write(self.path,{'status':'completed','findings':[],'stats':{'read':1},'finding_count':0},'result.json')
  return self.proc
 def run_job(self):self.worker['run_search'](self.job['scan_id'],self.job['id'])
 def test_single_claim_stdin_secret_cleanup_and_browser_session_survives(self):
  self.run_job();self.run_job();self.assertEqual(self.spawn.call_count,1)
  self.assertNotIn('FICTIONAL_NATIVE_PASSWORD',str(self.spawn.call_args))
  self.assertIn('FICTIONAL_NATIVE_PASSWORD',self.proc.stdin.write.call_args.args[0])
  self.assertEqual(json.loads(self.proc.stdin.write.call_args.args[0])['tuning']['max_file_mb'],10)
  self.assertIsNone(self.redis.get(self.f.f.actions.session_key(self.private)))
  self.assertIsNotNone(self.redis.get(self.f.f.actions.session_key(self.value['session']['token'])))
  self.assertFalse((self.path/'result.json').exists());self.assertEqual(store.read(self.root,self.job['scan_id'],self.job['id'])['status'],'completed')
 def test_expired_private_session_never_spawns(self):
  self.redis.delete(self.f.f.actions.session_key(self.private));self.run_job();self.spawn.assert_not_called()
  self.assertEqual(store.read(self.root,self.job['scan_id'],self.job['id'])['error'],'session_expired')
 def test_cancellation_kills_process_and_keeps_progress(self):
  self.proc.poll.return_value=None;(self.path/'cancel').touch()
  store.write(self.path,{'stats':{'read':10},'finding_count':2},'progress.json')
  self.run_job();self.os.killpg.assert_called_once_with(self.proc.pid,signal.SIGKILL)
  value=store.read(self.root,self.job['scan_id'],self.job['id']);self.assertEqual(value['status'],'cancelled');self.assertEqual(value['finding_count'],2)
  self.assertFalse((self.path/'progress.json').exists())
