from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, StatementError
from pydantic import BaseModel, Field
from app.models.scan import Project, Scan, NetworkPart
from app.core.config import settings
from app.core.db import get_db
from app.reports.project_archive import MAX_BYTES, export_project, read_archive, import_project

router = APIRouter(prefix='/api/project-transfer', tags=['project-transfer'])

@router.get('/{project_id}/export')
def download(project_id: int, db: Session = Depends(get_db)):
    try:
        content = export_project(db, project_id, settings.SCANS_DIR)
    except ValueError as exc: raise HTTPException(400, str(exc))
    except OSError: raise HTTPException(400, 'Не удалось прочитать файлы проекта')
    return StreamingResponse(content, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="project_{project_id}.zip"'})

@router.post('/import')
async def upload(file: UploadFile = File(...), preview: bool = Form(True), name: str = Form(''), db: Session = Depends(get_db)):
    try:
        content = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    try:
        payload, files = read_archive(content)
        if preview:
            dates = sorted(s['observed_at'] for s in payload['scans'] if s.get('observed_at'))
            return {'observed_from': dates[0] if dates else None, 'observed_to': dates[-1] if dates else None, 'name': payload['projects'][0]['name'], 'parts': len(payload['network_parts']), 'reports': len(payload['scans']), 'files': len(files)-2, 'bytes': sum(map(len, files.values()))}
        return {'project_id': import_project(db, payload, files, settings.SCANS_DIR, name)}
    except (ValueError, IntegrityError, StatementError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else 'Некорректные данные или конфликт названий в проекте')


class ProjectNotes(BaseModel):
    description: str = Field(default='', max_length=20000)
    map_view: dict | None = None

@router.get('/{project_id}/notes')
def notes(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, 'Проект не найден')
    return {'description': project.description or '', 'map_view': project.map_view}

@router.put('/{project_id}/notes')
def save_notes(project_id: int, payload: ProjectNotes, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, 'Проект не найден')
    if payload.map_view is not None:
        view = payload.map_view
        if set(view) - {'report_ids','source','whole_project','merge_parts','network_part_id'}: raise HTTPException(400, 'Неизвестные настройки карты')
        ids = view.get('report_ids', [])
        if not isinstance(ids, list) or len(ids)>50 or any(type(i) is not int for i in ids): raise HTTPException(400, 'Некорректный список отчётов')
        if any(type(view.get(k, False)) is not bool for k in ('whole_project','merge_parts')): raise HTTPException(400, 'Некорректные параметры адресации')
        part_id = view.get('network_part_id')
        if part_id is not None:
            if type(part_id) is not int or not db.query(NetworkPart).filter_by(id=part_id, project_id=project_id).first(): raise HTTPException(400, 'Часть сети должна принадлежать проекту')
        if not view.get('whole_project') and part_id is None and ids: raise HTTPException(400, 'Выберите часть сети')
        valid = {s.id for s in db.query(Scan).filter(Scan.project_id==project_id, Scan.id.in_(ids)).all()}
        if set(ids) != valid or (view.get('source') is not None and view['source'] not in ids): raise HTTPException(400, 'Отчёты должны принадлежать проекту')
    project.description = payload.description
    project.map_view = payload.map_view
    db.commit()
    return {'description': project.description, 'map_view': project.map_view}
