"""Build-time contract check with fictional data; never touches a share."""
from importlib.metadata import version
from snaffler import Snaffler

assert version('snaffler-ng')=='1.5.13'
engine=Snaffler(max_read_bytes=2048)
check=engine.check_file('//192.0.2.1/Demo/app.config',size=64,mtime_epoch=0.0)
assert check.status.name in ('DISCARD','SNAFFLE','MATCHED','NEEDS_CONTENT','CHECK_KEYS','PEEK_ARCHIVE')
if check.status.name in ('NEEDS_CONTENT','CHECK_KEYS','PEEK_ARCHIVE'):
    engine.scan_content(b'password="fictional-contract-fixture"',prior=check)
print('PASS: pinned snaffler-ng library contract')
