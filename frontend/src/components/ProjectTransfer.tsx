import { uiText, t, formatDateTime, formatNumber } from '../i18n/core';
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Download, Upload, FileText } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import WorkspaceDialog from './WorkspaceDialog';
import { downloadFile } from '../utils/svgExport';

import type { SavedMapView } from '../context/ProjectContext';
export type { SavedMapView } from '../context/ProjectContext';
export default function ProjectTransfer({currentView,onRestore,parentBusy=false,onBusyChange}:{currentView?:SavedMapView|null;onRestore?:(view:SavedMapView)=>void;parentBusy?:boolean;onBusyChange?:(value:boolean)=>void}){
  const {project,refresh,select,setLocked,locked,mapTools}=useProject();
  currentView=currentView??mapTools?.view??null;
  onRestore=onRestore??mapTools?.restore;
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  parentBusy=parentBusy||!!locked&&!busy;
  const [notesOpen,setNotesOpen]=useState(false);
  const [file,setFile]=useState<File|null>(null),[name,setName]=useState('');
  const [preview,setPreview]=useState<{name:string;parts:number;reports:number;files:number;bytes:number;observed_from?:string;observed_to?:string}|null>(null);
  const [notice,setNotice]=useState('');
  const [description,setDescription]=useState('');
  const [savedView,setSavedView]=useState<SavedMapView|null>(null);
  const [notesReady,setNotesReady]=useState(false);
  useEffect(()=>{let active=true;setDescription('');setSavedView(null);setNotesReady(false);if(project)axios.get(`/api/project-transfer/${project.id}/notes`).then(({data})=>{if(active){setDescription(data.description);setSavedView(data.map_view);setNotesReady(true);}}).catch(()=>{if(active)setError(t("Не удалось загрузить описание проекта"));});return()=>{active=false;};},[project?.id]);
  const save=async()=>{if(!project)return;lock(true);setError('');try{const view=currentView||savedView;await axios.put(`/api/project-transfer/${project.id}/notes`,{description,map_view:view});setSavedView(view);setNotice(t("Описание и выбранные отчёты карты сохранены в проекте."));}catch(e){setError(failure(e));}finally{lock(false);}};
  const failure=(e:unknown)=>axios.isAxiosError(e)&&typeof e.response?.data?.detail==='string'?e.response.data.detail:t("Не удалось передать проект. Проверьте соединение и размер архива.");
  const lock=(value:boolean)=>{setBusy(value);setLocked(value);onBusyChange?.(value);};
  const inspect=async(chosen:File|null)=>{
    setFile(chosen);setPreview(null);setError('');if(!chosen)return;
    if(chosen.size>512*1024*1024){setError(t("Максимальный размер архива — 512 МБ"));return;}
    lock(true);
    try{const body=new FormData();body.append('file',chosen);body.append('preview','true');const {data}=await axios.post('/api/project-transfer/import',body,{timeout:600000});setPreview(data);setName(data.name);}
    catch(e){setError(failure(e));}finally{lock(false);}
  };
  const upload=async()=>{
    if(!file||!preview)return;lock(true);setError('');
    try{const body=new FormData();body.append('file',file);body.append('preview','false');body.append('name',name);const {data}=await axios.post('/api/project-transfer/import',body,{timeout:600000});await refresh();select({projectId:data.project_id,partId:null});setOpen(false);setFile(null);setPreview(null);setNotice(t("Проект «{v0}» импортирован. Выберите часть сети или просмотр всего проекта.", {
  v0: name
}));}
    catch(e){setError(failure(e));}finally{lock(false);}
  };
  const download=async()=>{
    if(!project)return;lock(true);setError('');setNotice('');
    try{const {data}=await axios.get(`/api/project-transfer/${project.id}/export`,{responseType:'blob',timeout:600000});downloadFile(data,`project_${project.id}.zip`,'application/zip');setNotice(t("Архив проекта подготовлен."));}
    catch(e){let detail=t("Не удалось выгрузить проект");if(axios.isAxiosError(e)&&e.response?.data instanceof Blob){try{detail=JSON.parse(await e.response.data.text()).detail||detail;}catch{}}setError(detail);}finally{lock(false);}
  };
  return <div className="project-transfer-actions">
    <button className="project-small-button" title={t("Экспорт выбранного проекта в ZIP")} disabled={busy||parentBusy||!project} onClick={download}><Download size={14}/>{busy?t("Обработка…"):t("Экспорт проекта")}</button>
    <button className="project-small-button" title={t("Импорт проекта из ZIP")} disabled={busy||parentBusy} onClick={()=>{setError('');setOpen(true);}}><Upload size={14}/>{t("Импорт проекта")}</button>
    <button className="project-small-button project-notes-button" title={t("Описание проекта")} aria-label={t("Описание проекта")} disabled={busy||parentBusy||!project} onClick={()=>setNotesOpen(true)}><FileText size={15}/>{t("Описание проекта")}</button>
    {(notice||error&&!open&&!notesOpen)&&<span className="project-transfer-notice" role="status">{uiText(error || notice)}<button aria-label={t("Скрыть сообщение проекта")} onClick={()=>{setError('');setNotice('');}}>×</button></span>}
    <WorkspaceDialog open={notesOpen} title={t("Описание проекта")} busy={busy} onClose={()=>setNotesOpen(false)}>
      <div className="project-notes-form"><label>{t("Цель обследования и выводы")}<textarea aria-label={t("Описание проекта")} rows={5} value={description} maxLength={20000} disabled={busy||parentBusy||!notesReady} onChange={e=>setDescription(e.target.value)}/></label>
      {error&&<p role="alert" className="report-alert">{uiText(error)}</p>}
      <div className="project-notes-footer"><button className="report-choice" disabled={busy||parentBusy||!savedView?.report_ids.length||!onRestore} title={onRestore?t("Открыть подготовленный набор отчётов"):t("Откройте страницу «Карта сети»")} onClick={()=>{if(savedView&&onRestore){onRestore(savedView);setNotesOpen(false);}}}>{t("Открыть сохранённую карту")}</button><button className="report-button report-button-primary" disabled={busy||parentBusy||!notesReady} onClick={async()=>{await save();}}>{t("Сохранить")}</button></div>
      {currentView&&<p className="project-notes-hint">{t("Вместе с описанием сохранятся выбранные отчёты и источник карты.")}</p>}
      {notice&&<p role="status" className="project-notes-hint">{uiText(notice)}</p>}
      </div>
    </WorkspaceDialog>
    <WorkspaceDialog open={open} title={t("Импорт проекта")} busy={busy} onClose={()=>setOpen(false)}>
      <p>{t("Будет создан отдельный проект. История и файлы сохранятся, сканирование не запускается. Лимит архива и распакованных данных — 512 МБ.")}</p>
      <input aria-label={t("Архив проекта")} type="file" accept=".zip,application/zip" disabled={busy||parentBusy} onChange={e=>inspect(e.target.files?.[0]||null)}/>
      {busy&&<p role="status">{t("Проверка и обработка архива…")}</p>}{error&&<p role="alert" className="report-alert">{uiText(error)}</p>}
      {preview&&<div className="space-y-3"><p>{t('Проект «{v0}»: частей сети — {v1}, отчётов — {v2}, файлов — {v3}. Объём: {v4} МБ.',{v0:preview.name,v1:formatNumber(preview.parts),v2:formatNumber(preview.reports),v3:formatNumber(preview.files),v4:formatNumber(preview.bytes/1024/1024,{minimumFractionDigits:1,maximumFractionDigits:1})})}</p>{preview.observed_from&&<p>{t("Время обследований:")} {formatDateTime(preview.observed_from)} — {preview.observed_to?formatDateTime(preview.observed_to):'—'}</p>}<label>{t("Название нового проекта")}<input aria-label={t("Название импортируемого проекта")} value={name} maxLength={120} disabled={busy||parentBusy} onChange={e=>setName(e.target.value)}/></label><button className="report-button report-button-primary" disabled={busy||parentBusy||!name.trim()} onClick={upload}>{t("Создать проект")}</button></div>}
    </WorkspaceDialog>
  </div>;
}
