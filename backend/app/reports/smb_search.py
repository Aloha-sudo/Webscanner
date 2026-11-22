"""Bounded local metadata search. Never connects to SMB or reads document contents."""
import json
import fnmatch
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from app.reports import smb

MAX_MATCHES = 50000
MAX_SECONDS = 10


def search_files(root, scan_id, query, offset=0, limit=100):
    smb.text(query, 200)
    query = query.strip().replace('\\', '/')
    if not query or not 0 <= offset <= MAX_MATCHES or not 1 <= limit <= 100:
        raise ValueError('Укажите имя, путь или маску файла')
    needle = query.casefold()
    wildcard = '*' in needle or '?' in needle
    pattern = re.compile(fnmatch.translate(needle.replace('[', '[[]'))) if wildcard else None
    def matches(path, name):
        return int(bool(pattern.fullmatch(path.casefold()) or pattern.fullmatch(name.casefold())) if pattern else needle in path.casefold())
    reports = smb.list_reports(root, scan_id)
    latest = {}
    for report in reports:
        latest.setdefault((report['host'], (report.get('account') or '').casefold(), report.get('auth_method')), report)
    reports = list(latest.values())
    hosts = {report['host'] for report in reports}
    covered = {report['host'] for report in reports if report.get('coverage') == 'files' or report.get('format') == 'netexec-spider-plus'}
    partial = any(report.get('partial') or report.get('limits') for report in reports if report['host'] in covered)
    scanned = 0
    truncated = False
    deadline = time.monotonic() + MAX_SECONDS
    # Disk-backed aggregation bounds memory, merges duplicate paths across accounts,
    # and retains which exact report supplied each hit. Temp data is removed on exit.
    with tempfile.TemporaryDirectory(prefix='webscanner-smb-search-') as temporary:
        connection = sqlite3.connect(Path(temporary) / 'results.sqlite3')
        try:
            connection.executescript('''
                CREATE TABLE files(host TEXT,share TEXT,path TEXT,entry TEXT,PRIMARY KEY(host,share,path));
                CREATE TABLE sources(host TEXT,share TEXT,path TEXT,report_id TEXT,account TEXT,
                    PRIMARY KEY(host,share,path,report_id));
            ''')
            for report in reports:
                if time.monotonic() >= deadline:
                    truncated = True
                    break
                try:
                    with smb.catalog(root, scan_id, report['id']) as catalog:
                        catalog.create_function('file_match', 2, matches)
                        catalog.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
                        rows = catalog.execute('SELECT share,path,parent,name,kind,metadata FROM entries WHERE kind=? AND file_match(path,name)', ['file'])
                        for row in rows:
                            if scanned >= MAX_MATCHES or time.monotonic() >= deadline:
                                truncated = True
                                break
                            entry = dict(row)
                            entry['metadata'] = json.loads(entry['metadata'])
                            key = (report['host'], entry['share'], entry['path'])
                            connection.execute('INSERT OR IGNORE INTO files VALUES (?,?,?,?)', (*key,json.dumps(entry,ensure_ascii=False)))
                            connection.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)', (*key,report['id'],report.get('account')))
                            scanned += 1
                except ValueError:
                    # A catalog can disappear/become unreadable during another user's cleanup.
                    # Keep other results but never present this as a complete search.
                    partial = True
                    truncated = time.monotonic() >= deadline
                except FileNotFoundError:
                    partial = True
                if truncated:
                    break
            total = connection.execute('SELECT count(*) FROM files').fetchone()[0]
            items = []
            for host, share, path, raw in connection.execute('SELECT host,share,path,entry FROM files ORDER BY host,share,path LIMIT ? OFFSET ?', [limit,offset]):
                sources = [{'report_id':rid,'account':account} for rid,account in connection.execute('SELECT report_id,account FROM sources WHERE host=? AND share=? AND path=? ORDER BY rowid',[host,share,path])]
                items.append({'host':host,'entry':json.loads(raw),'sources':sources})
            return {'items':items,'total':total,'offset':offset,'limit':limit,'partial':bool(partial or truncated),
                    'truncated':truncated,'hosts':len(hosts),'covered_hosts':len(covered)}
        finally:
            connection.close()
