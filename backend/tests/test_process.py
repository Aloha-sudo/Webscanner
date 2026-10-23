import sys
import tempfile
import time
import unittest
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from app.core.process import execute, ScanCancelled
from app.core.ports import top_tcp_ports
from app.core.migrations import migrate


class ProcessTests(unittest.TestCase):
    def test_failure_not_empty_success(self):
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            execute([sys.executable, '-c', 'import sys; sys.stderr.write("broken"); sys.exit(2)'])

    def test_success_and_timeout(self):
        self.assertEqual(execute([sys.executable, '-c', 'print("ok")'])[0].strip(), 'ok')
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            execute([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=.15)

    def test_cancel_running_process(self):
        start = time.monotonic()
        def check():
            if time.monotonic() - start > .15:
                raise ScanCancelled()
        with self.assertRaises(ScanCancelled):
            execute([sys.executable, '-c', 'import time; time.sleep(20)'], check_cancelled=check)
        self.assertLess(time.monotonic()-start, 2)

    def test_top_ports_frequency_not_numeric_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'services'
            path.write_text('http 80/tcp 0.9\nrdp 3389/tcp 0.8\ndns 53/udp 1.0\nftp 21/tcp 0.1\n')
            self.assertEqual(top_tcp_ports(path, 2), '80,3389')

    def test_top100_is_subset_of_top1000(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'services'
            path.write_text(''.join(f'service{i} {10000+i}/tcp {i/2000}\n' for i in range(1,1001)))
            small=top_tcp_ports(path,100).split(',')
            large=top_tcp_ports(path,1000).split(',')
            self.assertEqual(len(small),100)
            self.assertEqual(len(large),1000)
            self.assertEqual(small,large[:100])
            self.assertTrue(all(int(port)>1000 for port in small))

    def test_migration_keeps_existing_rows_and_is_idempotent(self):
        engine = create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE ports (id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE scans (id INTEGER PRIMARY KEY, target VARCHAR(255))'))
            conn.execute(text("INSERT INTO scans VALUES (1, 'existing')"))
        migrate(engine); migrate(engine)
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT target,speed FROM scans')).one(), ('existing','normal'))
            self.assertEqual(conn.execute(text('SELECT count(*) FROM scanner_schema_version')).scalar(),8)
        self.assertIn('comment', {c['name'] for c in inspect(engine).get_columns('scans')})
        self.assertIn('retry_of_id', {c['name'] for c in inspect(engine).get_columns('scans')})
        self.assertFalse(inspect(engine).has_table('observation_shares'))
