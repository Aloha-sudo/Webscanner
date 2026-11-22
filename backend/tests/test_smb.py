import json
from pathlib import Path
import tempfile
import unittest
from app.reports import smb


def file_info(size='1.2 KB'):
    return {'size': size, 'ctime_epoch': '2026-11-06 10:00:00',
            'mtime_epoch': '2026-11-06 11:00:00', 'atime_epoch': '2026-11-06 12:00:00'}


class SmbReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.metadata = {'host': '192.0.2.1', 'account': 'LAB\\reader', 'source': '192.0.2.2',
                         'author': 'tester', 'observed_at': None, 'filename': '192.0.2.1.json'}

    def tearDown(self):
        self.temp.cleanup()

    def upload(self, data, scan=1):
        return smb.import_report(self.root, scan, json.dumps(data, ensure_ascii=False).encode(), self.metadata)

    def test_real_netexec_shape_browse_search_and_provenance(self):
        report = self.upload({'Docs': {'HR/Зарплата.xlsx': file_info(), 'HR/note.txt': file_info('0 B'),
                                      '100%_done.txt': file_info()}, 'Empty': {}})
        self.assertEqual(report['file_count'], 3)
        self.assertEqual(report['directory_count'], 1)
        self.assertEqual(report['account'], 'LAB\\reader')
        self.assertIsNone(report['observed_at'])
        page = smb.browse(self.root, 1, report['id'], 'Docs')
        self.assertEqual([i['kind'] for i in page['items']], ['directory', 'file'])
        self.assertEqual(page['items'][0]['path'], 'HR')
        self.assertEqual(page['items'][0]['metadata'], {})
        page = smb.browse(self.root, 1, report['id'], 'Docs', 'HR')
        self.assertEqual(page['total'], 2)
        self.assertEqual(page['items'][0]['metadata']['size'], '0 B')
        found = smb.browse(self.root, 1, report['id'], 'Docs', query='ЗАРПЛАТА')
        self.assertEqual(found['total'], 1)
        self.assertEqual(smb.browse(self.root, 1, report['id'], 'Docs', query='%_')['total'], 1)
        self.assertEqual(smb.browse(self.root, 1, report['id'], 'Empty')['total'], 0)
        original = smb.report_dir(self.root, 1, report['id']) / 'original.json'
        import hashlib
        self.assertEqual(report['sha256'], hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertEqual(smb.list_reports(self.root, 1), [report])

    def test_pagination_and_scan_isolation(self):
        report = self.upload({'C$': {f'folder/f{i:03}.txt': file_info() for i in range(205)}})
        page = smb.browse(self.root, 1, report['id'], 'C$', 'folder', offset=100)
        self.assertEqual(page['total'], 205)
        self.assertEqual(len(page['items']), 100)
        self.assertEqual(page['items'][0]['name'], 'f100.txt')
        with self.assertRaises(FileNotFoundError):
            smb.browse(self.root, 2, report['id'], 'C$')
        for report_id in ('../1', '/etc/passwd', 'nope'):
            with self.assertRaises(FileNotFoundError):
                smb.get_report(self.root, 1, report_id)
        self.assertEqual(smb.list_reports(self.root, 2), [])

    def test_malformed_input_is_atomic(self):
        for value in ({}, [], {'Docs': []}, {'../Docs': {}}, {'Docs': {'../secret': file_info()}},
                      {'Docs': {'/secret': file_info()}}, {'Docs': {'a//b': file_info()}},
                      {'Docs': {'a': {'size': 12}}}, {'Docs': {'a': file_info(), 'a/b': file_info()}},
                      {'Docs': {'x': file_info(), 'x\\y': file_info()}},
                      {'Docs': {'a/b': file_info(), 'a\\b': file_info()}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.upload(value)
        for content in (b'not json', b'{"Docs":{},"Docs":{}}', b'{"Docs":{"x":NaN}}', b'\xff'):
            with self.assertRaises(ValueError):
                smb.parse_report(content)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_limits_and_no_partial_publication(self):
        from unittest.mock import patch
        with patch.object(smb, 'MAX_FILES', 1), self.assertRaises(ValueError):
            self.upload({'Docs': {'one': file_info(), 'two': file_info()}})
        with patch.object(smb, 'MAX_ENTRIES', 1), self.assertRaises(ValueError):
            self.upload({'Docs': {'folder/file': file_info()}})
        with patch.object(smb, 'MAX_BYTES', 2), self.assertRaises(ValueError):
            smb.parse_report(b'{"Docs":{}}')
        self.assertEqual(smb.list_reports(self.root, 1), [])

    def test_catalog_corruption_and_symlink_are_rejected(self):
        report = self.upload({'Docs': {'file': file_info()}})
        path = smb.report_dir(self.root, 1, report['id']) / 'catalog.sqlite3'
        path.write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError, 'повреждён'):
            smb.get_report(self.root, 1, report['id'])
        path.unlink(); path.symlink_to(self.root / 'elsewhere')
        with self.assertRaises(ValueError):
            smb.get_report(self.root, 1, report['id'])

    def test_project_file_copy_needs_no_scan_id_rewrite(self):
        import shutil
        report = self.upload({'Docs': {'note.txt': file_info()}})
        shutil.copytree(self.root / '1', self.root / '99')
        self.assertEqual(smb.get_report(self.root, 99, report['id']), report)
        self.assertEqual(smb.browse(self.root, 99, report['id'], 'Docs')['total'], 1)


class SmbApiTests(unittest.TestCase):
    """Exercise endpoint functions without production settings or multipart installation."""
    @classmethod
    def setUpClass(cls):
        import ast
        from types import SimpleNamespace
        from fastapi import Depends, File, Form, Header, HTTPException, Query, UploadFile
        from fastapi.responses import FileResponse
        from sqlalchemy.orm import Session
        from datetime import datetime, timezone
        import ipaddress
        source = Path(__file__).parents[1] / 'app/api/smb.py'
        nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef)]
        for node in nodes:
            node.decorator_list = []
        from app.schemas.smb import SmbStart, SmbAction
        from uuid import uuid4
        ns = dict(Header=Header, SmbAction=SmbAction, SmbStart=SmbStart, uuid4=uuid4, smb=smb, Path=Path, datetime=datetime, timezone=timezone, ipaddress=ipaddress,
                  Depends=Depends, File=File, Form=Form, HTTPException=HTTPException, Query=Query,
                  UploadFile=UploadFile, Session=Session, FileResponse=FileResponse,
                  Scan=object(), get_db=lambda: None, settings=SimpleNamespace(SCANS_DIR=''))
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(source), 'exec'), ns)
        cls.api = ns

    def test_host_binding_metadata_validation_upload_and_download(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from fastapi import HTTPException
        import io
        scan = SimpleNamespace(hosts=[SimpleNamespace(ip='192.0.2.1')])
        db = Mock(); db.get.return_value = scan
        with tempfile.TemporaryDirectory() as root:
            self.api['settings'].SCANS_DIR = root
            file = SimpleNamespace(filename='C:\\tmp\\host.json', file=io.BytesIO(json.dumps({'Docs': {'note.txt': file_info()}}).encode()))
            report = self.api['upload'](scan_id=1, host='192.0.2.1', account='LAB\\reader', source='source', author='Tester', observed_at='2026-11-06T15:00:00+03:00', file=file, db=db)
            self.assertEqual(report['filename'], 'host.json')
            self.assertEqual(report['observed_at'], '2026-11-06T12:00:00+00:00')
            self.assertEqual(self.api['reports'](1, db), [report])
            page = self.api['entries'](1, report['id'], 'Docs', '', '', 0, 100, db)
            self.assertEqual(page['items'][0]['name'], 'note.txt')
            response = self.api['original'](1, report['id'], db)
            self.assertEqual(Path(response.path).read_bytes(), file.file.getvalue())
            for host, account, date in [('192.0.2.99', '', ''), ('192.0.2.1', 'x\ny', ''), ('192.0.2.1', '', '2026-11-06T12:00')]:
                with self.assertRaises(HTTPException) as raised:
                    self.api['metadata_for'](scan, host, account, '', '', date, 'x.json')
                self.assertEqual(raised.exception.status_code, 422)
            db.get.return_value = None
            with self.assertRaises(HTTPException) as raised:
                self.api['reports'](999, db)
            self.assertEqual(raised.exception.status_code, 404)
