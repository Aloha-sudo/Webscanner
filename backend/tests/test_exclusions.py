import ipaddress
import unittest
from pydantic import ValidationError
from app.schemas.scan import ScanCreate
from app.core.exclusions import allowed_targets, excluded_ports, validate_addresses, validate_hosts
class ExclusionTests(unittest.TestCase):
    def test_ip_and_cidr_removed_before_scan(self):
        self.assertEqual(allowed_targets('192.168.1.0/29','192.168.1.2,192.168.1.4/30'), ['192.168.1.1','192.168.1.3'])
    def test_all_resolved_addresses_of_host_excluded(self):
        resolver=lambda name:[ipaddress.ip_address('192.168.1.2'),ipaddress.ip_address('192.168.1.3')]
        self.assertEqual(allowed_targets('192.168.1.0/29',exclude_hosts='printer.local',resolver=resolver),['192.168.1.1','192.168.1.4','192.168.1.5','192.168.1.6'])
    def test_empty_and_unresolved_targets_fail(self):
        with self.assertRaisesRegex(ValueError,'Все целевые'):
            allowed_targets('192.168.1.1','192.168.1.1')
        with self.assertRaisesRegex(ValueError,'не найдены'):
            allowed_targets('192.168.1.0/24',exclude_hosts='unknown.local',resolver=lambda name:[])
    def test_ports_dedup_ranges_and_validation(self):
        self.assertEqual(excluded_ports('22, 9100\n8000-8002;22'),{22,9100,8000,8001,8002})
        for value in ('0','65536','80-22','--help','1-65535'):
            with self.subTest(value=value),self.assertRaises(ValueError):excluded_ports(value)
    def test_api_validation_and_normalization(self):
        scan=ScanCreate(target='192.168.1.0/24',exclude_ips='192.168.1.2\n192.168.2.0/24',exclude_hosts='Printer.LOCAL',exclude_ports='22; 9100')
        self.assertEqual(scan.exclude_ips,'192.168.1.2,192.168.2.0/24')
        self.assertEqual(scan.exclude_hosts,'printer.local')
        self.assertEqual(scan.exclude_ports,'22,9100')
        for field,value in [('exclude_ips','1.2.3.999'),('exclude_ips','::1'),('exclude_hosts','*.local'),('exclude_ports','70000')]:
            with self.subTest(field=field),self.assertRaises(ValidationError):ScanCreate(target='127.0.0.1',**{field:value})
