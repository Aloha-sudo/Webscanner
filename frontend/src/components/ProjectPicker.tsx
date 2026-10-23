import { uiText, t } from '../i18n/core';
import ProjectTransfer from './ProjectTransfer';
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Plus, Pencil, X, FolderOpen, Settings, Trash2 } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
type Dialog={kind:'project'|'part'|'renameProject'|'renamePart';id?:number;name:string};
export default function ProjectPicker(){
  const {projects,project,part,selection,select,refresh,loading,error,locked}=useProject();
  const [dialog,setDialog]=useState<Dialog|null>(null);const [name,setName]=useState('');const [busy,setBusy]=useState(false);const [notice,setNotice]=useState('');
  const menu=useRef<HTMLDetailsElement>(null);
  const open=(d:Dialog)=>{if(menu.current)menu.current.open=false;setName(d.name);setDialog(d);setNotice('');};
  useEffect(()=>{
    const close=(event:MouseEvent)=>{if(menu.current&&event.target instanceof Node&&!menu.current.contains(event.target))menu.current.open=false;};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&menu.current)menu.current.open=false;};
    document.addEventListener('mousedown',close);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',escape);};
  },[]);
  const deleteProject=async(deleteReports=false)=>{
    if(!project||busy||locked)return;
    setBusy(true);setNotice('');
    try{
      const {data:summary}=await axios.get<{report_count:number;networks:string[];active_count:number}>(`/api/catalog/projects/${project.id}/summary`,{timeout:15000});
      if(summary.active_count){setNotice(t("В проекте {v0} активных сканов. Сначала остановите их.", {
  v0: summary.active_count
}));return;}
      const text=deleteReports
        ? t("Удалить проект «{v0}» ВМЕСТЕ СО СКАНАМИ И ФАЙЛАМИ?\nОтчётов: {v1}. Все результаты и файлы будут удалены без возможности восстановления.", {
  v0: project.name,
  v1: summary.report_count
})
        : t("Удалить проект «{v0}», сохранив сканы?\n{v1} отчётов перейдут в «Без проекта». Результаты, исходные файлы и скриншоты сохранятся.", {
  v0: project.name,
  v1: summary.report_count
});
      if(!window.confirm(text))return;
      const {data}=await axios.delete<{deleted_reports:number;preserved_reports:number;cleanup_errors:number[]}>(`/api/catalog/projects/${project.id}`,{data:{expected_count:summary.report_count,delete_reports:deleteReports},timeout:30000});
      select({projectId:null,partId:null});if(menu.current)menu.current.open=false;await refresh();
      setNotice(deleteReports?t("Проект удалён. Удалено отчётов: {v0}.{v1}", {
  v0: data.deleted_reports,
  v1: data.cleanup_errors.length ? t(" Не удалось удалить файлы отчётов: {v0}.", {
    v0: data.cleanup_errors.join(', ')
  }) : ''
}):t("Проект удалён. Сохранено сканов: {v0}. Они доступны в общей истории без проекта.", {
  v0: data.preserved_reports
}));
    }catch(error){setNotice(axios.isAxiosError(error)?error.response?.data?.detail||t("Не удалось удалить проект"):t("Не удалось удалить проект"));}finally{setBusy(false);}
  };
  const save=async(e:React.FormEvent)=>{e.preventDefault();if(!dialog)return;setBusy(true);setNotice('');try{
    if(dialog.kind==='project'){const {data}=await axios.post('/api/catalog/projects',{name});await refresh();select({projectId:data.id,partId:null});}
    if(dialog.kind==='part'){const {data}=await axios.post(`/api/catalog/projects/${project?.id}/parts`,{name});await refresh();select({projectId:project?.id||null,partId:data.id});}
    if(dialog.kind==='renameProject'){await axios.patch(`/api/catalog/projects/${dialog.id}`,{name});await refresh();}
    if(dialog.kind==='renamePart'){await axios.patch(`/api/catalog/parts/${dialog.id}`,{name});await refresh();}
    setNotice(t("Каталог обновлён"));setDialog(null);
  }catch(e){setNotice(axios.isAxiosError(e)?e.response?.data?.detail||t("Не удалось сохранить"):t("Не удалось сохранить"));}finally{setBusy(false);}};
  const merge=async(id:number,target:number,count:number)=>{const origin=project?.parts.find(p=>p.id===id);const dest=project?.parts.find(p=>p.id===target);if(!window.confirm(t("Перенести {v0} отчётов из «{v1}» в «{v2}» и убрать лишнюю часть сети? Файлы и результаты сохранятся.", {
  v0: count,
  v1: origin?.name,
  v2: dest?.name
})))return;setBusy(true);try{await axios.post(`/api/catalog/parts/${id}/merge`,{target_part_id:target,expected_count:count});await refresh();if(selection.partId===id)select({projectId:project?.id||null,partId:target});setNotice(t("Части сети объединены, отчёты сохранены"));}catch(e){setNotice(axios.isAxiosError(e)?e.response?.data?.detail||t("Ошибка объединения"):t("Ошибка объединения"));}finally{setBusy(false);}};
  return <div className="project-workspace">
    <div className="project-controls"><FolderOpen size={18} className="text-accent"/>
      <label>{t("Проект")}<select aria-label={t("Текущий проект")} disabled={loading||busy||locked} value={selection.projectId||''} onChange={e=>select({projectId:Number(e.target.value)||null,partId:null})}><option value="">{t("Без проекта · разовый скан")}</option>{projects.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
      <label>{t("Часть сети")}<select aria-label={t("Текущая часть сети")} disabled={!project||busy||loading||locked} value={selection.partId||''} onChange={e=>select({projectId:selection.projectId,partId:Number(e.target.value)||null})}><option value="">{project?t("Выберите часть сети"):t("Сначала выберите проект")}</option>{project?.parts.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
      <details ref={menu} className="project-management"><summary><Settings size={15}/>{t("Управление проектом")}</summary><div className="project-management-panel">
        <div className="project-menu-heading"><h2>{t("Управление проектом")}</h2><button type="button" aria-label={t("Закрыть управление проектом")} onClick={()=>{if(menu.current)menu.current.open=false;}}><X size={17}/></button></div>
        <p className="project-menu-current">{project?.name||t("Проект не выбран")}</p>
        <div className="project-menu-actions"><button disabled={busy||loading||locked} className="report-button report-button-secondary" onClick={()=>open({kind:'project',name:''})}><Plus size={15}/>{t("Создать проект")}</button>{project&&<button disabled={busy||locked} className="report-button report-button-secondary" onClick={()=>open({kind:'renameProject',id:project.id,name:project.name})}><Pencil size={14}/>{t("Переименовать")}</button>}</div>
        <ProjectTransfer parentBusy={busy||loading}/>
        {project&&<><section className="project-menu-section"><div className="project-menu-heading"><h3>{t("Части сети")}</h3><button disabled={busy||loading||locked} className="project-small-button" onClick={()=>open({kind:'part',name:''})}><Plus size={14}/>{t("Добавить часть сети")}</button></div>
          {!project.parts.length&&<p className="text-xs text-gray-500">{t("Добавьте первую часть сети для сканов и отчётов.")}</p>}
          {project.parts.map(p=><div key={p.id} className="project-part-row"><span>{p.name}<small>{p.report_count} {t("отчётов")}</small></span><button className="project-small-button" disabled={busy||locked} aria-label={t("Переименовать {v0}", {
  v0: p.name
})} onClick={()=>open({kind:'renamePart',id:p.id,name:p.name})}><Pencil size={13}/></button><select aria-label={t("Объединить {v0}", {
  v0: p.name
})} disabled={busy||locked||project.parts.length<2} value="" onChange={e=>merge(p.id,Number(e.target.value),p.report_count)}><option value="">{t("Объединить с…")}</option>{project.parts.filter(n=>n.id!==p.id).map(n=><option key={n.id} value={n.id}>{n.name}</option>)}</select></div>)}
        </section><section className="project-menu-section"><h3>{t("Удаление проекта")}</h3><p className="text-xs text-gray-500">{t("По умолчанию сканы остаются в общей истории.")}</p><button disabled={busy||locked} className="scan-action-button danger project-delete-action" onClick={()=>deleteProject(false)}><Trash2 size={15}/>{t("Удалить проект, сохранить сканы")}</button><details className="project-delete-advanced"><summary>{t("Удаление вместе со сканами")}</summary><button disabled={busy||locked} className="scan-action-button danger" onClick={()=>deleteProject(true)}>{t("Удалить проект вместе со сканами и файлами")}</button></details></section></>}
        <p className="text-xs text-gray-500">{t("Переименование и объединение сохраняют отчёты.")}</p>
      </div></details>
    </div>
    <p className="project-save-target">{project?(part?t("Сохранить в: {v0} / {v1}", {
  v0: project.name,
  v1: part.name
}):t("Выберите часть сети перед запуском или загрузкой отчётов.")):t("Новые сканы сохраняются без проекта. Для карты сети выберите проект и часть сети.")}</p>
    {(error||notice)&&<p role="status" className="text-xs mt-2">{uiText(error || notice)}</p>}
    {dialog&&<div className="project-dialog-overlay" onClick={()=>{if(!busy)setDialog(null);}}><form role="dialog" aria-modal="true" aria-labelledby="project-dialog-title" className="project-dialog" onSubmit={save} onClick={e=>e.stopPropagation()}><div className="flex justify-between items-center"><h2 id="project-dialog-title" className="font-semibold">{dialog.kind==='project'?t("Новый проект"):dialog.kind==='part'?t("Новая часть сети"):t("Изменить название")}</h2><button type="button" disabled={busy||locked} aria-label={t("Закрыть")} onClick={()=>setDialog(null)}><X size={18}/></button></div><label className="block mt-4 text-sm">{t("Название")}<input autoFocus required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder={dialog.kind==='project'?t("Пентест компании А"):t("Офис / Серверный сегмент / Филиал")} /></label>{notice&&<p role="alert" className="text-sm mt-3">{uiText(notice)}</p>}<div className="flex justify-end gap-2 mt-5"><button type="button" className="report-button report-button-secondary" disabled={busy||locked} onClick={()=>setDialog(null)}>{t("Отмена")}</button><button disabled={busy||!name.trim()} className="report-button report-button-primary">{busy?t("Сохранение…"):dialog.kind.startsWith('rename')?t("Сохранить"):t("Создать")}</button></div></form></div>}
  </div>;
}
