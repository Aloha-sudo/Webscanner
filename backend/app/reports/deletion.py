def validate_project_deletion(scans, expected_count):
    if not scans:
        raise ValueError('Проект не найден или в нём нет отчётов')
    if len(scans) != expected_count:
        raise ValueError('Состав проекта изменился. Обновите список и подтвердите удаление снова')
    if any(getattr(s.status, 'value', s.status) in ('running', 'queued') for s in scans):
        raise ValueError('В проекте есть активные сканы. Сначала остановите их')
    return [s.id for s in scans]


def remove_project_records(db, project, part_model, scan_model, expected_count, delete_reports=False):
    scans=db.query(scan_model).filter(scan_model.project_id==project.id).with_for_update().all()
    if len(scans)!=expected_count:
        raise ValueError('Количество отчётов изменилось. Обновите каталог')
    if any(getattr(s.status,'value',s.status) in ('running','queued') for s in scans):
        raise ValueError('Сначала остановите активные сканы')
    ids=[s.id for s in scans]
    for scan in scans:
        if delete_reports:
            db.delete(scan)
        else:
            scan.project_id=None
            scan.network_part_id=None
            scan.project=None
            scan.network=None
    db.flush()
    for part in db.query(part_model).filter(part_model.project_id==project.id):
        db.delete(part)
    db.flush()
    db.delete(project)
    db.commit()
    return ids
