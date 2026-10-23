"""Portable, versioned project archives; no SQL or executable content is imported."""
import hashlib
import io
import ipaddress
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from sqlalchemy import DateTime, String, Integer, Boolean, JSON
from sqlalchemy.orm import selectinload
from app.core.catalog import clean_name, name_key
from app.models.scan import Project, NetworkPart, Scan, Host, Port, Service, Screenshot

MAX_BYTES = 512 * 1024 * 1024
MODELS = [Project, NetworkPart, Scan, Host, Port, Service, Screenshot]
RELATIONS = {NetworkPart: {'project_id': Project}, Scan: {'project_id': Project, 'network_part_id': NetworkPart}, Host: {'scan_id': Scan}, Port: {'host_id': Host}, Service: {'port_id': Port}, Screenshot: {'scan_id': Scan}}


def record(obj):
    result = {}
    for c in obj.__table__.columns:
        value = getattr(obj, c.name)
        if isinstance(value, datetime): value = value.isoformat()
        elif hasattr(value, 'value'): value = value.value
        result[c.name] = value
    return result


def export_project(db, project_id, root):
    project = db.get(Project, project_id)
    if not project: raise ValueError('Проект не найден')
    scans = db.query(Scan).options(
        selectinload(Scan.hosts).selectinload(Host.ports).selectinload(Port.service_obj),
        selectinload(Scan.screenshots),
    ).filter_by(project_id=project_id).order_by(Scan.id).all()
    if any(s.status in ('queued', 'running') or s.dns_status in ('queued', 'running') for s in scans):
        raise ValueError('Дождитесь завершения сканов и DNS-задач')
    parts = db.query(NetworkPart).filter_by(project_id=project_id).all()
    hosts = [h for s in scans for h in s.hosts]
    ports = [p for h in hosts for p in h.ports]
    objects = [ [project], parts, scans, hosts, ports, [p.service_obj for p in ports if p.service_obj], [i for s in scans for i in s.screenshots] ]
    payload = {m.__tablename__: [record(o) for o in items] for m, items in zip(MODELS, objects)}
    output = io.BytesIO(); checksums = {}; total = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        def put(name, content):
            nonlocal total
            if len(checksums) >= 19999: raise ValueError('Слишком много файлов проекта')
            total += len(content)
            if total > MAX_BYTES: raise ValueError('Проект превышает лимит 512 МБ')
            archive.writestr(name, content)
            checksums[name] = hashlib.sha256(content).hexdigest()
        put('project.json', json.dumps(payload, ensure_ascii=False).encode())
        put('README.txt', f'WebScanner: {project.name}\n{project.description or chr(32)}\nОтчётов: {len(scans)}\nИмпортируйте ZIP через «Импорт проекта». Никакие сканы при импорте не запускаются.\n'.encode())
        for scan in scans:
            directory = Path(root) / str(scan.id)
            if directory.is_symlink(): raise ValueError('Символические ссылки не поддерживаются')
            if directory.exists():
                for path in directory.rglob('*'):
                    if path.is_symlink(): raise ValueError('Символические ссылки не поддерживаются')
                    if path.is_file():
                        if path.stat().st_size > MAX_BYTES - total: raise ValueError('Проект превышает лимит 512 МБ')
                        put(f'files/{scan.id}/{path.relative_to(directory).as_posix()}', path.read_bytes())
        for shot in payload['screenshots']:
            prefix = f"local://scan_{shot['scan_id']}/"
            path = shot.get('minio_path') or ''
            filename = path[len(prefix):] if path.startswith(prefix) else ''
            if not filename or f"files/{shot['scan_id']}/screenshots/{filename}" not in checksums:
                raise ValueError('Отсутствует файл скриншота: восстановите его перед экспортом')
        manifest = json.dumps({'format': 'webscanner-project', 'version': 1, 'sha256': checksums})
        if total + len(manifest.encode()) > MAX_BYTES: raise ValueError('Проект превышает лимит 512 МБ')
        archive.writestr('manifest.json', manifest)
    if output.tell() > MAX_BYTES: raise ValueError('Архив превышает лимит 512 МБ')
    output.seek(0)
    return output


