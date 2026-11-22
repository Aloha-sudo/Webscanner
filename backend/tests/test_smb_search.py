import json
import tempfile
import unittest
from unittest.mock import patch
from app.reports import smb
from app.reports.smb_search import search_files


def info(size='1 KB'):
    return dict(size=size,ctime_epoch='',mtime_epoch='',atime_epoch='')


class SmbFileSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=self.temp.name
    def tearDown(self):self.temp.cleanup()
    def report(self,host='192.0.2.1',account='LAB\\one',files=None,scan=1):
        return smb.import_report(self.root,scan,json.dumps({'Docs':files or {}},ensure_ascii=False).encode(),
                                 dict(host=host,account=account,auth_method='password',filename='report.json'))
    def test_search_masks_unicode_literals_and_scan_isolation(self):
        report=self.report(files={'HR/Договор.docx':info(),'HR/vault.kdbx':info(),'HR/100%_done.txt':info(),'a[1].txt':info()})
        self.report(scan=2,files={'secret.kdbx':info()})
        for query,expected in [('дОгОвОр','HR/Договор.docx'),('*.KDBX','HR/vault.kdbx'),('HR\\*.docx','HR/Договор.docx'),('%_','HR/100%_done.txt'),('a[1].*','a[1].txt')]:
            result=search_files(self.root,1,query)
            self.assertEqual(result['total'],1,query);self.assertEqual(result['items'][0]['entry']['path'],expected)
            self.assertEqual(result['items'][0]['sources'][0]['report_id'],report['id'])
        self.assertEqual(search_files(self.root,1,"' OR 1=1 --")['total'],0)
        self.assertEqual(search_files(self.root,1,'HR')['total'],3,'directories are not file hits')
        self.assertEqual(search_files(self.root,999,'*')['total'],0)
    def test_latest_per_account_and_host_and_cross_account_merge(self):
        self.report(files={'old.txt':info()})
        one=self.report(files={'shared.txt':info(),'one.txt':info()})
        two=self.report(account='LAB\\two',files={'shared.txt':info(),'two.txt':info()})
        self.report(host='192.0.2.2',files={'shared.txt':info()})
        result=search_files(self.root,1,'*')
        self.assertEqual(result['total'],4)
        shared=next(item for item in result['items'] if item['host']=='192.0.2.1' and item['entry']['path']=='shared.txt')
        self.assertEqual({source['report_id'] for source in shared['sources']},{one['id'],two['id']})
        self.assertEqual(result['covered_hosts'],2);self.assertEqual(result['hosts'],2)
        page=search_files(self.root,1,'*',offset=2,limit=1)
        self.assertEqual(page['items'],result['items'][2:3]);self.assertEqual(page['total'],4)
    def test_share_only_latest_does_not_reuse_older_file_list_and_partial_is_visible(self):
        self.report(files={'stale.txt':info()})
        smb.store_report(self.root,1,b'{}',dict(host='192.0.2.1',account='LAB\\one',auth_method='password',format='webscanner-smb',coverage='shares'),[],[])
        result=search_files(self.root,1,'*');self.assertEqual(result['total'],0);self.assertEqual(result['covered_hosts'],0)
        report=self.report(account='LAB\\two',files={'a.txt':info(),'b.txt':info()})
        with patch('app.reports.smb_search.MAX_MATCHES',1):
            result=search_files(self.root,1,'*');self.assertTrue(result['partial']);self.assertTrue(result['truncated']);self.assertEqual(result['total'],1)
        (smb.report_dir(self.root,1,report['id'])/'catalog.sqlite3').write_bytes(b'broken')
        # Damaged metadata listing remains an explicit error rather than a false no-match.
        with self.assertRaises(ValueError):search_files(self.root,1,'*')
    def test_invalid_search_input(self):
        for query in ('','   ','x'*201,'x\ny'):
            with self.assertRaises(ValueError):search_files(self.root,1,query)
        with self.assertRaises(ValueError):search_files(self.root,1,'*',offset=-1)
