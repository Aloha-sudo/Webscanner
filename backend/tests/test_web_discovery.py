import http.client
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.core.web_discovery import extract_urls, supplement_httpx


class WebTests(unittest.TestCase):
    def test_proxmox_wrong_nmap_name_checks_https_and_http(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'nmap.xml'
            p.write_text('<nmaprun><host><address addr="192.168.1.163" addrtype="ipv4"/><ports><port protocol="tcp" portid="8006"><state state="open"/><service name="wpl-analytics"/></port><port protocol="tcp" portid="22"><state state="open"/><service name="ssh"/></port></ports></host></nmaprun>')
            self.assertEqual(extract_urls(p,{8006}), ['https://192.168.1.163:8006','http://192.168.1.163:8006'])

    def test_fallback_saves_https_result_without_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'httpx.json'
            url='https://192.168.1.163:8006'
            record={'url':url,'host':'192.168.1.163','port':8006,'title':'Proxmox Virtual Environment','status_code':200}
            with patch('app.core.web_discovery.probe', return_value=record) as probe:
                self.assertEqual(supplement_httpx(p,[url,'http://192.168.1.163:8006']),[url])
                probe.assert_called_once_with(url)
                supplement_httpx(p,[url])
                probe.assert_called_once()

    def test_tls_bytes_on_http_do_not_abort_other_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'httpx.json'
            urls = ['http://192.168.1.163:8006', 'https://192.168.1.163:8006']
            record = {'url':urls[1], 'host':'192.168.1.163','port':8006,'status_code':200,'title':'Proxmox'}
            with patch('app.core.web_discovery.probe', side_effect=[http.client.BadStatusLine('\x15\x03\x03\x00\x02\x02'),record]):
                self.assertEqual(supplement_httpx(path,urls), [urls[1]])
                self.assertIn('Proxmox',path.read_text())