def read_archive(content):
    if len(content) > MAX_BYTES: raise ValueError('Архив превышает 512 МБ')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) > 20000 or len(set(names)) != len(names) or sum(i.file_size for i in infos) > MAX_BYTES:
                raise ValueError('Превышены лимиты архива или повторяются имена файлов')
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename or path.as_posix() != info.filename or info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Недопустимый путь в архиве')
            files = {name: archive.read(name) for name in names}
        manifest = json.loads(files.pop('manifest.json'))
        if manifest['format'] != 'webscanner-project' or manifest['version'] != 1: raise ValueError('Неизвестная версия архива')
        if {k: hashlib.sha256(v).hexdigest() for k,v in files.items()} != manifest['sha256']: raise ValueError('Контрольные суммы не совпадают')
        payload = json.loads(files['project.json'])
        if set(payload) != {m.__tablename__ for m in MODELS} or len(payload['projects']) != 1: raise ValueError('Некорректный состав проекта')
        ids = {}
        for model in MODELS:
            rows = payload[model.__tablename__]
            if not isinstance(rows, list): raise ValueError('Некорректные записи')
            ids[model] = set()
            for row in rows:
                if not isinstance(row, dict) or set(row) - set(model.__table__.columns.keys()): raise ValueError('Неизвестные поля проекта')
                if type(row.get('id')) is not int or row['id'] <= 0 or row['id'] in ids[model]: raise ValueError('Некорректные ID')
                for column in model.__table__.columns:
                    value = row.get(column.name)
                    if value is None:
                        if not column.nullable and column.name != 'id': raise ValueError(f'Отсутствует обязательное поле {column.name}')
                        continue
                    if isinstance(column.type, Boolean):
                        if type(value) is not bool: raise ValueError('Ожидается логическое значение')
                    elif isinstance(column.type, Integer):
                        if type(value) is not int or not -2147483648 <= value <= 2147483647: raise ValueError('Некорректное целое число')
                    elif isinstance(column.type, String):
                        if not isinstance(value, str) or '\x00' in value or (column.type.length and len(value)>column.type.length): raise ValueError('Некорректная строка')
                    elif isinstance(column.type, JSON):
                        if not isinstance(value, dict): raise ValueError('Некорректные JSON-метаданные')
                    elif isinstance(column.type, DateTime):
                        if not isinstance(value, str): raise ValueError('Некорректная дата')
                        datetime.fromisoformat(value)
                if model is Host: ipaddress.ip_address(row['ip'])
                if model is Port and (not 1 <= row['port'] <= 65535 or row.get('protocol') not in ('tcp','udp','sctp')): raise ValueError('Некорректный порт или протокол')
                if model is Project and row.get('map_view') is not None:
                    view = row['map_view']
                    if not isinstance(view, dict) or not isinstance(view.get('report_ids', []), list) or any(type(i) is not int for i in view.get('report_ids', [])):
                        raise ValueError('Некорректные настройки карты')
                    if view.get('source') is not None and type(view['source']) is not int: raise ValueError('Некорректный источник карты')
                    if view.get('network_part_id') is not None and type(view['network_part_id']) is not int: raise ValueError('Некорректная часть сети карты')
                ids[model].add(row['id'])
                for field, parent in RELATIONS.get(model, {}).items():
                    if row.get(field) is not None and row[field] not in ids[parent]: raise ValueError('Нарушены связи проекта')
                if model is Scan and (row.get('status') not in ('completed','failed','cancelled') or row.get('dns_status') in ('queued','running')): raise ValueError('Архив содержит активные задачи')
        part_projects = {p['id']: p['project_id'] for p in payload['network_parts']}
        for scan in payload['scans']:
            if scan.get('network_part_id') is not None and part_projects[scan['network_part_id']] != scan['project_id']: raise ValueError('Часть сети вне проекта')
            if scan.get('project_id') not in ids[Project]: raise ValueError('Скан вне проекта')
        for name in files:
            if name in ('project.json','README.txt'): continue
            path = PurePosixPath(name)
            if len(path.parts) < 3 or path.parts[0] != 'files' or path.parts[1] not in {str(i) for i in ids[Scan]}: raise ValueError('Файл вне проекта')
        for shot in payload['screenshots']:
            prefix = f"local://scan_{shot['scan_id']}/"
            path = shot.get('minio_path') or ''
            filename = path[len(prefix):] if path.startswith(prefix) else ''
            if not filename or '/' in filename or '\\' in filename or f"files/{shot['scan_id']}/screenshots/{filename}" not in files:
                raise ValueError('Некорректный или отсутствующий файл скриншота')
        return payload, files
    except (KeyError, TypeError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeError, RuntimeError, NotImplementedError, RecursionError) as exc:
        raise ValueError('Повреждённый архив проекта') from exc


