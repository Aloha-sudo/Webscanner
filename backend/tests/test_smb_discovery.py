import unittest
from app.core.smb_discovery import discover_targets
from app.core.process import ScanCancelled


class SmbDiscoveryTests(unittest.TestCase):
    def test_parallel_tcp_filter_keeps_target_order_without_authentication(self):
        class Socket:
            def __enter__(self): return self
            def __exit__(self,*args): pass
        calls=[]
        def connector(address,timeout):
            calls.append((address,timeout))
            if address[0]=='192.0.2.2':raise OSError('unreachable')
            return Socket()
        found=discover_targets(['192.0.2.1','192.0.2.2','192.0.2.3'],connector=connector)
        self.assertEqual(found,['192.0.2.1','192.0.2.3'])
        self.assertEqual(len(calls),3)
        self.assertTrue(all(address[1]==445 and timeout<1 for address,timeout in calls))

    def test_cancel_before_network(self):
        def check(): raise ScanCancelled()
        def connector(*args,**kwargs): raise AssertionError('No connections after cancellation')
        with self.assertRaises(ScanCancelled):discover_targets(['192.0.2.1'],check,connector)
