"""Local SMB catalog deletion: isolation, validation and active-job protection."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
from fastapi import HTTPException
from app.models.scan import Scan
from app.reports import smb
from test_smb_jobs import SmbJobFixture


class SmbDeletionTests(SmbJobFixture, unittest.TestCase):
    def report(self, scan_id=None):
        return smb.import_report(self.temp.name,scan_id or self.scan_id,b'{"Docs":{}}',
                                 {'host':'192.0.2.1','account':'LAB\\reader','filename':'report.json'})

    def test_selected_only_and_job_reference_cleanup(self):
        first=self.report();second=self.report()
        with self.session() as db:
            scan=db.get(Scan,self.scan_id)
            scan.smb_job={'status':'completed','report_ids':[first['id'],second['id']]};db.commit()
            result=self.api['delete_reports'](self.scan_id,{'report_ids':[first['id']]},db)
            self.assertEqual(result,{'deleted':[first['id']]})
            self.assertIsNotNone(db.get(Scan,self.scan_id))
        self.assertEqual(self.state()['report_ids'],[second['id']])
        self.assertEqual([item['id'] for item in smb.list_reports(self.temp.name,self.scan_id)],[second['id']])
        self.assertFalse((Path(self.temp.name)/str(self.scan_id)/'smb'/first['id']).exists())

    def test_invalid_or_cross_scan_selection_removes_nothing(self):
        first=self.report();foreign=self.report(self.scan_id+1)
        for ids in ([],[first['id'],first['id']],['../escape'],[first['id'],foreign['id']],None,'bad'):
            with self.subTest(ids=ids),self.session() as db:
                with self.assertRaises(HTTPException):
                    self.api['delete_reports'](self.scan_id,{'report_ids':ids},db)
                self.assertEqual(smb.get_report(self.temp.name,self.scan_id,first['id'])['id'],first['id'])
        self.assertEqual(smb.get_report(self.temp.name,self.scan_id+1,foreign['id'])['id'],foreign['id'])

    def test_active_job_blocks_deletion_and_missing_scan_is_404(self):
        report=self.report()
        for status in ('queued','running'):
            with self.session() as db:
                scan=db.get(Scan,self.scan_id);scan.smb_job={'status':status};db.commit()
                with self.assertRaises(HTTPException) as raised:
                    self.api['delete_reports'](self.scan_id,{'report_ids':[report['id']]},db)
                self.assertEqual(raised.exception.status_code,409)
        self.assertTrue(smb.report_dir(self.temp.name,self.scan_id,report['id']).is_dir())
        with self.session() as db,self.assertRaises(HTTPException) as raised:
            self.api['delete_reports'](999,{'report_ids':[report['id']]},db)
        self.assertEqual(raised.exception.status_code,404)

    def test_symlink_cannot_delete_external_directory(self):
        report=self.report();external=Path(self.temp.name)/'outside';external.mkdir();(external/'keep').write_text('keep')
        link=Path(self.temp.name)/str(self.scan_id)/'smb'/('f'*32);link.symlink_to(external,target_is_directory=True)
        with self.assertRaises(FileNotFoundError):
            smb.delete_reports(self.temp.name,self.scan_id,[report['id'],link.name])
        self.assertEqual((external/'keep').read_text(),'keep')
        self.assertTrue(smb.report_dir(self.temp.name,self.scan_id,report['id']).exists())

    def test_move_failure_rolls_back_prior_moves(self):
        first=self.report();second=self.report();original=Path.rename
        def rename(path,target):
            if path.name==second['id']:raise OSError('disk failure')
            return original(path,target)
        with patch.object(Path,'rename',rename),self.assertRaises(OSError):
            smb.delete_reports(self.temp.name,self.scan_id,[first['id'],second['id']])
        self.assertEqual(len(smb.list_reports(self.temp.name,self.scan_id)),2)
