"""Synthetic source adapters: real runner, fake FTP and isolated local files."""
import ftplib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from pydantic import SecretStr
from app.secrets.sources import ftp_location,ftp_in_scope,local_directory,read_local,prepare,connect_ftp
from app.secrets.native import run_native,read_findings
from app.core.secret_file_ops import operate
from app.core.smb_file_ops import FileLimit

KEY=b'-----BEGIN OPENSSH PRIVATE KEY-----\nFICTIONAL_SOURCE_CONTENT\n-----END OPENSSH PRIVATE KEY-----'
class FakeFTP:
 def mlsd(self,path):return [('id_rsa',{'type':'file','size':str(len(KEY))}),('neutral.txt',{'type':'file','size':str(len(KEY))})]
 def retrbinary(self,command,callback):callback(KEY)
 def voidcmd(self,command):return '200 OK'
 def quit(self):pass
 def close(self):pass

class SourceTests(unittest.TestCase):
 def test_ftp_locations_and_scoped_roots(self):
  self.assertEqual(ftp_location('EXAMPLE.test:2121/docs/'),'ftp://example.test:2121/docs')
  options={'targets':['ftp://192.0.2.1:2121/docs']}
  self.assertEqual(ftp_in_scope(options,'ftp://192.0.2.1:2121/docs/key').path,'/docs/key')
  for value in ['ftp://192.0.2.2:2121/docs/key','ftp://192.0.2.1/docs/key','ftp://192.0.2.1:2121/docs-other/key','ftp://192.0.2.1:2121/else/key']:
   with self.assertRaises(ValueError):ftp_in_scope(options,value)
 def test_ftp_urls_cannot_contain_credentials_or_commands(self):
  for value in ['ftp://user:PRIVATE@192.0.2.1/docs','ftp://192.0.2.1:99999','ftp://192.0.2.1/../app','ftp://192.0.2.1/key\nDELE data','sftp://192.0.2.1','ftp://192.0.2.1/?password=PRIVATE']:
   with self.assertRaises(ValueError,msg=value):ftp_location(value)
 def test_local_directory_is_relative_and_links_are_rejected(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);inputs=root/'inputs';inputs.mkdir();folder=inputs/'client';folder.mkdir();(folder/'id_rsa').write_bytes(KEY)
   outside=root/'outside';outside.mkdir();(outside/'secret').write_bytes(KEY);(inputs/'link').symlink_to(outside,target_is_directory=True);(folder/'alias').symlink_to(outside/'secret')
   self.assertEqual(local_directory(inputs,'client'),str(folder));self.assertEqual(read_local({'local_paths':[str(folder)]},str(folder/'id_rsa'),4),KEY[:4])
   for value in ['../outside',str(outside),'link']:
    with self.assertRaises(ValueError):local_directory(inputs,value)
   for value in [outside/'secret',folder/'alias',folder/'..'/'..'/'outside'/'secret']:
    with self.assertRaises(ValueError):read_local({'local_paths':[str(folder)]},str(value),1024)
 def test_full_native_local_source_and_preview(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);inputs=root/'inputs';inputs.mkdir();(inputs/'neutral.txt').write_bytes(KEY)
   outside=root/'id_rsa';outside.write_bytes(KEY);(inputs/'id_rsa').symlink_to(outside)
   output=root/'job';output.mkdir();options={'source':'local','targets':[str(inputs)],'local_paths':[str(inputs)]}
   result=run_native(options,'',output)
   self.assertEqual(result['status'],'completed');self.assertGreater(result['finding_count'],0)
   items=read_findings(output)['items'];self.assertTrue(all(item['source']=='local' for item in items));self.assertFalse(any(item['name']=='id_rsa' for item in items))
   preview=operate(options,'',str(inputs/'neutral.txt'),'preview',root/'download');self.assertIn('FICTIONAL_SOURCE_CONTENT',preview['preview']['text'])
   self.assertFalse((root/'download').exists());operate(options,'',str(inputs/'neutral.txt'),'download',root/'download');self.assertEqual((root/'download').read_bytes(),KEY)
   for file in output.iterdir():
    if file.is_file():self.assertNotIn(b'FICTIONAL_SOURCE_CONTENT',file.read_bytes())
 def test_full_native_ftp_source_and_preview(self):
  options={'source':'ftp','targets':['ftp://192.0.2.1:2121/docs'],'username':'reader','ftp_tls':False}
  with tempfile.TemporaryDirectory() as temporary:
   output=Path(temporary)
   with patch('app.secrets.sources.connect_ftp',side_effect=lambda *args:FakeFTP()) as connect:
    result=run_native(options,'FICTIONAL_FTP_PASSWORD',output)
   self.assertEqual(result['status'],'completed');self.assertGreater(result['finding_count'],0);self.assertGreater(result['stats']['read'],0)
   items=read_findings(output)['items'];self.assertTrue(all(item['source']=='ftp' for item in items));self.assertEqual(items[0]['host'],'192.0.2.1')
   self.assertTrue(all(call.args[2:] == ('192.0.2.1',2121) for call in connect.call_args_list))
   with patch('app.core.secret_file_ops.connect_ftp',return_value=FakeFTP()):
    value=operate(options,'FICTIONAL_FTP_PASSWORD',items[0]['location'],'preview',output/'download')
   self.assertIn('FICTIONAL_SOURCE_CONTENT',value['preview']['text'])
   for file in output.iterdir():
    if file.is_file():self.assertNotIn(b'FICTIONAL_SOURCE_CONTENT',file.read_bytes());self.assertNotIn(b'FICTIONAL_FTP_PASSWORD',file.read_bytes())
 def test_ftp_transport_tls_and_login_failure_cleanup(self):
  ftp=Mock();options={'targets':['ftp://example.test:2121/docs'],'username':'reader','ftp_tls':True}
  with patch('app.secrets.sources.ftplib.FTP_TLS',return_value=ftp) as factory:
   self.assertIs(connect_ftp(options,'FICTIONAL','example.test',2121),ftp)
  ftp.prot_p.assert_called_once();ftp.login.assert_called_once_with('reader','FICTIONAL');self.assertTrue(factory.call_args.kwargs['context'].check_hostname)
  ftp.login.side_effect=ftplib.error_perm('530 Login incorrect')
  with patch('app.secrets.sources.ftplib.FTP_TLS',return_value=ftp):
   with self.assertRaises(ftplib.error_perm):connect_ftp(options,'FICTIONAL','example.test',2121)
  ftp.close.assert_called_once()
  with self.assertRaises(ValueError):connect_ftp(options,'FICTIONAL','other.test',2121)
 def test_prepare_keeps_password_out_of_public_options(self):
  payload=SimpleNamespace(source='ftp',options=None,use_session=False,scan_id=None,locations=['ftp://192.0.2.1/docs'],ftp_username='reader',ftp_password=SecretStr('FICTIONAL_FTP_PASSWORD'),ftp_tls=False)
  request=prepare(payload,'/unused');self.assertNotIn('FICTIONAL_FTP_PASSWORD',str(request.public()));self.assertEqual(request.credential(),'FICTIONAL_FTP_PASSWORD')
 def test_preview_limit(self):
  ftp=FakeFTP();ftp.retrbinary=lambda command,callback:callback(b'12345')
  with tempfile.TemporaryDirectory() as temporary,patch('app.core.secret_file_ops.connect_ftp',return_value=ftp),patch('app.core.secret_file_ops.MAX_DOWNLOAD',4):
   with self.assertRaises(FileLimit):operate({'source':'ftp','targets':['ftp://192.0.2.1/']},'','ftp://192.0.2.1/file','download',Path(temporary)/'download')
