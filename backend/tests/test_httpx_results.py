import unittest
from app.reports.httpx_results import normalize_result
class HttpxTests(unittest.TestCase):
    def test_domain_record_retains_url_and_matches_scanned_address(self):
        url = 'https://nextcloud.example.com:443'
        result = normalize_result({'url': url, 'host': 'nextcloud.example.com', 'a': ['192.168.1.152']})
        self.assertEqual(result['url'], url)
        self.assertEqual(result['ip'], '192.168.1.152')

    def test_domain_fallback_uses_unambiguous_scan_mapping(self):
        record = {'url': 'http://cloud.example.com:80', 'host': 'cloud.example.com'}
        self.assertEqual(normalize_result(record, {'cloud.example.com': ['192.168.1.152']})['ip'], '192.168.1.152')
        self.assertIsNone(normalize_result(record, {'cloud.example.com': ['192.168.1.152', '192.168.1.153']}))

    def test_cli_string_port_is_integer_for_database(self):
        result=normalize_result({'url':'https://192.168.1.163:8006','host':'192.168.1.163','port':'8006','status_code':200})
        self.assertEqual(result['port'],8006)
        self.assertEqual(result['ip'],'192.168.1.163')
        self.assertTrue(result['ssl'])
    def test_host_ip_and_long_titles(self):
        result=normalize_result({'url':'https://printer.local','host':'printer.local','host_ip':'192.168.1.5','title':'x'*600})
        self.assertEqual(result['ip'],'192.168.1.5')
        self.assertEqual(len(result['title']),500)
    def test_failed_records_and_invalid_ports_are_skipped(self):
        self.assertIsNone(normalize_result({'url':'http://192.168.1.1','failed':True}))
        self.assertIsNone(normalize_result({'url':'http://192.168.1.1','port':'70000'}))
