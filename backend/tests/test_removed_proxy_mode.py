"""Retired proxy requests must never silently become direct network scans."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base
from app.core.retry import retry_payload
from app.models.scan import Scan, ScanStatus
from app.schemas.scan import ScanCreate
from app.tasks import scan_tasks as tasks


class RemovedProxyTests(unittest.TestCase):
    def test_old_api_requests_are_rejected_and_proxy_is_not_a_supported_field(self):
        self.assertNotIn('proxy_options',ScanCreate.model_fields)
        for value in ({'host':'192.0.2.10','port':1080},{},'socks5://192.0.2.10:1080'):
            with self.subTest(value=value),self.assertRaisesRegex(ValidationError,'прокси удалено'):
                ScanCreate(target='192.0.2.20',proxy_options=value)
        self.assertEqual(ScanCreate(target='192.0.2.20').target,'192.0.2.20')

    def test_retired_report_cannot_be_retried_even_with_direct_overrides(self):
        old=SimpleNamespace(proxy_options={'host':'192.0.2.10','port':1080})
        for overrides in (None,{'proxy_options':None}):
            with self.assertRaisesRegex(ValueError,'прокси удалено'):
                retry_payload(old,overrides)

    def test_old_queued_tasks_fail_before_launching_any_network_tool(self):
        for metadata,flag in (({'host':'192.0.2.10','port':1080},False),(None,True)):
            with self.subTest(metadata=metadata,flag=flag),tempfile.TemporaryDirectory() as folder:
                engine=create_engine('sqlite://');Base.metadata.create_all(engine)
                sessions=sessionmaker(bind=engine)
                try:
                    with sessions() as db:
                        scan=Scan(target='192.0.2.20',status=ScanStatus.QUEUED,proxy_options=metadata)
                        db.add(scan);db.commit();scan_id=scan.id
                    with patch.object(tasks,'SessionLocal',sessions),patch.object(tasks,'settings',SimpleNamespace(SCANS_DIR=folder)),patch.object(tasks,'run_command') as run,patch.object(tasks,'execute') as execute,patch.object(tasks,'run_udp_scan') as udp,redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(RuntimeError,'прокси удалено'):
                            tasks.run_scan.run(scan_id,proxy_requested=flag)
                        run.assert_not_called();execute.assert_not_called();udp.assert_not_called()
                    with sessions() as db:
                        scan=db.get(Scan,scan_id)
                        self.assertEqual(scan.status,ScanStatus.FAILED)
                        self.assertIsNotNone(scan.finished_at)
                        self.assertIn('Импортируйте',scan.error_message)
                    self.assertFalse((Path(folder)/str(scan_id)/'nmap.xml').exists())
                finally:
                    engine.dispose()
