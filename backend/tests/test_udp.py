import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.db import Base
from app.core.ports import top_ports, top_tcp_ports
from app.core.process import ScanCancelled
from app.models.scan import Scan, ScanStatus, Port
from app.reports.parser import parse_report
from app.reports.visibility import build_visibility
from app.core.retry import retry_payload
from app.tasks import scan_tasks as tasks

XML = '''<nmaprun><host><status state="up"/><address addr="127.0.0.1" addrtype="ipv4"/>
<ports><port protocol="udp" portid="53"><state state="open" reason="udp-response"/><service name="domain"/></port>
<port protocol="udp" portid="161"><state state="open|filtered" reason="no-response"/><service name="snmp"/></port>
<port protocol="udp" portid="123"><state state="closed"/></port></ports></host>
<runstats><finished exit="success"/></runstats></nmaprun>'''

class UdpTests(unittest.TestCase):
    def setUp(self):
        # Existing test modules use minimal settings when pydantic-settings is absent.
        fixture = SimpleNamespace(UDP_TIMEOUT=1800, PORT_PROFILES={'udp_quick':'53,123,161'})
        patcher = patch.object(tasks, 'settings', fixture)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_grouped_silent_ports_are_preserved(self):
        xml = b'''<nmaprun><scaninfo protocol="udp" services="53,161"/>
        <host><status state="up"/><address addr="127.0.0.1" addrtype="ipv4"/>
        <ports><extraports state="open|filtered" count="2"><extrareasons reason="no-responses" count="2"/></extraports></ports></host></nmaprun>'''
        ports = parse_report(xml)['hosts'][0]['ports']
        self.assertEqual([(p['port'],p['state']) for p in ports], [(53,'open|filtered'),(161,'open|filtered')])
        with self.assertRaises(ValueError):
            parse_report(xml.replace(b'<scaninfo protocol="udp" services="53,161"/>', b''))

    def test_udp_frequency_list_does_not_use_tcp_ranking(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'services'
            path.write_text('ssh 22/tcp 0.99\ndns 53/udp 0.8\nntp 123/udp 0.9\n')
            self.assertEqual(top_ports(path, 1, 'udp'), '123')
            self.assertEqual(top_tcp_ports(path, 1), '22')

    def test_active_parser_and_import_preserve_uncertainty_and_protocol(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'nmap.xml'; path.write_text(XML)
            ports = tasks.parse_nmap(path)[0]['ports']
        self.assertEqual([(p['port'],p['state']) for p in ports], [(53,'open'),(161,'open|filtered')])
        imported = parse_report(XML.encode())
        self.assertEqual([(p['port'],p['state']) for p in imported['hosts'][0]['ports']], [(53,'open'),(161,'open|filtered')])
        again = parse_report(json.dumps(imported).encode())
        self.assertEqual(again['hosts'], imported['hosts'])

    def test_uncertain_udp_does_not_establish_host_or_service_visibility(self):
        report = {'id':1,'target':'127.0.0.1','project':'lab','network':'lab','source_host':'scanner',
                  'hosts':[{'ip':'127.0.0.1','ports':[{'port':161,'protocol':'udp','state':'open|filtered'}]}]}
        rows=build_visibility([report])['rows']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['cells'][0]['state'],'uncertain')

    def test_udp_scope_does_not_claim_tcp_was_tested(self):
        base = {'target':'127.0.0.1','project':'lab','network':'lab','source_host':'scanner'}
        tcp = dict(base, id=1, hosts=[{'ip':'127.0.0.1','ports':[{'port':53,'protocol':'tcp'}]}])
        udp = dict(base, id=2, scan_type='udp_quick', hosts=[], scope_confirmed=True,
                   scope_targets='127.0.0.1', scope_ports='53')
        row = next(r for r in build_visibility([tcp,udp])['rows'] if r['protocol']=='tcp')
        self.assertEqual(row['cells'][1]['state'], 'not_tested')

    def test_retry_keeps_udp_profile(self):
        scan=SimpleNamespace(target='127.0.0.1',scan_type='udp_custom',ports='53,161',speed='normal')
        self.assertEqual(retry_payload(scan).scan_type,'udp_custom')

    def test_udp_pipeline_persists_states_and_never_runs_tcp_or_web_tools(self):
        engine=create_engine('sqlite://')
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db, tempfile.TemporaryDirectory() as folder:
                scan=Scan(target='127.0.0.1',scan_type='udp_custom',status=ScanStatus.RUNNING)
                db.add(scan);db.commit()
                def execute(cmd, **kwargs):
                    self.assertEqual(cmd[0],'nmap')
                    self.assertIn('-sU',cmd)
                    self.assertNotIn('-sS',cmd)
                    self.assertEqual(cmd[cmd.index('-p')+1], '53,161')
                    Path(cmd[cmd.index('-oX')+1]).write_text(XML)
                    return '', '', 0
                with patch.object(tasks,'run_command',side_effect=execute) as run, patch.object(tasks,'ensure_active'):
                    result=tasks.run_udp_scan(db,scan,folder,'udp_custom','53,123,161','normal',{123})
                self.assertEqual(run.call_count,1)
                self.assertEqual(result['ports'],2)
                self.assertEqual(db.get(Scan,scan.id).status,ScanStatus.COMPLETED)
                self.assertEqual({p.state for p in db.query(Port)}, {'open','open|filtered'})
        finally:
            engine.dispose()

    def test_limits_exclusions_cancellation_and_timeout_fail_without_success(self):
        scan=SimpleNamespace(id=1,target='127.0.0.1',exclude_ips=None,exclude_hosts=None)
        with tempfile.TemporaryDirectory() as folder, patch.object(tasks,'update_scan'), patch.object(tasks,'run_command') as run:
            for profile,ports,blocked in [('udp_custom','1-1001',set()),('udp_custom','53',{53})]:
                with self.assertRaises(ValueError):
                    tasks.run_udp_scan(None,scan,folder,profile,ports,'normal',blocked)
            scan.target='10.0.0.0/16'
            with self.assertRaises(ValueError):
                tasks.run_udp_scan(None,scan,folder,'udp_quick',None,'normal',set())
            run.assert_not_called()
            scan.target='127.0.0.1'
            for error in (ScanCancelled(),RuntimeError('timeout')):
                run.side_effect=error
                with self.assertRaises(type(error)):
                    tasks.run_udp_scan(None,scan,folder,'udp_quick',None,'normal',set())