def import_project(db, payload, files, root, name):
    name = clean_name(name or payload['projects'][0]['name'])
    if not name or len(name) > 120: raise ValueError('Укажите название до 120 символов')
    if db.query(Project).filter_by(name_key=name_key(name)).first(): raise ValueError('Проект с таким названием уже существует')
    maps = {}; created = []
    try:
        for model in MODELS:
            maps[model] = {}
            pending = []
            for original in payload[model.__tablename__]:
                values = dict(original); old = values.pop('id')
                for field, parent in RELATIONS.get(model, {}).items():
                    if values.get(field) is not None: values[field] = maps[parent][values[field]]
                for column in model.__table__.columns:
                    if isinstance(column.type, DateTime) and values.get(column.name): values[column.name] = datetime.fromisoformat(values[column.name])
                if model is Project: values.update(name=name, name_key=name_key(name))
                if model is NetworkPart: values['name_key'] = name_key(values['name'])
                if model is Scan:
                    values.update(project=name, dns_job_id=None, retry_of_id=None)
                obj = model(**values); db.add(obj); pending.append((old, obj))
            db.flush()
            maps[model] = {old: obj.id for old, obj in pending}
        imported_project = db.get(Project, maps[Project][payload['projects'][0]['id']])
        view = imported_project.map_view
        if view:
            imported_project.map_view = {
                'report_ids': [maps[Scan][i] for i in view.get('report_ids', []) if i in maps[Scan]],
                'source': maps[Scan].get(view.get('source')),
                'network_part_id': maps[NetworkPart].get(view.get('network_part_id')),
                'whole_project': bool(view.get('whole_project')),
                'merge_parts': bool(view.get('merge_parts')),
            }
        for original in payload['scans']:
            db.get(Scan, maps[Scan][original['id']]).retry_of_id = maps[Scan].get(original.get('retry_of_id'))
        for old, new in maps[Scan].items():
            directory = Path(root) / str(new)
            if directory.exists(): raise ValueError('Каталог нового скана уже существует')
            directory.mkdir(parents=True); created.append(directory)
            prefix = f'files/{old}/'
            for path, content in files.items():
                if path.startswith(prefix):
                    target = directory / path[len(prefix):]; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        for original in payload['screenshots']:
            shot = db.get(Screenshot, maps[Screenshot][original['id']])
            old_scan = original['scan_id']; path = original.get('minio_path') or ''
            prefix = f'local://scan_{old_scan}/'
            if not path.startswith(prefix) or '/' in path[len(prefix):] or '\\' in path[len(prefix):] or not path[len(prefix):]:
                raise ValueError('Некорректный путь скриншота')
            filename = path[len(prefix):]
            if f'files/{old_scan}/screenshots/{filename}' not in files:
                raise ValueError('В архиве отсутствует файл скриншота')
            shot.minio_path = f'local://scan_{maps[Scan][old_scan]}/{filename}'
        db.commit()
        return maps[Project][payload['projects'][0]['id']]
    except Exception:
        db.rollback()
        for directory in created: shutil.rmtree(directory)
        raise
