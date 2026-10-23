from types import SimpleNamespace
from datetime import datetime, timezone
import unittest
from app.core.retry import retry_payload


class RetryTests(unittest.TestCase):
    def original(self):
        return SimpleNamespace(target='10.0.0.0/24', scan_type='custom', ports='22,445',
                               comment='Office', speed='fast', exclude_ips='10.0.0.2',
                               exclude_hosts=None, exclude_ports='23', project_id=7,
                               network_part_id=8, source_host='10.0.0.1', author='Alex',
                               observed_at=datetime.now(timezone.utc), scope_targets='10.0.0.0/24',
                               scope_ports='22,445', scope_confirmed=True)

    def test_retry_preserves_execution_context_and_clears_past_evidence(self):
        old = self.original()
        new = retry_payload(old)
        self.assertEqual((new.project_id, new.network_part_id, new.source_host), (7, 8, '10.0.0.1'))
        self.assertEqual((new.ports, new.exclude_ips, new.exclude_ports), ('22,445', '10.0.0.2', '23'))
        self.assertIsNone(new.observed_at)
        self.assertIsNone(new.scope_targets)
        self.assertFalse(new.scope_confirmed)
        self.assertTrue(old.scope_confirmed)

    def test_explicit_overrides_are_validated(self):
        old = self.original()
        new = retry_payload(old, {'source_host': '10.0.0.3', 'target': '10.0.1.0/24'})
        self.assertEqual(new.source_host, '10.0.0.3')
        self.assertEqual(old.source_host, '10.0.0.1')
        with self.assertRaises(ValueError):
            retry_payload(old, {'target': 'bad target'})
