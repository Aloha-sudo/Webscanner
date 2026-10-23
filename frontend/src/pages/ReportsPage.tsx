import { t } from '../i18n/core';
import { useState } from 'react';
import { Upload } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import ReportTools from '../components/ReportTools';

export default function ReportsPage(){
  const {project,part,locked}=useProject();
  const [showUpload,setShowUpload]=useState(false);
  const [allProjects,setAllProjects]=useState(false);
  return <div className="reports-redesign space-y-5">
    <header className="reports-page-heading"><h1>{t("Отчёты и сравнение")}</h1><button className="report-button report-button-primary" disabled={locked} onClick={()=>setShowUpload(true)}><Upload size={16}/>{t("Загрузить отчёты")}</button></header>
    <div className="reports-scope-bar"><span>{allProjects||!project?t("Отчёты всех проектов"):`${project.name}${part?` / ${part.name}`:t(" / Все части сети")}`}</span><label><input type="checkbox" disabled={locked} checked={allProjects} onChange={e=>setAllProjects(e.target.checked)}/>{t("Все проекты")}</label></div>
    <ReportTools allProjects={allProjects} showUpload={showUpload} onCloseUpload={()=>setShowUpload(false)}/>
  </div>;
}
