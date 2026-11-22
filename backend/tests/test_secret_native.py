"""Exercise the real pinned runner on fictional local files; no SMB network IO."""
import tempfile
from pathlib import Path
import unittest
from app.secrets.native import run_native,read_findings,configuration,parse_path

class NativeSecretTests(unittest.TestCase):
 def test_native_fast_and_normal_find_keys_without_persisting_content(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'input';source.mkdir()
   (source/'id_rsa').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nFICTIONAL_PRIVATE_VALUE\n-----END OPENSSH PRIVATE KEY-----')
   (source/'neutral.txt').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nFICTIONAL_CONTENT_VALUE\n-----END OPENSSH PRIVATE KEY-----')
   (source/'credentials.txt').write_text('password="FICTIONAL_PASSWORD_VALUE"')
   for fast in (True,False):
    output=root/str(fast);output.mkdir()
    value=run_native({'targets':[]},'',output,fast=fast,local_paths=[str(source)])
    self.assertEqual(value['status'],'completed');self.assertGreater(value['finding_count'],0);self.assertGreater(value['stats']['read'],0)
    page=read_findings(output,'id_rsa');self.assertGreater(page['total'],0)
    self.assertTrue(all(item['evidence']=='[redacted]' for item in page['items']))
    for file in output.iterdir():
     if file.is_file():
      raw=file.read_bytes();self.assertNotIn(b'FICTIONAL_PRIVATE_VALUE',raw);self.assertNotIn(b'FICTIONAL_PASSWORD_VALUE',raw);self.assertNotIn(b'FICTIONAL_CONTENT_VALUE',raw)
 def test_native_defaults_fresh_state_no_remote_write_checks(self):
  cfg=configuration({'targets':['192.0.2.1']},Path('/tmp/fictional-native'),fast=False)
  self.assertFalse(cfg.targets.check_writable);self.assertFalse(cfg.scanning.snaffle)
  self.assertIsNone(cfg.scanning.max_depth);self.assertIn('IPC$',cfg.targets.exclude_share)
  self.assertGreater(len(cfg.rules.file),0)
 def test_pagination_queries_all_findings_instead_of_first_page(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as temporary:
   path=Path(temporary)
   with sqlite3.connect(path/'engine.sqlite3') as db:
    db.execute('CREATE TABLE finding(finding_id TEXT,file_path TEXT,rule_name TEXT,triage TEXT,context TEXT,size INTEGER)')
    db.executemany('INSERT INTO finding VALUES(?,?,?,?,?,?)',[(str(i),f'//192.0.2.1/Docs/{i:04}.txt','Rule','Red','name',1) for i in range(205)])
   self.assertEqual(len(read_findings(path)['items']),100)
   self.assertEqual(read_findings(path,offset=200)['total'],205)
   self.assertEqual(len(read_findings(path,offset=200)['items']),5)
   self.assertEqual(read_findings(path,'0204.txt')['total'],1)
   self.assertEqual(read_findings(path,'*.txt')['total'],205)
 def test_unc_paths(self):
  self.assertEqual(parse_path(r'\\192.0.2.1\Docs\folder\id_rsa')['path'],'folder/id_rsa')
  self.assertIsNone(parse_path('/etc/passwd'))

 def test_transport_delegates_auth_and_rejects_outside_scope(self):
  from unittest.mock import patch,Mock
  from snaffler.transport.smb import SMBTransport
  options={'targets':['192.0.2.1'],'mode':'credentials','credential_type':'ntlm','username':'reader','domain':'LAB'}
  def execute(controller):
   transport=SMBTransport(controller.cfg)
   transport.connect('192.0.2.1')
   with self.assertRaises(ValueError):transport.connect('192.0.2.99')
  with tempfile.TemporaryDirectory() as temporary:
   with patch('app.core.smb_file_ops.connect',return_value=Mock()) as connect,patch('snaffler.engine.runner.SnafflerRunner.execute',execute):
    run_native(options,'a'*32,Path(temporary))
   connect.assert_called_once_with('192.0.2.1',options,'a'*32)
 def test_unreachable_first_ip_does_not_abort_subnet(self):
  from unittest.mock import patch
  reached=[]
  def execute(controller):
   controller._validate_credentials();reached.append(True)
  with tempfile.TemporaryDirectory() as temporary:
   with patch('app.core.smb_file_ops.connect',side_effect=OSError('unreachable')),patch('snaffler.engine.runner.SnafflerRunner.execute',execute):
    run_native({'targets':['192.0.2.1','192.0.2.2']},'',Path(temporary))
  self.assertEqual(reached,[True])

 def test_tuning_maps_to_native_limits_threads_and_exclusions(self):
  cfg=configuration({'targets':['192.0.2.1']},Path('/tmp/fixture'),fast=False,max_depth=4,share_names=['Docs*'],exclude_shares=['Backup'],tuning={'max_file_mb':32,'read_mb':8,'threads':12,'exclude_paths':['*/Temp']})
  self.assertEqual(cfg.scanning.max_depth,4);self.assertEqual(cfg.scanning.max_file_bytes,32*1024**2);self.assertEqual(cfg.scanning.max_read_bytes,8*1024**2)
  self.assertEqual(cfg.advanced.max_threads,12);self.assertEqual(cfg.advanced.file_threads,4);self.assertIn('*/Temp',cfg.targets.exclude_unc);self.assertEqual(cfg.targets.share_filter,['Docs*'])
 def test_depth_zero_and_directory_exclusions_affect_real_traversal(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'input';source.mkdir();(source/'id_rsa').write_text('fictional');nested=source/'nested';nested.mkdir();(nested/'id_ed25519').write_text('fictional')
   for mode,depth,tuning,expected in [('root',0,{},1),('all',None,{},2),('excluded',None,{'exclude_paths':['*/nested']},1)]:
    output=root/mode;output.mkdir();value=run_native({'targets':[]},'',output,fast=False,max_depth=depth,tuning=tuning,local_paths=[str(source)])
    self.assertEqual(value['finding_count'],expected,mode)
 def test_read_limit_keeps_filename_findings_and_marks_partial(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'input';source.mkdir()
   for number in range(6):(source/f'neutral{number}.txt').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nFICTIONAL\n-----END OPENSSH PRIVATE KEY-----')
   (source/'id_rsa').write_text('FICTIONAL')
   output=root/'job';output.mkdir();value=run_native({'targets':[]},'',output,local_paths=[str(source)],tuning={'max_reads':1})
   self.assertEqual(value['status'],'partial');self.assertEqual(value['stats']['read'],1);self.assertGreater(value['stats']['read_limit'],0)
   self.assertGreater(read_findings(output,'id_rsa')['total'],0)
 def test_total_volume_budget_never_exceeded_and_small_files_not_false_partial(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'input';source.mkdir()
   (source/'neutral.txt').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nFICTIONAL\n-----END OPENSSH PRIVATE KEY-----')
   small=root/'small';small.mkdir();value=run_native({'targets':[]},'',small,local_paths=[str(source)],tuning={'total_read_mb':1})
   self.assertEqual(value['status'],'completed')
   for number in range(8):(source/f'data{number}.txt').write_bytes(b'x'*400000)
   output=root/'limited';output.mkdir();value=run_native({'targets':[]},'',output,local_paths=[str(source)],tuning={'total_read_mb':1})
   self.assertLessEqual(value['stats']['bytes'],1024**2);self.assertEqual(value['status'],'partial');self.assertGreater(value['stats']['volume_limit'],0)
