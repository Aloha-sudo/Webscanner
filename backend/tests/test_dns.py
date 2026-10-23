import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace, ModuleType

import dns.exception
import dns.resolver
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from app.core import dns_resolution as resolution
# Isolated settings avoid depending on the production pydantic-settings package
# or connecting to the deployment database in this SQLite fixture.
fixture_config = ModuleType('app.core.config')
fixture_config.settings = SimpleNamespace(DATABASE_URL='postgresql://scanner:scanner@localhost/scanner', REDIS_URL='redis://localhost/0', SCANS_DIR='/tmp')
import sys
try:
    import pydantic_settings
except ModuleNotFoundError:
    sys.modules.setdefault('app.core.config', fixture_config)
from app.core import dns_jobs as jobs
from app.core.db import Base
from app.core.migrations import migrate
from app.core.process import ScanCancelled
from app.models.scan import Scan, Host, Port, NetworkPart, Project, ScanStatus
from app.schemas.dns import DnsOptions
from app.core.retry import retry_payload
from app.reports.parser import parse_report


def host(ip, dns=False):
    return {'ip': ip, 'ports': [{'port': 53, 'protocol': 'tcp'}] if dns else []}


def answer(status='resolved', names=None):
    return {'status': status, 'names': names or (['files.office.test'] if status == 'resolved' else []), 'server': '10.0.0.53', 'transport': 'tcp'}


