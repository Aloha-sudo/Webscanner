import unittest
from unittest.mock import patch
from app.core.queue_dependencies import check_queue_dependencies


class QueueDependenciesTests(unittest.TestCase):
    def test_real_redis_transport_loads_without_network_or_environment(self):
        with patch('socket.socket.connect', side_effect=AssertionError('Must not connect')):
            versions = check_queue_dependencies()
        self.assertEqual(set(versions), {'celery', 'kombu', 'redis'})

    def test_incompatible_client_version_is_detected_without_a_broker(self):
        from kombu.exceptions import VersionMismatch
        with patch('kombu.transport.redis.redis.VERSION', (0, 0, 0)):
            with self.assertRaises(VersionMismatch):
                check_queue_dependencies()
