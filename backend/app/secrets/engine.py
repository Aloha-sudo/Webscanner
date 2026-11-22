"""Adapter to pinned snaffler-ng. Engine output stays in memory, never logs."""
from importlib.metadata import version,PackageNotFoundError

VERSION='1.5.13'

def available():
    try:return version('snaffler-ng')==VERSION
    except PackageNotFoundError:return False

class Detector:
    def __init__(self,engine=None):
        if engine is None:
            if not available():raise ValueError('secret_engine_unavailable')
            from snaffler import Snaffler
            engine=Snaffler(max_read_bytes=2*1024*1024)
        self.engine=engine

    def check(self,path,size):return self.engine.check_file(path,size=size,mtime_epoch=0.0)

    def needs_bytes(self,check):return check.status.name in ('NEEDS_CONTENT','CHECK_KEYS','PEEK_ARCHIVE')

    def result(self,check,data=None):
        result=self.engine.scan_content(data,prior=check) if data is not None else (check.result or getattr(check,'_best_result',None))
        if result is None:return None
        # Persist only classification, never match/context which may contain credentials.
        triage=getattr(result.triage,'label',getattr(result.triage,'name','Unknown'))
        return {'rule':str(result.rule_name)[:200],'severity':str(triage)[:20],
                'kind':'content' if data is not None and result is not getattr(check,'_best_result',None) else 'name',
                'evidence':'[redacted]'}
