"""Build-time Redis transport compatibility check; no config, sockets or task dispatch."""
from importlib.metadata import version
from types import SimpleNamespace


def check_queue_dependencies():
    from kombu.transport.redis import Channel
    # Execute Kombu's own redis-py version check before connecting to a broker.
    # A memory:// broker never reaches this code, which hid VersionMismatch in tests.
    client_type = Channel._get_client(SimpleNamespace(global_keyprefix=''))
    client = client_type(host='127.0.0.1', port=6379)
    client.close()
    return {package: version(package) for package in ('celery', 'kombu', 'redis')}


if __name__ == '__main__':
    versions = check_queue_dependencies()
    print('PASS: Redis transport client loads without a connection; ' +
          ', '.join(f'{name}={value}' for name, value in versions.items()))
