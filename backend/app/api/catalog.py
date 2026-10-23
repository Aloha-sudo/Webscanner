import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.config import settings
from app.core.catalog import clean_name, name_key, resolve_context
from app.models.scan import Project, NetworkPart, Scan, ScanStatus
from app.schemas.scan import CatalogName, MoveReports, TeamMetadata

router=APIRouter(prefix='/api/catalog',tags=['projects'])


def require(db, model, id):
    item=db.get(model,id)
    if item is None:
        raise HTTPException(404,'Запись каталога не найдена')
    return item


def save(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Такое название уже существует. Выберите существующую запись или другое название')


@router.get('')
def list_catalog(db:Session=Depends(get_db)):
    projects=db.query(Project).order_by(Project.name).all()
    parts=db.query(NetworkPart).order_by(NetworkPart.name).all()
    counts={}
    for id in db.query(Scan.network_part_id).all():
        counts[id[0]]=counts.get(id[0],0)+1
    return [{'id':p.id,'name':p.name,'parts':[{'id':n.id,'name':n.name,'report_count':counts.get(n.id,0)} for n in parts if n.project_id==p.id]} for p in projects]


@router.post('/projects',status_code=201)
def create_project(payload:CatalogName,db:Session=Depends(get_db)):
    try:
        name=clean_name(payload.name)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    item=Project(name=name,name_key=name_key(name));db.add(item);save(db);db.refresh(item)
    return {'id':item.id,'name':item.name}


@router.post('/projects/{id}/parts',status_code=201)
def create_part(id:int,payload:CatalogName,db:Session=Depends(get_db)):
    require(db,Project,id)
    try:
        name=clean_name(payload.name)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    item=NetworkPart(project_id=id,name=name,name_key=name_key(name));db.add(item);save(db);db.refresh(item)
    return {'id':item.id,'name':item.name}


@router.patch('/projects/{id}')
def rename_project(id:int,payload:CatalogName,db:Session=Depends(get_db)):
    item=require(db,Project,id)
    try:
        item.name=clean_name(payload.name);item.name_key=name_key(item.name)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    with db.no_autoflush:
        db.query(Scan).filter(Scan.project_id==id).update({'project':item.name},synchronize_session=False)
    save(db)
    return {'id':id,'name':item.name}


@router.patch('/parts/{id}')
def rename_part(id:int,payload:CatalogName,db:Session=Depends(get_db)):
    item=require(db,NetworkPart,id)
    try:
        item.name=clean_name(payload.name);item.name_key=name_key(item.name)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    with db.no_autoflush:
        db.query(Scan).filter(Scan.network_part_id==id).update({'network':item.name},synchronize_session=False)
    save(db)
    return {'id':id,'name':item.name}


@router.post('/move-reports')
def move_reports(payload:MoveReports,db:Session=Depends(get_db)):
    try:
        context=resolve_context(db,TeamMetadata(project_id=payload.project_id,network_part_id=payload.network_part_id),Project,NetworkPart)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    ids=set(payload.report_ids)
    scans=db.query(Scan).filter(Scan.id.in_(ids)).with_for_update().all()
    if len(scans)!=len(ids):
        raise HTTPException(404,'Часть отчётов не найдена')
    if any(s.status in (ScanStatus.RUNNING,ScanStatus.QUEUED) for s in scans):
        raise HTTPException(409,'Сначала остановите активные сканы')
    for s in scans:
        for k in ('project_id','network_part_id','project','network'):
            setattr(s,k,context[k])
    save(db)
    return {'moved':len(scans)}


class MergeParts(BaseModel):
    target_part_id:int=Field(...,ge=1)
    expected_count:int=Field(...,ge=0)


@router.post('/parts/{id}/merge')
def merge_part(id:int,payload:MergeParts,db:Session=Depends(get_db)):
    origin=require(db,NetworkPart,id);target=require(db,NetworkPart,payload.target_part_id)
    if origin.id==target.id or origin.project_id!=target.project_id:
        raise HTTPException(422,'Выберите другую часть сети в том же проекте')
    scans=db.query(Scan).filter(Scan.network_part_id==id).with_for_update().all()
    if len(scans)!=payload.expected_count:
        raise HTTPException(409,'Количество отчётов изменилось. Обновите каталог')
    if any(s.status in (ScanStatus.RUNNING,ScanStatus.QUEUED) for s in scans):
        raise HTTPException(409,'Сначала остановите активные сканы')
    for s in scans:
        s.network_part_id=target.id;s.network=target.name
    db.flush();db.delete(origin);save(db)
    return {'moved':len(scans),'target_part_id':target.id}


@router.get('/projects/{id}/summary')
def project_summary(id:int,db:Session=Depends(get_db)):
    project=require(db,Project,id)
    scans=db.query(Scan).filter(Scan.project_id==id).all()
    return {'project':project.name,'report_count':len(scans),'networks':[n.name for n in db.query(NetworkPart).filter(NetworkPart.project_id==id)],'active_count':sum(s.status in (ScanStatus.RUNNING,ScanStatus.QUEUED) for s in scans)}


class DeleteProject(BaseModel):
    delete_reports: bool = False
    expected_count:int=Field(...,ge=0)


@router.delete('/projects/{id}')
def delete_project(id:int,payload:DeleteProject,db:Session=Depends(get_db)):
    project=require(db,Project,id)
    from app.reports.deletion import remove_project_records
    try:
        ids=remove_project_records(db,project,NetworkPart,Scan,payload.expected_count,payload.delete_reports)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409,str(exc))
    errors=[]
    for scan_id in ids if payload.delete_reports else []:
        try:
            path=os.path.join(settings.SCANS_DIR,str(scan_id))
            if os.path.exists(path):shutil.rmtree(path)
        except OSError:errors.append(scan_id)
    return {'deleted_reports':len(ids) if payload.delete_reports else 0,'preserved_reports':0 if payload.delete_reports else len(ids),'cleanup_errors':errors}
