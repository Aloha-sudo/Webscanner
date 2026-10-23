"""Run scan tools with cancellation and bounded execution time."""
import os
import signal
import subprocess
import tempfile
import time


class ScanCancelled(Exception):
    pass


def execute(cmd, timeout=600, check_cancelled=lambda: None):
    check_cancelled()
    with tempfile.TemporaryFile(mode='w+') as out, tempfile.TemporaryFile(mode='w+') as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err, text=True, start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while proc.poll() is None:
                check_cancelled()
                if time.monotonic() >= deadline:
                    raise RuntimeError(f'{cmd[0]}: timeout after {timeout}s')
                time.sleep(0.1)
            check_cancelled()
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait()
        out.seek(0); err.seek(0)
        stdout, stderr = out.read(), err.read()
        if proc.returncode != 0:
            raise RuntimeError(f'{cmd[0]} failed ({proc.returncode}): {stderr[:500]}')
        return stdout, stderr, proc.returncode
