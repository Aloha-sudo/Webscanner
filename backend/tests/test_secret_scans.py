import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from app.secrets import store
from app.secrets.engine import Detector,available
from app.reports import smb
from app.core.secret_probe import scan,size_hint
from app.core import smb_file_ops

class SecretTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.meta=dict(host='192.0.2.1',account='LAB\\user',filename='report.json')
 def tearDown(self):self.temp.cleanup()
 def report(self):
  info={'size':'1 KB','ctime_epoch':'','mtime_epoch':'','atime_epoch':''}
  return smb.import_report(self.root,1,json.dumps({'Docs':{'note.txt':info,'image.png':info}}).encode(),self.meta)
 def test_detector_preserves_only_redacted_classification(self):
  match=SimpleNamespace(triage=SimpleNamespace(label='Red'),rule_name='PasswordConfig',match='TOPSECRET',context='password=TOPSECRET')
  engine=Mock();engine.scan_content.return_value=match
  detector=Detector(engine);prior=SimpleNamespace(status=SimpleNamespace(name='NEEDS_CONTENT'),result=None)
  result=detector.result(prior,b'password=TOPSECRET')
  self.assertEqual(result['kind'],'content');self.assertNotIn('TOPSECRET',json.dumps(result));self.assertEqual(result['evidence'],'[redacted]')
  self.assertTrue(detector.needs_bytes(prior))
 def test_selected_catalog_only_counts_skips_and_deletes_temporary_content(self):
  report=self.report();detector=Mock();detector.check.return_value=SimpleNamespace(status=SimpleNamespace(name='NEEDS_CONTENT'))
  detector.needs_bytes.return_value=True;detector.result.side_effect=lambda check,data: {'rule':'Config','severity':'Red','kind':'content','evidence':'[redacted]'} if data is not None else None
  connection=Mock();jobdir=self.root/'job';jobdir.mkdir()
  def operate(conn,share,path,action,request,output):
   self.assertEqual(share,'Docs');self.assertEqual(path,'note.txt');output.write_bytes(b'password=TOPSECRET');return {'size':18}
  with patch.object(smb_file_ops,'operate',operate):
   result=scan(self.root,1,[{'report_id':report['id'],'share':'Docs'}],{},'PRIVATE_PASSWORD',jobdir,detector=detector,connector=lambda *args:connection)
  self.assertEqual(result['stats']['read'],1);self.assertEqual(result['stats']['skipped'],1)
  self.assertEqual(len(result['findings']),1);self.assertFalse((jobdir/'content.bin').exists())
  self.assertNotIn('TOPSECRET',(jobdir/'progress.json').read_text());self.assertNotIn('PRIVATE_PASSWORD',json.dumps(result))
  connection.close.assert_called_once()
 def test_store_validation_isolation_stale_jobs_and_active_scope(self):
  token='a'*32;path=store.directory(self.root,1,token)
  state={'id':token,'status':'running','created_at':store.now(),'updated_at':store.now(),'choices':[{'report_id':'b'*32,'share':'Docs'}]}
  store.write(path,state);self.assertTrue(store.active(self.root,1));self.assertFalse(store.active(self.root,2));self.assertFalse(store.active(self.root,1,['c'*32]))
  with self.assertRaises(FileNotFoundError):store.read(self.root,2,token)
  with self.assertRaises(FileNotFoundError):store.directory(self.root,1,'../escape')
  state['updated_at']='2000-01-01T00:00:00+00:00';store.write(path,state)
  self.assertFalse(store.active(self.root,1));self.assertEqual(store.read(self.root,1,token)['status'],'failed')
 def test_size_hints_and_missing_engine_fail_explicitly(self):
  self.assertEqual(size_hint('1.5 KB'),1536);self.assertEqual(size_hint('0 B'),0);self.assertEqual(size_hint(None),1)
  with patch('app.secrets.engine.available',return_value=False),self.assertRaisesRegex(ValueError,'secret_engine_unavailable'):Detector()
 @unittest.skipUnless(available(),'pinned snaffler-ng is not installed in this environment')
 def test_real_pinned_engine_contract(self):
  detector=Detector();check=detector.check('//192.0.2.1/Docs/app.config',100)
  self.assertIn(check.status.name,('DISCARD','SNAFFLE','MATCHED','NEEDS_CONTENT','CHECK_KEYS','PEEK_ARCHIVE'))
  if detector.needs_bytes(check):detector.result(check,b'password="fixture-only-password"')

 @unittest.skipUnless(available(),'pinned engine required')
 def test_ssh_and_putty_keys_after_read_limit_are_still_classified(self):
  info={'size':'1 KB','ctime_epoch':'','mtime_epoch':'','atime_epoch':''}
  entries={f'a{i:03}.txt':info for i in range(502)}
  entries.update({'z/id_rsa':info,'z/test.ppk':info})
  report=smb.import_report(self.root,1,json.dumps({'Docs':entries}).encode(),self.meta)
  output=self.root/'key-job';output.mkdir()
  def operate(conn,share,path,action,request,target):target.write_bytes(b'just fixture text');return {'size':17}
  with patch('app.core.secret_probe.MAX_FILES',1),patch.object(smb_file_ops,'operate',operate):
   result=scan(self.root,1,[{'report_id':report['id'],'share':'Docs'}],{},'',output,detector=Detector(),connector=lambda *args:Mock())
  names={finding['name'] for finding in result['findings']}
  self.assertIn('id_rsa',names);self.assertIn('test.ppk',names)
  self.assertEqual(result['stats']['considered'],504);self.assertLessEqual(result['stats']['read'],1)
  self.assertTrue(result['partial'])

 @unittest.skipUnless(available(),'pinned engine required')
 def test_real_private_key_header_in_generic_text_file(self):
  detector=Detector();check=detector.check('//192.0.2.1/Demo/neutral.txt',128)
  self.assertTrue(detector.needs_bytes(check))
  result=detector.result(check,b'-----BEGIN OPENSSH PRIVATE KEY-----\nfictional-test-data\n-----END OPENSSH PRIVATE KEY-----\n')
  self.assertIsNotNone(result);self.assertEqual(result['kind'],'content');self.assertNotIn('fictional',json.dumps(result))
