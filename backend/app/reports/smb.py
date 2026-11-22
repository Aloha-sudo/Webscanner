"""Immutable, per-report SMB metadata catalogs. No SMB connections or file downloads."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 100_000
MAX_ENTRIES = 200_000
INVALID = 'Некорректный JSON spider_plus'
LIMIT = 'SMB-отчёт превышает лимит: 20 МБ, 100000 файлов или 200000 записей'
MISSING = 'SMB-отчёт не найден'
DAMAGED = 'Каталог SMB повреждён. Повторно импортируйте исходный JSON'


def text(value, maximum=256):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(INVALID)
    return value


def relative_path(value):
    value = text(value, 2048).replace('\\', '/')
    parts = value.split('/')
    if not value or len(parts) > 64 or any(p in ('', '.', '..') or ':' in p for p in parts):
        raise ValueError(INVALID)
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(INVALID)
        result[key] = value
    return result


def parse_report(content):
    if len(content) > MAX_BYTES:
        raise ValueError(LIMIT)
    try:
        data = json.loads(content.decode('utf-8-sig'), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError(INVALID)))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(INVALID) from exc
    if not isinstance(data, dict) or not data or len(data) > 1024:
        raise ValueError(INVALID)
    entries = {}
    shares = []
    total = 0
    for share, files in data.items():
        text(share)
        if not share or any(c in share for c in '/\\:') or share in ('.', '..') or not isinstance(files, dict):
            raise ValueError(INVALID)
        shares.append({'name': share, 'files': len(files)})
        for raw_path, metadata in files.items():
            total += 1
            if total > MAX_FILES:
                raise ValueError(LIMIT)
            path = relative_path(raw_path)
            if not isinstance(metadata, dict) or set(metadata) != {'size', 'ctime_epoch', 'mtime_epoch', 'atime_epoch'}:
                raise ValueError(INVALID)
            # NetExec uses human_size/human_time strings despite the *_epoch names.
            for key, value in metadata.items():
                text(value, 128)
            parts = path.split('/')
            for index in range(1, len(parts) + 1):
                subpath = '/'.join(parts[:index])
                kind = 'file' if index == len(parts) else 'directory'
                key = (share, subpath)
                if key in entries:
                    if entries[key]['kind'] != kind or kind == 'file':
                        raise ValueError(INVALID)
                    continue
                entries[key] = {'share': share, 'path': subpath, 'parent': '/'.join(parts[:index-1]),
                                'name': parts[index-1], 'kind': kind,
                                'metadata': metadata if kind == 'file' else {}}
                if len(entries) > MAX_ENTRIES:
                    raise ValueError(LIMIT)
    return shares, list(entries.values())


def reports_root(root, scan_id):
    directory = Path(root) / str(scan_id) / 'smb'
    if any(p.is_symlink() for p in (directory, directory.parent)):
        raise ValueError(DAMAGED)
    return directory


def report_dir(root, scan_id, report_id):
    if not re.fullmatch(r'[a-f0-9]{32}', report_id):
        raise FileNotFoundError(MISSING)
    directory = reports_root(root, scan_id) / report_id
    if directory.is_symlink() or not directory.is_dir():
        raise FileNotFoundError(MISSING)
    return directory


def import_report(root, scan_id, content, metadata):
    shares, entries = parse_report(content)
    return store_report(root, scan_id, content, metadata, shares, entries)


def store_report(root, scan_id, content, metadata, shares, entries):
    directory = reports_root(root, scan_id)
    directory.mkdir(parents=True, exist_ok=True)
    report_id = uuid4().hex
    report = {**metadata, 'id': report_id, 'format': metadata.get('format', 'netexec-spider-plus'),
              'imported_at': datetime.now(timezone.utc).isoformat(),
              'sha256': hashlib.sha256(content).hexdigest(), 'shares': shares,
              'file_count': sum(s['files'] for s in shares),
              'directory_count': sum(e['kind'] == 'directory' for e in entries)}
    staging = Path(tempfile.mkdtemp(prefix='.import-', dir=directory))
    try:
        (staging / 'original.json').write_bytes(content)
        connection = sqlite3.connect(staging / 'catalog.sqlite3')
        try:
            connection.executescript('''
                CREATE TABLE report (version INTEGER NOT NULL, metadata TEXT NOT NULL);
                CREATE TABLE entries (share TEXT, path TEXT, parent TEXT, name TEXT,
                                      kind TEXT, search TEXT, metadata TEXT, PRIMARY KEY(share,path));
                CREATE INDEX children ON entries(share,parent,kind,name);
            ''')
            connection.execute('INSERT INTO report VALUES (1,?)', (json.dumps(report, ensure_ascii=False),))
            connection.executemany('INSERT INTO entries VALUES (?,?,?,?,?,?,?)',
                ((e['share'], e['path'], e['parent'], e['name'], e['kind'], e['path'].casefold(),
                  json.dumps(e['metadata'], ensure_ascii=False)) for e in entries))
            connection.commit()
        finally:
            connection.close()
        if (staging / 'catalog.sqlite3').stat().st_size > 256 * 1024 * 1024:
            raise ValueError(LIMIT)
        staging.rename(directory / report_id)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return report


@contextmanager
def catalog(root, scan_id, report_id):
    path = report_dir(root, scan_id, report_id) / 'catalog.sqlite3'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError(DAMAGED)
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA query_only=ON')
        # Bound work even if a project archive supplied a malformed catalog.
        budget = [0]
        def limit_work():
            budget[0] += 1
            return budget[0] > 20000
        connection.set_progress_handler(limit_work, 1000)
        yield connection
    except (sqlite3.Error, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(DAMAGED) from exc
    finally:
        if connection is not None:
            connection.close()


def get_report(root, scan_id, report_id):
    with catalog(root, scan_id, report_id) as connection:
        row = connection.execute('SELECT version,metadata FROM report').fetchone()
        if row is None or row['version'] != 1:
            raise ValueError(DAMAGED)
        report = json.loads(row['metadata'])
        if not isinstance(report, dict) or report.get('id') != report_id:
            raise ValueError(DAMAGED)
        return report


def list_reports(root, scan_id):
    directory = reports_root(root, scan_id)
    if not directory.exists():
        return []
    return sorted((get_report(root, scan_id, p.name) for p in directory.iterdir()
                   if re.fullmatch(r'[a-f0-9]{32}', p.name)), key=lambda r: r['imported_at'], reverse=True)


def browse(root, scan_id, report_id, share, parent='', query='', offset=0, limit=100):
    report = get_report(root, scan_id, report_id)
    if share not in {s['name'] for s in report['shares']}:
        raise FileNotFoundError('Шара отсутствует в SMB-отчёте')
    if parent:
        relative_path(parent)
    text(query, 200)
    if not 0 <= offset <= MAX_ENTRIES or not 1 <= limit <= 200:
        raise ValueError(INVALID)
    # Literal substring search, including Unicode; % and _ are not SQL wildcards.
    where, params = ('share=? AND instr(search,?)>0', [share, query.casefold()]) if query else ('share=? AND parent=?', [share, parent])
    with catalog(root, scan_id, report_id) as connection:
        folder = None
        if parent:
            row = connection.execute('SELECT share,path,parent,name,kind,metadata FROM entries WHERE share=? AND path=? AND kind=?', [share, parent, 'directory']).fetchone()
            if row is None:
                raise FileNotFoundError('Каталог отсутствует в SMB-отчёте')
            folder = {**dict(row), 'metadata': json.loads(row['metadata'])}
        total = connection.execute(f'SELECT count(*) FROM entries WHERE {where}', params).fetchone()[0]
        rows = connection.execute(f'SELECT share,path,parent,name,kind,metadata FROM entries WHERE {where} ORDER BY kind,name,path LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
        items = [{**dict(row), 'metadata': json.loads(row['metadata'])} for row in rows]
    return {'items': items, 'folder': folder, 'total': total, 'offset': offset, 'limit': limit}


def delete_reports(root, scan_id, report_ids):
    """Remove explicitly selected local catalogs, never remote SMB files."""
    if (not isinstance(report_ids, list) or not 1 <= len(report_ids) <= 10000
            or any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value) for value in report_ids)
            or len(set(report_ids)) != len(report_ids)):
        raise ValueError('Выберите SMB-результаты для удаления')
    # Resolve the entire selection before moving anything, including cross-scan IDs.
    paths = [report_dir(root, scan_id, value) for value in report_ids]
    trash = Path(tempfile.mkdtemp(prefix='.delete-', dir=reports_root(root, scan_id)))
    moved = []
    try:
        for path in paths:
            destination = trash / path.name
            path.rename(destination)
            moved.append((path, destination))
    except Exception:
        for original, destination in reversed(moved):
            destination.rename(original)
        trash.rmdir()
        raise
    shutil.rmtree(trash)
    return report_ids
