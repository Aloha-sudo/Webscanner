"""Native snaffler-ng process: credentials on stdin, never CLI arguments."""
import ctypes
import json
import logging
import os
from pathlib import Path
import signal
import sys
from app.secrets.engine import available
from app.secrets.native import run_native
from app.secrets.store import write

def main():
    os.umask(0o077);logging.disable(logging.CRITICAL)
    payload=json.load(sys.stdin);path=Path(sys.argv[1])
    if sys.platform.startswith('linux'):
        ctypes.CDLL(None).prctl(1,signal.SIGKILL)
        if os.getppid()!=payload.get('parent_pid',os.getppid()):return
    try:
        if not available():raise ValueError('secret_engine_unavailable')
        result=run_native(payload['options'],payload['secret'],path,tuning=payload.get('tuning',{}),fast=payload.get('fast',True),max_depth=payload.get('max_depth'),share_names=payload.get('share_names',[]),exclude_shares=payload.get('exclude_shares',[]))
    except Exception:result={'status':'failed','error':'secret_engine_error'}
    write(path,result,'result.json')
if __name__=='__main__':main()
