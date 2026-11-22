"""Bounded TCP discovery, before any SMB credential is used."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import socket


def discover_targets(hosts, check_cancelled=lambda: None, connector=None):
    connector = connector or socket.create_connection
    def reachable(host):
        try:
            with connector((host, 445), timeout=0.8):
                return True
        except OSError:
            return False
    check_cancelled()
    reachable_set = set()
    with ThreadPoolExecutor(max_workers=min(32, len(hosts) or 1)) as pool:
        pending = {pool.submit(reachable, host): host for host in hosts}
        try:
            while pending:
                check_cancelled()
                done, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                for future in done:
                    host = pending.pop(future)
                    if future.result():
                        reachable_set.add(host)
        except BaseException:
            for future in pending:
                future.cancel()
            raise
    return [host for host in hosts if host in reachable_set]
