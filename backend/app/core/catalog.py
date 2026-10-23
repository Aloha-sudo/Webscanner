import re


def clean_name(value):
    value = re.sub(r'\s+', ' ', value or '').strip()
    if not value or len(value)>120 or '\x00' in value:
        raise ValueError('Название должно содержать от 1 до 120 символов')
    return value


def name_key(value):
    return clean_name(value).casefold()


def resolve_context(db, metadata, project_model, part_model):
    values=metadata.model_dump()
    project_id=values.get('project_id'); part_id=values.get('network_part_id')
    if project_id or part_id:
        project=db.get(project_model,project_id) if project_id else None
        part=db.get(part_model,part_id) if part_id else None
        if not project or not part or part.project_id!=project.id:
            raise ValueError('Выберите проект и принадлежащую ему часть сети')
    elif values.get('project') or values.get('network'):
        project=db.query(project_model).filter(project_model.name_key==name_key(values.get('project'))).first()
        part=db.query(part_model).filter(part_model.project_id==project.id,part_model.name_key==name_key(values.get('network'))).first() if project and values.get('network') else None
        if not project or not part:
            raise ValueError('Проект или часть сети отсутствует в каталоге. Выберите существующие или создайте их отдельной кнопкой')
    else:
        project=part=None
    values.update(project_id=project.id if project else None, network_part_id=part.id if part else None,
                  project=project.name if project else None, network=part.name if part else None)
    return values
