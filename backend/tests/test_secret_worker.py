import json,os,signal,sys,time
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
import test_secret_api as api_fixture
from test_smb_jobs import load_functions
from app.secrets import store

class SecretWorkerTests(unittest.TestCase):
 def setUp(self):
  self.f=api_fixture.SecretApiTests(methodName='runTest');self.f.setUp();self.job=self.f.start()
  self.path=store.directory(self.f.f.temp.name,self.f.f.scan_id,self.job['id'])
  self.proc=Mock();self.proc.pid=99999;self.proc.returncode=0;self.proc.poll.return_value=0
  self.spawn=Mock(side_effect=self.process);self.os=SimpleNamespace(getpid=lambda:123,killpg=Mock())
  self.worker=load_functions('app/core/secret_jobs.py',dict(json=json,os=self.os,signal=signal,sys=sys,time=time,
   subprocess=SimpleNamespace(Popen=self.spawn,PIPE=-1,DEVNULL=-3),settings=self.f.f.settings,
   secret_store=lambda:self.f.f.store,session_key=self.f.f.actions.session_key,store=store))
  self.worker['request_key']=lambda token:'secret-request:'+token
 def tearDown(self):self.f.tearDown()
 def process(self,*args,**kwargs):
  store.write(self.path,{'status':'completed','findings':[],'stats':{'read':1}},'result.json')
  return self.proc
 def run_job(self):self.worker['run'](self.f.f.scan_id,self.job['id'])
 def test_claim_once_only_ids_in_argv_no_credentials_on_disk(self):
  self.run_job();self.run_job();self.assertEqual(self.spawn.call_count,1)
  self.assertNotIn('PRIVATE_PASSWORD',str(self.spawn.call_args));self.assertIn('PRIVATE_PASSWORD',self.proc.stdin.write.call_args.args[0])
  state=store.read(self.f.f.temp.name,self.f.f.scan_id,self.job['id']);self.assertEqual(state['status'],'completed')
  for path in self.path.iterdir():self.assertNotIn('PRIVATE_PASSWORD',path.read_text())
 def test_expired_session_never_spawns(self):
  self.f.f.store.delete(self.f.f.actions.session_key(self.f.session['token']));self.run_job()
  self.spawn.assert_not_called();state=store.read(self.f.f.temp.name,self.f.f.scan_id,self.job['id']);self.assertEqual(state['error'],'session_expired')
 def test_cancel_marker_kills_child_and_removes_temporary_content(self):
  self.proc.poll.return_value=None;(self.path/'cancel').touch();(self.path/'content.bin').write_bytes(b'fixture content')
  self.run_job();self.os.killpg.assert_called_once_with(self.proc.pid,signal.SIGKILL)
  self.assertFalse((self.path/'content.bin').exists());self.assertEqual(store.read(self.f.f.temp.name,self.f.f.scan_id,self.job['id'])['status'],'cancelled')