class DnsEngineTests(unittest.TestCase):
    def test_old_schema_migration_preserves_all_evidence(self):
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE scanner_schema_version (version INTEGER PRIMARY KEY)'))
            for version in (1,2,3,4,5,7):
                conn.execute(text('INSERT INTO scanner_schema_version VALUES (:version)'), {'version':version})
            conn.execute(text('CREATE TABLE scans (id INTEGER PRIMARY KEY, target TEXT)'))
            conn.execute(text('CREATE TABLE hosts (id INTEGER PRIMARY KEY, hostname TEXT)'))
            conn.execute(text('CREATE TABLE network_parts (id INTEGER PRIMARY KEY)'))
            conn.execute(text("INSERT INTO scans VALUES (42, 'existing')"))
            conn.execute(text("INSERT INTO hosts VALUES (1, 'original')"))
        migrate(engine);migrate(engine)
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT id,target FROM scans')).one(),(42,'existing'))
            self.assertEqual(conn.execute(text('SELECT hostname,dns_result FROM hosts')).one(),('original',None))
            self.assertEqual(conn.execute(text('SELECT dns_status FROM scans')).scalar(),'not_requested')
        engine.dispose()

    def test_validation(self):
        self.assertEqual(DnsOptions(server=' 10.0.0.53 ').server, '10.0.0.53')
        self.assertIsNone(DnsOptions(server=' ').server)
        for value in ['example.com', '10.0.0.1;id', '0.0.0.0', '224.0.0.1']:
            with self.assertRaises(ValueError): DnsOptions(server=value)
        with self.assertRaises(ValueError): DnsOptions(transport='https')

    def test_candidates_are_bounded_and_manual_never_falls_back(self):
        with patch.object(resolution, 'system_servers', return_value=['127.0.0.11', '10.0.0.53']):
            hosts = [host(f'10.0.0.{i}', True) for i in range(1, 20)]
            self.assertEqual(resolution.candidates(hosts, {'server': '10.9.0.53'}), [{'server': '10.9.0.53', 'source': 'manual'}])
            found = resolution.candidates(hosts, {}, {'server': '10.1.0.53'})
            self.assertLessEqual(len(found), 8)
            self.assertEqual(found[0]['source'], 'saved')
            blocked = resolution.candidates(hosts, {}, blocked_ports={53})
            self.assertTrue(all(s['source'] == 'system' for s in blocked))

    def test_negative_probe_is_valid_and_next_resolver_can_return_names(self):
        async def query(ip, server, transport):
            return {**answer('no_record' if server == '10.0.0.53' else 'resolved'), 'server': server}
        with patch.object(resolution, 'system_servers', return_value=[]):
            result = asyncio.run(resolution.resolve_hosts({'hosts': [host('10.0.0.53', True), host('10.0.0.54', True), host('10.0.0.20')], 'options': {}}, query=query))
        self.assertEqual(result['summary']['counts'], {'resolved': 3})
        self.assertEqual(result['hosts']['10.0.0.20']['server'], '10.0.0.54')
        self.assertEqual(result['summary']['remember']['server'], '10.0.0.54')

    def test_no_ptr_refused_timeout_remain_distinct_and_do_not_remember(self):
        for status in ('no_record', 'refused', 'unreachable', 'dns_error'):
            async def query(ip, server, transport): return answer(status)
            with patch.object(resolution, 'system_servers', return_value=[]):
                result = asyncio.run(resolution.resolve_hosts({'hosts': [host('10.0.0.20')], 'options': {'server': '10.0.0.53'}}, query=query))
            self.assertEqual(result['hosts']['10.0.0.20']['status'], status)
            self.assertIsNone(result['summary']['remember'])

    def test_time_budget_and_missing_dns(self):
        async def slow(*args): await asyncio.sleep(1)
        result = asyncio.run(resolution.resolve_hosts({'hosts': [host('10.0.0.20')], 'options': {'server': '10.0.0.53'}}, query=slow, budget=.01))
        self.assertTrue(result['summary']['budget_exceeded'])
        self.assertEqual(result['hosts']['10.0.0.20']['status'], 'budget_exceeded')
        with patch.object(resolution, 'system_servers', return_value=[]):
            result = asyncio.run(resolution.resolve_hosts({'hosts': [host('10.0.0.20')], 'options': {}}, query=slow))
        self.assertEqual(result['hosts']['10.0.0.20']['status'], 'no_server')

    def test_transport_auto_retries_tcp_but_tcp_never_uses_udp(self):
        resolver = SimpleNamespace(nameservers=[], resolve_address=AsyncMock(side_effect=[dns.exception.Timeout(), [SimpleNamespace(target='files.office.test.')]]))
        with patch('dns.asyncresolver.Resolver', return_value=resolver):
            result = asyncio.run(resolution.query_ptr('10.0.0.20', '10.0.0.53', 'auto'))
        self.assertEqual(result['names'], ['files.office.test'])
        self.assertEqual([call.kwargs['tcp'] for call in resolver.resolve_address.call_args_list], [False, True])
        resolver.resolve_address=AsyncMock(side_effect=dns.resolver.NXDOMAIN())
        with patch('dns.asyncresolver.Resolver', return_value=resolver):
            result = asyncio.run(resolution.query_ptr('10.0.0.20', '10.0.0.53', 'tcp'))
        self.assertEqual(result['status'], 'no_record')
        self.assertTrue(resolver.resolve_address.call_args.kwargs['tcp'])
        resolver.resolve_address.assert_awaited_once()

    def test_json_import_preserves_dns_and_original_name(self):
        data={'hosts':[{'ip':'10.0.0.20','hostname':'original','dns_result':answer(),'ports':[]}]}
        result=parse_report(json.dumps(data).encode(),'report.json')['hosts'][0]
        self.assertEqual(result['hostname'],'original')
        self.assertEqual(result['dns_result']['names'],['files.office.test'])
        data['hosts'][0]['dns_result']['names']=['bad\x00name']
        with self.assertRaises(ValueError):parse_report(json.dumps(data).encode(),'report.json')


class DnsJobTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.Db=sessionmaker(bind=self.engine)
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(jobs,'SessionLocal',self.Db),patch.object(jobs.settings,'SCANS_DIR',self.temp.name)]
        for item in self.patches:item.start()
        with self.Db() as db:
            db.add(Project(id=1,name='Lab',name_key='lab'))
            db.add(NetworkPart(id=1,project_id=1,name='Office',name_key='office'))
            scan=Scan(id=1,target='10.0.0.20',status=ScanStatus.COMPLETED,network_part_id=1,project_id=1)
            self.token=jobs.new_dns_job(scan,{'enabled':True,'server':'10.0.0.53','transport':'tcp'})
            db.add(scan);db.add(Host(scan_id=1,ip='10.0.0.20',hostname='existing-name'));db.commit()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup();self.engine.dispose()

    def output(self, cmd, **kwargs):
        kwargs['check_cancelled']()
        payload=json.loads(Path(cmd[-2]).read_text())
        self.assertEqual(payload['options']['server'],'10.0.0.53')
        Path(cmd[-1]).write_text(json.dumps({'hosts':{'10.0.0.20':answer()},'summary':{'counts':{'resolved':1},'remember':{'server':'10.0.0.53','transport':'tcp'}}}))

    def test_result_persistence_preserves_original_status_and_hostname_and_deduplicates(self):
        with patch.object(jobs,'execute',side_effect=self.output) as execute:
            jobs.run_dns_job(1,self.token);jobs.run_dns_job(1,self.token)
            execute.assert_called_once()
        with self.Db() as db:
            scan=db.get(Scan,1)
            self.assertEqual(scan.status,ScanStatus.COMPLETED)
            self.assertEqual(scan.dns_status,'completed')
            self.assertEqual(scan.hosts[0].hostname,'existing-name')
            self.assertEqual(scan.hosts[0].dns_result['names'],['files.office.test'])
            self.assertEqual(db.get(NetworkPart,1).dns_defaults['server'],'10.0.0.53')
            self.assertEqual(retry_payload(scan).dns_options.server,'10.0.0.53')

    def test_stale_token_does_not_run(self):
        with patch.object(jobs,'execute') as execute:
            jobs.run_dns_job(1,'old-token');execute.assert_not_called()

    def test_failure_is_nonfatal_for_scan(self):
        with patch.object(jobs,'execute',side_effect=RuntimeError('timeout')), self.assertLogs('app.core.dns_jobs', level='ERROR'):
            jobs.run_dns_job(1,self.token)
        with self.Db() as db:
            scan=db.get(Scan,1)
            self.assertEqual(scan.status,ScanStatus.COMPLETED)
            self.assertEqual(scan.dns_status,'failed')

    def test_cancellation_prevents_persistence(self):
        def cancel():raise ScanCancelled()
        with patch.object(jobs,'execute',side_effect=self.output):
            with self.assertRaises(ScanCancelled):jobs.run_dns_job(1,self.token,check_cancelled=cancel)
        with self.Db() as db:
            self.assertEqual(db.get(Scan,1).dns_status,'cancelled')
            self.assertIsNone(db.get(Scan,1).hosts[0].dns_result)

    def test_manual_endpoint_rejects_active_duplicates_and_handles_queue_failure(self):
        from fastapi import HTTPException
        from app.api.dns import resolve_names
        with self.Db() as db:
            with self.assertRaises(HTTPException) as error:resolve_names(1,DnsOptions(),db)
            self.assertEqual(error.exception.status_code,409)
            scan=db.get(Scan,1);scan.dns_status='completed';db.commit()
            with patch('app.api.dns.resolve_scan_dns.delay',side_effect=RuntimeError('offline')):
                with self.assertRaises(HTTPException) as error:resolve_names(1,DnsOptions(),db)
            self.assertEqual(error.exception.status_code,503)
            self.assertEqual(db.get(Scan,1).status,ScanStatus.COMPLETED)
            self.assertEqual(db.get(Scan,1).dns_status,'failed')
            with patch('app.api.dns.resolve_scan_dns.delay') as delay:
                result=resolve_names(1,DnsOptions(server='10.0.0.53'),db)
                self.assertEqual(result.dns_status,'queued');delay.assert_called_once()

    def test_migration_adds_only_columns_and_is_repeatable(self):
        migrate(self.engine);migrate(self.engine)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT hostname FROM hosts')).scalar(),'existing-name')
        self.assertIn('dns_result',{c['name'] for c in inspect(self.engine).get_columns('hosts')})
