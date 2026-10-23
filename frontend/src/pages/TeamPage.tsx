import LocalDateTimeInput from '../components/LocalDateTimeInput';
import { validLocalDateTime } from '../utils/localDateTime';
import { uiText, t, formatDateTime } from '../i18n/core';
import type { SavedMapView } from '../context/ProjectContext';
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Upload, Network, Table2, Download, Trash2, RefreshCw, Route, ChevronDown } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import MoveReportsDialog from '../components/MoveReportsDialog';
import ImportNotice from '../components/ImportNotice';
import ObservedPaths from '../components/ObservedPaths';
import VisibilityMap from '../components/VisibilityMap';
import WorkspaceDialog from '../components/WorkspaceDialog';
import { initialSourceReport } from '../utils/observedPaths';
import type { Scan } from '../types';

type Cell = {report_id:number;state:string;service:string|null;version:string|null};
type Row = {device_id:string;network:string;ip:string;protocol:string;port:number;hostname:string|null;cells:Cell[]};
type Column = {network:string;id:number;target:string;source_host:string;author:string|null;observed_at:string|null;created_at:string;scope_confirmed:boolean};
type Visibility = {columns:Column[];rows:Row[];warnings:string[];merge_parts?:boolean};
type Queued = {file:File;source:string;author:string;observed:string;status:string;id?:number};
const states:Record<string,string> = {get found() {
  return t("Обнаружено");
},get unknown() {
  return t("Нет данных");
},get not_found() {
  return t("Не обнаружено");
},get not_tested() {
  return t("Не проверялось");
}};
const message = (e:unknown) => axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string' ? e.response.data.detail : t("Не удалось выполнить запрос");

