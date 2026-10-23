#!/usr/bin/env python3
"""WebScanner operator CLI. Standard library only. Scans run on the server worker."""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class ApiError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


class Client:
    def __init__(self, url):
        self.url = url.rstrip('/')
        if not self.url.startswith(('http://', 'https://')):
            raise ApiError('URL должен начинаться с http:// или https://')

    def request(self, method, path, payload=None, raw=None, content_type=None):
        headers = {'Accept': 'application/json'}
        body = json.dumps(payload).encode() if payload is not None else raw
        if body is not None:
            headers['Content-Type'] = content_type or 'application/json'
        req = urllib.request.Request(self.url + '/api' + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                value = response.read()
                try:
                    return json.loads(value) if value else None
                except (ValueError, UnicodeDecodeError):
                    raise ApiError('Сервер вернул не JSON. Проверьте --url: нужен адрес WebScanner, без /api') from None
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get('detail', str(exc))
            except (ValueError, UnicodeDecodeError):
                detail = f'HTTP {exc.code}'
            raise ApiError(str(detail), exc.code) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApiError('Не удалось связаться с сервером: ' + str(exc)) from None


def key(value):
    return ' '.join(value.split()).casefold()


def context(client, project_name, part_name, create=False):
    if not project_name and not part_name:
        return {}
    if not project_name or not part_name:
        raise ApiError('Укажите вместе --project и --part')
    projects = client.request('GET', '/catalog')
    project = next((p for p in projects if key(p['name']) == key(project_name)), None)
    if project is None:
        if not create:
            raise ApiError('Проект не найден; создайте его или добавьте --create-missing')
        try:
            project = client.request('POST', '/catalog/projects', {'name': project_name})
            project['parts'] = []
        except ApiError as exc:
            if exc.status != 409:
                raise
            return context(client, project_name, part_name, create)
    part = next((n for n in project.get('parts', []) if key(n['name']) == key(part_name)), None)
    if part is None:
        if not create:
            raise ApiError('Часть сети не найдена; добавьте --create-missing')
        try:
            part = client.request('POST', f"/catalog/projects/{project['id']}/parts", {'name': part_name})
        except ApiError as exc:
            if exc.status != 409:
                raise
            return context(client, project_name, part_name, create=False)
    return {'project_id': project['id'], 'network_part_id': part['id']}


def wait_scan(client, scan, timeout):
    end = time.monotonic() + timeout
    while scan['status'] in ('queued', 'running'):
        if time.monotonic() >= end:
            raise ApiError(f"Время ожидания истекло. Скан #{scan['id']} продолжает выполняться")
        print(f"#{scan['id']} {scan['status']} · {scan['stage']} · {scan['progress']}%", file=sys.stderr)
        time.sleep(3)
        scan = client.request('GET', f"/scans/{scan['id']}")
    return scan


def run(args, client):
    if args.command == 'projects':
        if args.action == 'list':
            return client.request('GET', '/catalog')
        project = client.request('POST', '/catalog/projects', {'name': args.name})
        if args.part:
            project['part'] = client.request('POST', f"/catalog/projects/{project['id']}/parts", {'name': args.part})
        return project
    if args.command == 'scan':
        payload = {'target': args.target, 'scan_type': args.profile, 'speed': args.speed,
                   **context(client, args.project, args.part, args.create_missing)}
        for field in ('ports', 'comment', 'exclude_ips', 'exclude_hosts', 'exclude_ports'):
            if getattr(args, field):
                payload[field] = getattr(args, field)
        if args.source:
            payload['source_host'] = args.source
        if args.author:
            payload['author'] = args.author
        return client.request('POST', '/scans', payload)
    if args.command == 'scans':
        if args.action == 'list':
            q = {'limit': args.limit}
            if args.project:
                q['project'] = args.project
            return client.request('GET', '/scans?' + urllib.parse.urlencode(q))
        if args.action == 'status':
            return client.request('GET', f'/scans/{args.id}')
        if args.action == 'cancel':
            return client.request('POST', f'/scans/{args.id}/cancel')
        payload = {}
        for cli, api in [('target', 'target'), ('source', 'source_host'), ('profile', 'scan_type'), ('ports', 'ports'), ('speed', 'speed')]:
            if getattr(args, cli):
                payload[api] = getattr(args, cli)
        return client.request('POST', f'/scans/{args.id}/retry', payload)
    if args.command == 'reports':
        path = Path(args.file)
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ApiError('Нужен существующий файл размером до 20 МБ')
        import secrets
        boundary = 'webscanner-' + secrets.token_hex(16)
        metadata = context(client, args.project, args.part, args.create_missing)
        metadata.update(source_host=args.source, author=args.author)
        name = path.name.replace('"', '_').replace('\r', '_').replace('\n', '_')
        raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()
               + json.dumps(metadata).encode() + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
               + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
        return client.request('POST', '/scans/import', raw=raw, content_type='multipart/form-data; boundary=' + boundary)


def parser():
    p = argparse.ArgumentParser(description='WebScanner: проекты и сканы из терминала. Скан выполняет worker сервера.')
    p.add_argument('--url', default='http://localhost:3000', help='Адрес WebScanner, например http://192.0.2.10:3000')
    p.add_argument('--json', action='store_true', help='Структурированный JSON вместо краткого вывода')
    sub = p.add_subparsers(dest='command', required=True)
    projects = sub.add_parser('projects').add_subparsers(dest='action', required=True)
    projects.add_parser('list')
    create = projects.add_parser('create'); create.add_argument('name'); create.add_argument('--part')
    def context_args(q):
        q.add_argument('--project'); q.add_argument('--part'); q.add_argument('--create-missing', action='store_true')
        q.add_argument('--source'); q.add_argument('--author')
    def waiting(q):
        q.add_argument('--wait', action='store_true'); q.add_argument('--wait-timeout', type=int, default=3600)
    scan = sub.add_parser('scan'); scan.add_argument('target'); context_args(scan); waiting(scan)
    scan.add_argument('--profile', choices=['quick','top100','top1000','web','full','custom'], default='quick')
    scan.add_argument('--speed', choices=['normal','fast','hard'], default='normal')
    for field in ('ports','comment','exclude-ips','exclude-hosts','exclude-ports'): scan.add_argument('--'+field)
    scans = sub.add_parser('scans').add_subparsers(dest='action', required=True)
    listing = scans.add_parser('list'); listing.add_argument('--project'); listing.add_argument('--limit', type=int, default=50)
    for action in ('status','cancel','retry'):
        q = scans.add_parser(action); q.add_argument('id', type=int)
        if action == 'retry':
            waiting(q)
            for field in ('target','source','profile','ports','speed'): q.add_argument('--'+field)
    imports = sub.add_parser('reports').add_subparsers(dest='action', required=True)
    report = imports.add_parser('import'); report.add_argument('file'); context_args(report)
    return p


def print_result(result, client, as_json=False):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif isinstance(result, list):
        if not result:
            print('Проектов пока нет.')
        for project in result:
            print(f"#{project['id']}  {project['name']}")
            for part in project.get('parts', []):
                print(f"    #{part['id']}  {part['name']} · отчётов: {part.get('report_count', 0)}")
    elif isinstance(result, dict) and 'scans' in result:
        print(f"Отчётов: {result['total']}; показано: {len(result['scans'])}")
        for scan in result['scans']:
            print(f"#{scan['id']:<5} {scan['status']:<10} {scan['target']} · {scan.get('source_host') or 'источник не указан'}")
    elif isinstance(result, dict) and 'id' in result and 'target' in result:
        print(f"#{result['id']} · {result['status']} · {result['target']}")
        if result.get('retry_of_id'):
            print(f"Повтор скана #{result['retry_of_id']}")
        print(f"Этап: {result['stage']} · {result['progress']}%")
        print(f"Результат: {result.get('total_hosts', 0)} хостов · {result.get('total_ports', 0)} портов")
        print(f"{client.url}/scan/{result['id']}")
        if result.get('error_message'):
            print(result['error_message'], file=sys.stderr)
    elif isinstance(result, dict) and 'name' in result:
        print(f"Проект #{result['id']}: {result['name']}")
        if result.get('part'):
            print(f"Часть сети #{result['part']['id']}: {result['part']['name']}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        client = Client(args.url)
        result = run(args, client)
        if getattr(args, 'wait', False):
            result = wait_scan(client, result, args.wait_timeout)
        print_result(result, client, args.json)
        return 1 if isinstance(result, dict) and result.get('status') in ('failed','cancelled') else 0
    except (ApiError, OSError) as exc:
        print('Ошибка: ' + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Ожидание прервано; серверный скан не отменён.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
