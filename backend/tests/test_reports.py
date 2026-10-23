import json
import unittest
from app.reports.parser import parse_report
from app.reports.compare import compare_reports
from app.schemas.scan import ScanCreate
from pydantic import ValidationError


class ReportsTests(unittest.TestCase):
    def test_nmap_standard_doctype_ipv6_and_closed_ports(self):
        data = b'''<?xml version="1.0"?><!DOCTYPE nmaprun><nmaprun scanner="nmap"><host><status state="up"/><address addr="2001:db8::1" addrtype="ipv6"/><hostnames><hostname name="server"/></hostnames><ports><port protocol="tcp" portid="443"><state state="open"/><service name="https" product="nginx" version="1.2"/></port><port protocol="tcp" portid="22"><state state="closed"/></port></ports></host></nmaprun>'''
        result = parse_report(data)
        self.assertEqual(result['hosts'][0]['hostname'], 'server')
        self.assertEqual(result['hosts'][0]['ports'][0]['version'], 'nginx 1.2')
        self.assertEqual(len(result['hosts'][0]['ports']), 1)

    def test_fastscan_success_banners_and_ignored_failures(self):
        data = br'''2026/10/14 12:00:00.123456 INFO Scanning 3 ports on 10.0.0.1
2026/10/14 12:00:01.123456 SUCCESS 10.0.0.1:22 "SSH-2.0-OpenSSH_9.0\r\n"
2026/10/14 12:00:01.234567 FAIL 10.0.0.1:23 connection refused
2026/10/14 12:00:02.123456 SUCCESS 10.0.0.1:443 ""
2026/10/14 12:00:03.123456 ERROR 10.0.0.1:80 some error
'''
        report = parse_report(data)
        self.assertEqual(report['source'], 'fastscan')
        self.assertEqual([p['port'] for p in report['hosts'][0]['ports']], [22,443])
        self.assertEqual(report['hosts'][0]['ports'][0]['banner'], 'SSH-2.0-OpenSSH_9.0\r\n')

    def test_fastscan_ipv6_escapes_and_duplicate(self):
        report = parse_report(br'SUCCESS [2001:db8::1]:80 "hello\x00\tworld"' + b'\n' + br'SUCCESS [2001:db8::1]:80 "hello\x00\tworld"')
        self.assertEqual(len(report['hosts'][0]['ports']), 1)
        self.assertEqual(report['hosts'][0]['ports'][0]['banner'], 'hello\\x00\tworld')
        with self.assertRaisesRegex(ValueError, 'имя хоста'):
            parse_report(b'SUCCESS example.com:22 "SSH"')

    def test_masscan_dedup_and_udp(self):
        rows = [{'ip':'10.0.0.1', 'ports':[{'port':53,'proto':'udp','status':'open'}]},
                {'ip':'10.0.0.1', 'ports':[{'port':53,'proto':'udp','status':'open'}]}]
        result = parse_report(json.dumps(rows).encode())
        self.assertEqual(len(result['hosts']), 1)
        self.assertEqual(len(result['hosts'][0]['ports']), 1)
        self.assertEqual(result['hosts'][0]['ports'][0]['protocol'], 'udp')

    def test_rustscan_and_masscan_text_equivalence(self):
        a = parse_report(b'10.0.0.1 -> [22,80]\n10.0.0.1 -> [443]')
        b = parse_report(b'open tcp 22 10.0.0.1 123\nopen tcp 80 10.0.0.1 123\nDiscovered open port 443/tcp on 10.0.0.1')
        self.assertEqual(a['hosts'], b['hosts'])

    def test_gnmap_service_and_closed(self):
        report = parse_report(b'Host: 10.0.0.1 (srv) Ports: 22/open/tcp//ssh//OpenSSH 9/, 80/closed/tcp//http///')
        self.assertEqual(report['hosts'][0]['ports'][0]['version'], 'OpenSSH 9')
        self.assertEqual(len(report['hosts'][0]['ports']), 1)

    def test_csv_russian_and_utf16_hosts_only(self):
        result = parse_report('IP-адрес;Имя компьютера\n10.0.0.1;сервер'.encode('utf-16'))
        self.assertEqual(result['hosts'][0]['hostname'], 'сервер')
        self.assertEqual(result['hosts'][0]['ports'], [])

    def test_reject_entities_bad_ip_bad_port_empty_and_oversized(self):
        for data in (b'<!DOCTYPE nmaprun [<!ENTITY x "hello">]><nmaprun/>',
                     b'[]', b'not a report', b'10.0.0.999 -> [22]', b'10.0.0.1 -> [65536]',
                     b'x'*(20*1024*1024+1), b'{"hosts":[{"ip":"10.0.0.1", "ports":"bad"}]}'):
            with self.subTest(data=data[:80]), self.assertRaises(ValueError):
                parse_report(data)

    def test_compare_direction_and_protocol(self):
        a = parse_report(b'IP,port,protocol,service\n10.0.0.1,53,tcp,dns\n10.0.0.2,22,tcp,ssh')
        b = parse_report(b'IP,port,protocol,service\n10.0.0.1,53,udp,dns\n10.0.0.3,80,tcp,http')
        result = compare_reports(a,b)
        self.assertEqual(result['added_hosts'][0]['ip'], '10.0.0.3')
        self.assertEqual(result['removed_hosts'][0]['ip'], '10.0.0.2')
        self.assertEqual(result['changed_hosts'][0]['added_ports'][0]['protocol'], 'udp')
        self.assertEqual(result['changed_hosts'][0]['removed_ports'][0]['protocol'], 'tcp')
        same = compare_reports(a,a)
        self.assertEqual(same['unchanged_hosts'], 2)
        self.assertFalse(same['changed_hosts'])

    def test_webscanner_json_keeps_web_metadata(self):
        row = {'ip':'10.0.0.1', 'ports':[{'port':443,'protocol':'tcp','url':'https://10.0.0.1:443','title':'Hello','status_code':200,'ssl':True}]}
        parsed = parse_report(json.dumps({'hosts':[row]}).encode())
        self.assertEqual(parsed['hosts'][0]['ports'][0]['web']['title'], 'Hello')
        self.assertEqual(parsed['hosts'][0]['ports'][0]['web']['status_code'], 200)

    def test_compare_service_version(self):
        a = {'hosts':[{'ip':'10.0.0.1','ports':[{'port':80,'protocol':'tcp','service':'http','version':'1'}]}]}
        b = {'hosts':[{'ip':'10.0.0.1','ports':[{'port':80,'protocol':'tcp','service':'http','version':'2'}]}]}
        self.assertEqual(compare_reports(a,b)['changed_hosts'][0]['changed_ports'][0]['fields'], {'version':{'before':'1','after':'2'}})

    def test_api_input_validation(self):
        ScanCreate(target='10.0.0.0/24', ports='22,80,8000-8100')
        ScanCreate(target='example.com')
        for target in ('', '-iL /etc/passwd', '1.2.3.999', '10.0.0.0/8', '::1', 'https://example.com'):
            with self.subTest(target=target), self.assertRaises(ValidationError):
                ScanCreate(target=target)
        for ports in ('0', '65536', '80-22', '22,,80', '1-999999999'):
            with self.subTest(ports=ports), self.assertRaises(ValidationError):
                ScanCreate(target='127.0.0.1', ports=ports)