export default function TeamPage() {
  const [deleteMessage,setDeleteMessage]=useState('');
  const [notice,setNotice]=useState<{added:number;failed:number;context:string}|null>(null);
  const [uploadProgress,setUploadProgress]=useState('');
  const {project:currentProject,part,selection,refresh:refreshCatalog,loading:catalogLoading,setLocked,select,setMapTools}=useProject();
  const project=currentProject?.name||'';const network=part?.name||'';
  const [wholeProject,setWholeProject]=useState(false);
  const [mergeParts,setMergeParts]=useState(true);
  const [moving,setMoving]=useState(false);
  const [queue,setQueue]=useState<Queued[]>([]);const [reports,setReports]=useState<Scan[]>([]);
  const [selected,setSelected]=useState<number[]>([]);const [result,setResult]=useState<Visibility|null>(null);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [view,setView]=useState('map');
  const [page,setPage]=useState(0);
  const [showUpload,setShowUpload]=useState(false);
  const [showReports,setShowReports]=useState(true);
  const resultPanel=useRef<HTMLElement>(null);
  const [pathRequest,setPathRequest]=useState<{from:string;to:string}|null>(null);
  const [search,setSearch]=useState('');const [source,setSource]=useState('');
  const [scopeTargets,setScopeTargets]=useState('');const [scopePorts,setScopePorts]=useState('');const [confirmed,setConfirmed]=useState(false);
  const refreshContexts=refreshCatalog;
  useEffect(()=>{setLocked(busy);return()=>setLocked(false);},[busy]);
  const load=async(resetSelection=false)=>{
    if(!project.trim() || (!wholeProject&&!network.trim()))return;
    setError('');setBusy(true);setResult(null);setPathRequest(null);
    try{
      const all:Scan[]=[];let total=1;
      while(all.length<total){const {data}=await axios.get<{scans:Scan[];total:number}>('/api/scans',{params:{project_id:selection.projectId,network_part_id:wholeProject?undefined:selection.partId,skip:all.length,limit:200},timeout:15000});all.push(...data.scans);total=data.total;if(!data.scans.length)break;}
      setReports(all);setSelected(old=>resetSelection?all.filter(s=>s.source_host&&['completed','failed','cancelled'].includes(s.status)).slice(0,20).map(s=>s.id):old.filter(id=>all.some(report=>report.id===id)));
    }catch(e){setError(message(e));}finally{setBusy(false);}
  };
  useEffect(()=>{setReports([]);setResult(null);setSelected([]);setShowReports(true);if(currentProject&&(wholeProject||part))load(true);},[selection.projectId,selection.partId,currentProject?.id,part?.id,wholeProject]);
  useEffect(()=>{setMergeParts(true);},[selection.projectId]);
  useEffect(()=>{setQueue([]);setShowUpload(false);},[selection.projectId,selection.partId]);
  useEffect(()=>{if(result)resultPanel.current?.scrollIntoView({behavior:'smooth',block:'start'});},[result]);

  const upload=async()=>{
    if(queue.some(item=>!item.id&&!validLocalDateTime(item.observed))){setError(t('Укажите время в формате HH:mm, от 00:00 до 23:59'));return;}
    setBusy(true);setError('');setNotice(null);
    const imported:Scan[]=[];let failed=0;
    const pending=queue.filter(item=>!item.id).length;let processed=0;
    for(let i=0;i<queue.length;i++){
      const item=queue[i];if(item.id)continue;
      setUploadProgress(t("Загрузка {v0} из {v1}: {v2}", {
  v0: processed + 1,
  v1: pending,
  v2: item.file.name
}));
      setQueue(q=>q.map((r,j)=>j===i?{...r,status:t("Загружается…")}:r));
      try{
        const body=new FormData();body.append('file',item.file);
        body.append('metadata',JSON.stringify({project_id:selection.projectId,network_part_id:selection.partId,source_host:item.source.trim(),author:item.author.trim()||null,observed_at:item.observed?new Date(item.observed).toISOString():null,scope_targets:confirmed?scopeTargets.trim()||null:null,scope_ports:confirmed?scopePorts.trim()||null:null,scope_confirmed:confirmed}));
        const {data}=await axios.post<Scan>('/api/scans/import',body);
        imported.push(data);
        setQueue(q=>q.map((r,j)=>j===i?{...r,id:data.id,status:t("Добавлен")}:r));
      }catch(e){failed++;setQueue(q=>q.map((r,j)=>j===i?{...r,status:message(e)}:r));}
      processed++;
    }
    setUploadProgress('');setNotice({added:imported.length,failed,context:`${project.trim()} / ${network.trim()}`});
    if(imported.length){
      setReports(old=>[...imported.reverse(),...old.filter(r=>!imported.some(s=>s.id===r.id))]);
      setSelected(old=>Array.from(new Set([...imported.map(r=>r.id),...old])).slice(0,50));
      setResult(null);
      await load();
    }
    setBusy(false);if(!failed)setShowUpload(false);refreshContexts();
  };
  const deleteReport=async(scan:Scan)=>{
    if(!window.confirm(t("Удалить отчёт #{v0} «{v1}»? Он исчезнет из общей истории и карты сети. Исходный файл и скриншоты также будут удалены.", {
  v0: scan.id,
  v1: scan.target
})))return;
    setBusy(true);setError('');setDeleteMessage('');
    try{
      await axios.delete(`/api/scans/${scan.id}`,{timeout:15000});
      setReports(items=>items.filter(s=>s.id!==scan.id));setSelected(ids=>ids.filter(id=>id!==scan.id));
      setQueue(items=>items.filter(item=>item.id!==scan.id));setResult(null);setNotice(null);
      setDeleteMessage(t("Отчёт #{v0} удалён из истории и карты сети.", {
  v0: scan.id
}));await refreshContexts();
    }catch(e){setError(message(e));}finally{setBusy(false);}
  };
  const build=async()=>{
    setBusy(true);setError('');setResult(null);setPathRequest(null);
    try{const {data}=await axios.get<Visibility>('/api/scans/visibility',{params:{project_id:selection.projectId,network_part_id:wholeProject?undefined:selection.partId,whole_project:wholeProject,merge_parts:wholeProject&&mergeParts,report_ids:selected.join(',')}});setResult(data);setPage(0);setSource(String(initialSourceReport(data)||''));setShowReports(false);setView('map');}
    catch(e){setError(message(e));}finally{setBusy(false);}
  };
  const restoreMap=async(saved:SavedMapView)=>{
    setBusy(true);setError('');
    try{const {data}=await axios.get<Visibility>('/api/scans/visibility',{params:{project_id:selection.projectId,network_part_id:saved.whole_project?undefined:saved.network_part_id,whole_project:saved.whole_project,merge_parts:saved.whole_project&&saved.merge_parts,report_ids:saved.report_ids.join(',')}});
      // Context changes reload the report list; apply the saved result after that reload.
      setWholeProject(saved.whole_project);setMergeParts(saved.merge_parts);
      select({projectId:selection.projectId,partId:saved.network_part_id});
      setPendingRestore({data,saved});
    }catch(e){setError(message(e));}finally{setBusy(false);}
  };
  useEffect(()=>{
    setMapTools?.({view:result?{report_ids:result.columns.map(c=>c.id),source:Number(source)||null,whole_project:wholeProject,merge_parts:mergeParts,network_part_id:selection.partId}:null,restore:restoreMap});
    return()=>setMapTools?.(null);
  },[result,source,wholeProject,mergeParts,selection.projectId,selection.partId]);
  const [pendingRestore,setPendingRestore]=useState<{data:Visibility;saved:SavedMapView}|null>(null);
  useEffect(()=>{if(!busy&&pendingRestore){const {data,saved}=pendingRestore;setPendingRestore(null);setResult(data);setSelected(saved.report_ids);setSource(String(saved.source||initialSourceReport(data)||''));setShowReports(false);setView('map');setSearch('');setPage(0);}},[busy,reports,pendingRestore]);
  const update=(index:number,key:'source'|'author'|'observed',value:string)=>setQueue(q=>q.map((item,i)=>i===index?{...item,[key]:value}:item));
  const rows=result?.rows.filter(r=>`${r.ip} ${r.hostname||''} ${r.port} ${r.cells.map(c=>c.service||'').join(' ')}`.toLowerCase().includes(search.toLowerCase()))||[];
  return <div className="space-y-5">
    {notice && <ImportNotice warning={!!notice.failed} title={notice.added ? t("Отчёты добавлены: {v0}", {
  v0: notice.added
}) : t("Отчёты не загружены")} onClose={()=>setNotice(null)}>
      {!!notice.added && <p>{t('Сохранены в общем списке и в проекте «{v0}».',{v0:notice.context})}</p>}
      {!!notice.failed && <p>{t("Не удалось загрузить:")} {notice.failed}{t(". Причина указана возле каждого файла. Успешные отчёты сохранены.")}</p>}
      {!!notice.added && <button className="report-choice" onClick={()=>{setShowReports(true);document.getElementById('team-report-list')?.scrollIntoView({behavior:'smooth',block:'start'});}}>{t("Перейти к добавленным отчётам")}</button>}
    </ImportNotice>}
    <header className="reports-page-heading"><h1>{t("Карта сети")}</h1><button className="report-button report-button-secondary" disabled={busy||!currentProject} onClick={()=>setShowUpload(true)}><Upload size={16}/>{t("Загрузить отчёты")}</button></header>

    {deleteMessage&&<div role="status" className="report-success">{uiText(deleteMessage)}</div>}
    {error&&<div role="alert" className="report-alert">{uiText(error)}</div>}
    <section className="map-scope-toolbar"><label>{t("Просмотр")}<select aria-label={t("Область карты")} value={wholeProject?'project':'part'} disabled={busy||!currentProject} onChange={e=>{setWholeProject(e.target.value==='project');setResult(null);}}><option value="part">{t("Выбранная часть сети")}</option><option value="project">{t("Весь проект")}</option></select></label><details><summary>{t("Параметры адресации")}{mergeParts?t(" · общая"):''}</summary><div><label><input type="checkbox" checked={mergeParts} disabled={busy||!wholeProject} onChange={e=>{setMergeParts(e.target.checked);setResult(null);}}/>{t("Общая адресация: одинаковые IP — одни устройства")}</label><p>{t("По умолчанию одинаковые IP в разных частях проекта объединяются в одно устройство. Отключите, если в частях сети одинаковые IP принадлежат разным устройствам. Просмотр не меняет место сохранения новых сканов и файлов.")}</p></div></details></section>
    <WorkspaceDialog open={showUpload} title={t("Загрузить отчёты команды")} wide busy={busy} onClose={()=>setShowUpload(false)}>
      <p className="report-upload-destination">{project&&network?t("Сохранить в: {v0} / {v1}", {
  v0: project,
  v1: network
}):t("Для загрузки выберите проект и часть сети в верхней панели.")}</p>
      {error&&<div role="alert" className="report-alert">{uiText(error)}</div>}
    <div className="team-upload-content">
      <p className="text-sm text-gray-500 my-3">{t("Для каждого файла укажите хост, с которого выполнялось сканирование. Можно загрузить до 50 файлов за одну очередь.")}</p>
      <label className="report-button report-button-secondary cursor-pointer"><Upload size={15}/>{t("Выбрать файлы")}<input type="file" multiple className="sr-only" disabled={busy} onChange={e=>{
        const files=Array.from(e.target.files||[]);if(files.length>50){setError(t("Максимум 50 файлов"));return;}setNotice(null);setQueue(files.map(file=>({file,source:'',author:'',observed:'',status:''})));
      }}/></label>
      {!!queue.length && <div className="overflow-x-auto mt-3"><table className="report-table"><thead><tr><th>{t("Файл")}</th><th>{t("Точка сканирования")}</th><th>{t("Автор")}</th><th>{t("Время сканирования")}</th><th>{t("Результат загрузки")}</th></tr></thead><tbody>{queue.map((item,i)=><tr key={i}><td className="break-all">{item.file.name}</td><td><input aria-label={t("Точка сканирования {v0}", {
  v0: item.file.name
})} disabled={busy||!!item.id} value={item.source} onChange={e=>update(i,'source',e.target.value)} placeholder={t("192.168.1.50 · бухгалтерия")} maxLength={253}/></td><td><input aria-label={t("Автор {v0}", {
  v0: item.file.name
})} disabled={busy||!!item.id} value={item.author} onChange={e=>update(i,'author',e.target.value)} placeholder={t("Имя")} maxLength={120}/></td><td><LocalDateTimeInput label={t('Время {v0}',{v0:item.file.name})} disabled={busy||!!item.id} value={item.observed} onChange={value=>update(i,'observed',value)}/></td><td>{item.id?<Link className="text-accent" to={`/scan/${item.id}`}>{t("Добавлен #")}{item.id}</Link>:uiText(item.status)||t("Готов к загрузке")}</td></tr>)}</tbody></table></div>}
      <details className="mt-4"><summary className="text-sm cursor-pointer">{t("Уточнить, что проверялось — необязательно")}</summary><p className="text-xs text-gray-500 my-2">{t("Можно загрузить отчёты без этих настроек. Они нужны только для различия «Не обнаружено» и «Нет данных». Укажите цели и все проверенные порты, включая те, где ничего не найдено. Эти параметры применяются ко всей очереди; при разных настройках загружайте отчёты отдельными очередями.")}</p><div className="team-form-grid"><label>{t("Цели IPv4 / CIDR")}<input disabled={busy} value={scopeTargets} onChange={e=>{setScopeTargets(e.target.value);setConfirmed(false);}} placeholder="192.168.1.0/24"/></label><label>{t("Какие TCP-порты проверял сканер")}<input disabled={busy} value={scopePorts} onChange={e=>{setScopePorts(e.target.value);setConfirmed(false);}} placeholder="22,80,443,8006"/></label></div><label className="flex items-center gap-2 text-xs mt-3"><input type="checkbox" disabled={busy||!scopeTargets.trim()||!scopePorts.trim()} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>{t("Сканирование завершилось, и в файлах есть весь результат по указанным целям и портам")}</label><p className="text-xs text-gray-500 mt-2">{t("Если галочка не отмечена, эти поля не отправляются. Отчёты всё равно загружаются; отсутствие записи показывается как «Нет данных».")}</p></details>
      {uploadProgress && <p role="status" className="text-sm text-accent mt-4">{uiText(uploadProgress)}</p>}
      {!!queue.length && <button className="report-button report-button-primary mt-4" disabled={busy||catalogLoading||!project.trim()||!network.trim()||queue.some(q=>!q.id&&!q.source.trim())||queue.some(q=>!q.id&&!validLocalDateTime(q.observed))||queue.every(q=>q.id)} onClick={upload}>{busy?t("Обработка…"):t("Загрузить отчёты")}</button>}
      {queue.some(item=>!item.id&&!validLocalDateTime(item.observed))&&<p role="alert" className="report-alert">{t('Укажите время в формате HH:mm, от 00:00 до 23:59')}</p>}
      {!!queue.length && !busy && <p role="status" className="text-xs text-gray-500 mt-3">{!project.trim() || !network.trim() ? t("Для загрузки выберите проект и часть сети в верхней панели.") : queue.some(q=>!q.id&&!q.source.trim()) ? t("Для загрузки укажите точку сканирования у файлов: {v0}.", {
  v0: queue.filter(q => !q.id && !q.source.trim()).slice(0, 3).map(q => q.file.name).join(', ')
}) : queue.every(q=>q.id) ? t("Все файлы уже загружены и находятся в общем списке.") : t("Можно загружать. Параметры области проверки не обязательны.")}</p>}
      <p className="text-xs text-gray-500 mt-3">{t("Загруженные отчёты автоматически появляются в списке ниже и в общей истории. При повторной загрузке отправляются только файлы с ошибками.")}</p>
    </div>
    </WorkspaceDialog>
    {moving&&<MoveReportsDialog ids={selected} onClose={()=>setMoving(false)} onMoved={()=>{setMoving(false);setResult(null);setSelected([]);setDeleteMessage(t("Отчёты перенесены. Файлы сохранены."));load();}}/>}
    {!!reports.length&&<section id="team-report-list" className="report-panel scroll-mt-4"><div className="map-report-selection-bar"><div><strong>{t("Выбрано отчётов:")} {selected.length}</strong><span>{t("Всего в списке:")} {reports.length} {t("· можно выбрать до 50")}</span></div><div className="map-report-actions"><button disabled={busy} className="report-choice" title={t("Обновить список отчётов")} aria-label={t("Обновить список отчётов")} onClick={()=>load()}><RefreshCw size={15}/></button><button disabled={busy} className="report-button report-button-secondary" aria-expanded={showReports} onClick={()=>setShowReports(!showReports)}>{showReports?t("Свернуть список"):t("Выбрать отчёты")}</button><button disabled={busy||!selected.length} onClick={build} className="report-button report-button-primary"><Network size={15}/>{busy?t("Обработка…"):t("Построить карту")}</button></div></div>
      {showReports&&<div><div className="map-report-list-heading"><span>{t("Выберите отчёты. Список можно растягивать вниз за нижний правый угол.")}</span><button disabled={busy||!selected.length} className="report-choice" onClick={()=>setMoving(true)}>{t("Перенести выбранные")}</button></div><div className="team-report-list-scroll"><table className="report-table team-report-table"><thead><tr><th>{t("Выбор")}</th><th>{t("Отчёт")}</th><th>{t("Точка сканирования")}</th><th>{t("Автор / время проверки")}</th><th>{t("Действия")}</th></tr></thead><tbody>{reports.map(s=><tr key={s.id}><td><input type="checkbox" aria-label={t("Выбрать отчёт {v0}", {
  v0: s.id
})} checked={selected.includes(s.id)} disabled={busy||!s.source_host||['running','queued'].includes(s.status)||(!selected.includes(s.id)&&selected.length>=50)} onChange={e=>{setSelected(ids=>e.target.checked?[...ids,s.id]:ids.filter(id=>id!==s.id));setResult(null);}}/></td><td><Link to={`/scan/${s.id}`} className="text-accent">#{s.id} · {s.target}</Link><div className="scan-meta">{s.network} · {s.status}{!s.scope_confirmed?t(" · область не подтверждена"):''}</div></td><td>{s.source_host||t("Не указана — откройте отчёт и назначьте источник")}</td><td>{s.author||t("Не указан")}<div className="scan-meta">{s.observed_at?formatDateTime(s.observed_at):t("Время сканирования неизвестно")}</div></td><td><button disabled={busy||['running','queued'].includes(s.status)} title={['running','queued'].includes(s.status)?t("Сначала остановите активный скан"):t("Удалить отчёт #{v0}", {
  v0: s.id
})} className="scan-action-button danger" onClick={()=>deleteReport(s)}><Trash2 size={15}/>{t("Удалить")}</button></td></tr>)}</tbody></table></div></div>}</section>}
    {result&&<section ref={resultPanel} className="report-panel map-result-panel scroll-mt-4"><div className="map-result-toolbar"><div className="map-view-tabs"><button className="report-choice" aria-pressed={view==='map'} onClick={()=>setView('map')}><Network size={14}/>{t("Карта")}</button><button className="report-choice" aria-pressed={view==='table'} onClick={()=>setView('table')}><Table2 size={14}/>{t("Таблица")}</button></div><button className="report-choice map-path-action" aria-pressed={view==='paths'} onClick={()=>{setPathRequest(null);setView('paths');}}><Route size={14}/>{t("Найти путь")}</button><span className="map-result-count">{result.columns.length} {t("отчётов ·")} {new Set(result.rows.map(row=>row.device_id)).size} {t("устройств")}</span><details className="map-export-menu"><summary className="report-choice"><Download size={14}/>{t("Экспорт")}<ChevronDown size={12}/></summary><button className="report-choice" onClick={event=>{const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='visibility.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);event.currentTarget.closest('details')?.removeAttribute('open');}}>{t("Скачать JSON")}</button></details></div>
      <div className="p-4 space-y-3"><details className="map-result-help"><summary>{t("Как читать результаты")}</summary><p>{result.warnings.map(uiText).join(' ')}</p></details><div className="flex flex-wrap gap-3 text-xs">{Object.entries(states).map(([key,label])=><span key={key} className={`visibility-state ${key}`}>{label}</span>)}</div><input aria-label={t("Поиск устройств и портов")} className="team-search" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}} placeholder={t("Найти IP, порт, имя или сервис")}/></div>
      {view==='paths'?<ObservedPaths key={`${result.columns.map(c=>c.id).join(',')}/${pathRequest?.from||''}/${pathRequest?.to||''}`} data={result} initialFrom={pathRequest?.from} initialTo={pathRequest?.to}/>:view==='table'?<div className="overflow-auto max-h-[650px]"><table className="report-table visibility-table"><thead><tr><th>{t("Устройство / сервис")}</th>{result.columns.map(c=><th key={c.id}><Link to={`/scan/${c.id}`}>{c.source_host}</Link><div className="scan-meta">{t("Отчёт #")}{c.id} · {c.network}</div></th>)}</tr></thead><tbody>{rows.slice(page*100,(page+1)*100).map(r=><tr key={`${r.device_id}/${r.protocol}/${r.port}`}><td><div className="font-mono">{r.ip}</div><div className="scan-meta">{r.network}</div><div className="scan-meta">{r.protocol==='host'?t("Устройство"):`${r.port}/${r.protocol}`} {r.hostname}</div></td>{r.cells.map(c=><td key={c.report_id}><span className={`visibility-state ${c.state}`}>{states[c.state]}</span>{c.service && <div className="scan-meta">{c.service} {c.version}</div>}</td>)}</tr>)}</tbody></table><div className="flex items-center gap-4 p-4 text-xs"><button disabled={page===0} className="report-choice" onClick={()=>setPage(page-1)}>{t("Назад")}</button><span>{t("Строки")} {rows.length? page*100+1:0}–{Math.min((page+1)*100,rows.length)} {t("из")} {rows.length}</span><button className="report-choice" disabled={(page+1)*100>=rows.length} onClick={()=>setPage(page+1)}>{t("Далее")}</button></div></div>:<VisibilityMap mapTitle={`${project} · ${wholeProject?t("Весь проект"):network}`} data={result} rows={rows} source={source} setSource={setSource} onShowPath={(from,to)=>{setPathRequest({from,to});setView('paths');}}/>}
    </section>}
  </div>;
}
