import { uiText, t } from '../i18n/core';
import { useState } from 'react';
import axios from 'axios';
import { useProject } from '../context/ProjectContext';
export default function MoveReportsDialog({ids,onClose,onMoved}:{ids:number[];onClose:()=>void;onMoved:()=>void}){
  const {projects,selection,refresh}=useProject();const [pid,setPid]=useState(selection.projectId||0);const [nid,setNid]=useState(0);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const project=projects.find(p=>p.id===pid);
  return <div className="project-dialog-overlay"><form className="project-dialog" role="dialog" aria-modal="true" aria-label={t("Перенос отчётов")} onSubmit={async e=>{e.preventDefault();if(!window.confirm(t("Перенести {v0} отчётов в «{v1} / {v2}»? Файлы сохранятся.", {
  v0: ids.length,
  v1: project?.name,
  v2: project?.parts.find(n => n.id === nid)?.name
})))return;setBusy(true);try{await axios.post('/api/catalog/move-reports',{report_ids:ids,project_id:pid,network_part_id:nid});await refresh();onMoved();}catch(e){setError(axios.isAxiosError(e)?e.response?.data?.detail||t("Ошибка переноса"):t("Ошибка переноса"));}finally{setBusy(false);}}}><h2 className="font-semibold">{t("Перенести выбранные отчёты (")}{ids.length})</h2><label className="block text-sm mt-4">{t("Проект")}<select value={pid||''} disabled={busy} onChange={e=>{setPid(Number(e.target.value));setNid(0);}}><option value="">{t("Выберите проект")}</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="block text-sm mt-3">{t("Часть сети")}<select value={nid||''} disabled={busy||!pid} onChange={e=>setNid(Number(e.target.value))}><option value="">{t("Выберите часть сети")}</option>{project?.parts.map(n=><option key={n.id} value={n.id}>{n.name}</option>)}</select></label><p className="text-xs text-gray-500 mt-3">{t("Меняется только принадлежность отчётов. Исходные файлы, результаты и источники сканирования сохраняются.")}</p>{error&&<p role="alert" className="text-sm text-red-400 mt-3">{uiText(error)}</p>}<div className="flex gap-2 justify-end mt-5"><button type="button" className="report-button report-button-secondary" disabled={busy} onClick={onClose}>{t("Отмена")}</button><button disabled={busy||!pid||!nid} className="report-button report-button-primary">{busy?t("Перенос…"):t("Перенести")}</button></div></form></div>;
}
