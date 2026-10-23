import { uiText, t, formatDateTime } from '../i18n/core';
import { useProject } from '../context/ProjectContext';
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Upload, FileText, Download, Search, X, Check, Loader2, ArrowLeftRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { listScans } from '../api/client';
import ImportNotice from './ImportNotice';
import type { Scan, Host } from '../types';

type Fields = Record<string, { before: unknown; after: unknown }>;
type Difference = {
  added_hosts: Host[]; removed_hosts: Host[]; unchanged_hosts: number; warnings: string[];
  changed_hosts: { ip: string; added_ports: Host['ports']; removed_ports: Host['ports']; changed_ports: {port: number; protocol: string; fields: Fields}[]; metadata: Fields }[];
};
const portLabel = (p: { port: number; protocol: string }) => `${p.port}/${p.protocol}`;
const value = (v: unknown) => v == null || v === '' ? t("Не указано в отчёте") : typeof v === 'boolean' ? (v ? t("Да") : t("Нет")) : typeof v === 'object' ? JSON.stringify(v) : String(v);
const errorMessage = (error: unknown) => {
  if (!axios.isAxiosError(error)) return t("Не удалось выполнить запрос");
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d.msg).join('; ') : t("Не удалось выполнить запрос");
};

export default function ReportTools({allProjects,showUpload,onCloseUpload}:{allProjects:boolean;showUpload:boolean;onCloseUpload:()=>void}) {
  const {selection,project,part,loading:catalogLoading,setLocked}=useProject();
  const resultPanel = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const uploadDialog=useRef<HTMLDialogElement>(null);
  const [search, setSearch] = useState('');
  const [dragging, setDragging] = useState(false);
  const [loadingReports, setLoadingReports] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showNotice,setShowNotice] = useState(false);
  const [success, setSuccess] = useState<Scan | null>(null);
  const [before, setBefore] = useState('');
  const [after, setAfter] = useState('');
  const [result, setResult] = useState<Difference | null>(null);
  const [allScans, setAllScans] = useState<Scan[]>([]);
  useEffect(()=>{setLocked(busy);return()=>setLocked(false);},[busy]);
  useEffect(()=>{
    const dialog=uploadDialog.current;if(!dialog)return;
    if(showUpload&&!dialog.open)dialog.showModal();
    if(!showUpload&&dialog.open)dialog.close();
  },[showUpload]);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoadingReports(true);setAllScans([]);setBefore('');setAfter('');setResult(null);setError('');
      const reports: Scan[] = [];
      try {
        let total = 1;
        while (reports.length < total) {
          const page = await listScans(reports.length,200,{project_id:allProjects?null:selection.projectId,network_part_id:allProjects?null:selection.partId});
          total = page.total;
          reports.push(...page.scans);
          if (!page.scans.length || cancelled) break;
        }
        if (!cancelled) setAllScans(current=>[...current.filter(item=>!reports.some(report=>report.id===item.id)),...reports]);
      } catch { if (!cancelled) setError(t("Не удалось загрузить отчёты для сравнения")); }
      finally { if (!cancelled) setLoadingReports(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [allProjects,selection.projectId,selection.partId]);
  useEffect(() => { if (result) resultPanel.current?.scrollIntoView({behavior: 'smooth', block: 'start'}); }, [result]);
  const completed = allScans.filter(s => s.status === 'completed');
  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    if(catalogLoading || (project&&!part)){setError(t("Выберите часть сети в верхней панели"));return;}
    if (file.size > 20 * 1024 * 1024) { setError(t("Максимальный размер — 20 МБ")); return; }
    setBusy(true); setError(''); setSuccess(null);
    try {
      const body = new FormData(); body.append('file', file);body.append('metadata',JSON.stringify({project_id:selection.projectId,network_part_id:selection.partId}));
      const { data } = await axios.post<Scan>('/api/scans/import', body);
      setSuccess(data); setShowNotice(true); setAllScans(old=>[data,...old.filter(s=>s.id!==data.id)]);setFile(null);if(input.current)input.current.value='';onCloseUpload();
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const compare = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const { data } = await axios.get<Difference>('/api/scans/compare', {params: {before, after}});
      setResult(data);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const filtered = completed.filter(s => `${s.id} ${s.target} ${s.source_host||''} ${s.project||''} ${s.network||''} ${s.comment || ''} ${s.scan_type}`.toLowerCase().includes(search.toLowerCase()));
  const choose = (id: string, side: 'before' | 'after') => {
    if (side === 'before') { setBefore(id); if (after === id) setAfter(''); }
    else { setAfter(id); if (before === id) setBefore(''); }
    setResult(null);
  };
  const firstReport = completed.find(s => String(s.id) === before);
  const secondReport = completed.find(s => String(s.id) === after);
  const reportName = (scan: Scan | undefined, id: string) => scan ? `#${id} · ${scan.target}` : t("Отчёт #{v0}", {
  v0: id
});
  const selectionCard=(id:string,label:string,side:'before'|'after')=><label className="comparison-report-field">{label}<select aria-label={label} value={id} disabled={busy||loadingReports} onChange={e=>choose(e.target.value,side)}><option value="">{t("Выберите отчёт")}</option>{completed.map(scan=><option key={scan.id} value={scan.id} disabled={String(scan.id)===(side==='before'?after:before)}>#{scan.id} · {scan.target} · {date(scan.created_at)}{scan.source_host?t(" · из {v0}", {
  v0: scan.source_host
}):''}</option>)}</select></label>;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `compare_${before}_${after}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="report-workspace">
    {success && showNotice && <ImportNotice title={t("Отчёт успешно загружен")} onClose={()=>setShowNotice(false)}><p>{t("Отчёт #")}{success.id} {t("сохранён в общей истории:")} {success.total_hosts} {t("хостов,")} {success.total_ports} {t("портов.")}</p><Link className="report-choice" to={`/scan/${success.id}`}>{t("Открыть загруженный отчёт")}</Link></ImportNotice>}
    {error && !showUpload && <div role="alert" className="report-alert">{uiText(error)}</div>}
    <div className="report-grid report-grid-wide">
      <div className="min-w-0 space-y-5">
        <section className="report-panel">
          <div className="report-panel-heading"><h2>{t("Сравнить два отчёта")}</h2></div>
          <div className="comparison-controls">
            {selectionCard(before,t("Первый отчёт"),'before')}
            <button type="button" className="report-button report-button-secondary comparison-swap" aria-label={t("Поменять отчёты местами")} title={t("Поменять отчёты местами")} disabled={busy||!before||!after} onClick={()=>{setBefore(after);setAfter(before);setResult(null);}}><ArrowLeftRight size={17}/></button>
            {selectionCard(after,t("Второй отчёт"),'after')}
            <button type="button" onClick={compare} disabled={busy||loadingReports||!before||!after||before===after} className="report-button report-button-primary">{busy?<Loader2 size={15} className="animate-spin"/>:<ArrowLeftRight size={15}/>}{t("Показать различия")}</button>
          </div>
          <p className="comparison-help">{t("Выберите отчёты здесь или в таблице ниже. Для сравнения по времени: первый — более ранний, второй — более поздний.")}</p>
        </section>
        <section className="report-panel">
          <div className="report-panel-heading"><div className="flex items-center gap-3"><h2>{allProjects||!project?t("Все отчёты"):t("Отчёты проекта")}</h2><span className="report-count">{completed.length}</span></div><span className="text-xs text-slate-500">{t("Завершённые")}</span></div>
          <div className="p-4 border-b border-border"><div className="report-search"><Search size={16}/><input aria-label={t("Поиск отчётов")} placeholder={t("IP, источник или номер отчёта")} value={search} onChange={e=>setSearch(e.target.value)}/>{search && <button aria-label={t("Очистить поиск")} onClick={()=>setSearch('')}><X size={14}/></button>}</div></div>
          <div className="overflow-x-auto max-h-[520px]">
            <table className="report-table"><thead><tr><th>{t("Отчёт")}</th><th>{t("Источник")}</th><th>{t("Хосты / порты")}</th><th>{t("Дата")}</th><th className="text-right">{t("Выберите два отчёта")}</th></tr></thead><tbody>
              {filtered.map(scan => {
                const id = String(scan.id), isBefore = before === id, isAfter = after === id;
                return <tr key={id} className={isBefore || isAfter ? 'report-row-selected' : ''}>
                  <td><Link to={`/scan/${id}`} className="report-report-link"><FileText size={16} className="shrink-0 text-slate-500"/><span className="truncate max-w-[240px]">{scan.target}</span></Link><div className="text-xs text-slate-500 mt-1 pl-6">#{id} <span className="mx-1">·</span> {source(scan.scan_type)}</div></td>
                  <td className="report-source-cell">{scan.source_host||t("Не указан")}<div className="scan-meta">{scan.project||t("Без проекта")}{scan.network?` / ${scan.network}`:''}</div></td><td className="tabular-nums whitespace-nowrap">{scan.total_hosts}<span className="text-slate-600 mx-2">/</span>{scan.total_ports}</td>
                  <td className="text-slate-500 whitespace-nowrap text-xs">{date(scan.created_at)}</td>
                  <td><div className="flex justify-end gap-1.5"><button disabled={busy || isAfter} aria-label={t("Выбрать первым: отчёт #{v0}, {v1}", {
  v0: id,
  v1: scan.target
})} aria-pressed={isBefore} onClick={()=>choose(isBefore ? '' : id,'before')} className={`report-choice ${isBefore ? 'active' : ''}`}>{isBefore && <Check size={12}/>}{t("Первым")}</button><button disabled={busy || isBefore} aria-label={t("Выбрать вторым: отчёт #{v0}, {v1}", {
  v0: id,
  v1: scan.target
})} aria-pressed={isAfter} onClick={()=>choose(isAfter ? '' : id,'after')} className={`report-choice ${isAfter ? 'active' : ''}`}>{isAfter && <Check size={12}/>}{t("Вторым")}</button></div></td>
                </tr>;
              })}
            </tbody></table>
            {!filtered.length && <div className="report-empty"><FileText size={25}/><p>{loadingReports ? t("Загрузка отчётов…") : search ? t("По этому запросу ничего не найдено") : t("Пока нет завершённых отчётов")}</p><span>{!loadingReports && !search ? t("Загрузите файл или завершите сканирование.") : ''}</span></div>}
          </div>
        </section>
      </div>
      <dialog ref={uploadDialog} className="report-upload-dialog report-panel" aria-labelledby="report-upload-title" onCancel={e=>{if(busy)e.preventDefault();else onCloseUpload();}} onClick={e=>{if(e.target===e.currentTarget&&!busy)onCloseUpload();}}>
        <div className="report-panel-heading"><h2 id="report-upload-title">{t("Загрузить отчёт из файла")}</h2><button type="button" aria-label={t("Закрыть загрузку отчёта")} disabled={busy} onClick={onCloseUpload}><X size={18}/></button></div>
        <form onSubmit={upload} className="p-5 space-y-4">
          <p className="report-upload-destination">{project?(part?t("Сохранить в: {v0} / {v1}", {
  v0: project.name,
  v1: part.name
}):t("Выберите часть сети в верхней панели перед загрузкой.")):t("Отчёт сохранится без проекта.")}</p>
          {error&&<div role="alert" className="report-alert">{uiText(error)}</div>}
          <p className="text-xs text-slate-400 leading-relaxed">{t("Загрузите результат Nmap, Masscan или другого поддерживаемого сканера. Отчёт появится в общем списке — его можно открыть и сравнить.")}</p>
          <input ref={input} aria-label={t("Файл отчёта")} type="file" className="sr-only" disabled={busy} onChange={e=>{setFile(e.target.files?.[0] || null);setSuccess(null);}}/>
          <button type="button" disabled={busy} onClick={()=>input.current?.click()} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);if(!busy){setFile(e.dataTransfer.files[0] || null);setSuccess(null);}}} className={`report-dropzone ${dragging ? 'dragging' : ''}`}>
            {file ? <FileText size={25}/> : <Upload size={25}/>}<span className="text-sm font-medium break-all">{file ? file.name : t("Выберите файл")}</span><span className="text-xs text-slate-500">{file ? t("{v0} КБ · нажмите, чтобы заменить", {
  v0: (file.size / 1024).toFixed(0)
}) : t("или перетащите его сюда")}</span>
          </button>
          <div className="flex justify-between text-xs text-slate-500"><span>XML, JSON, CSV, TXT</span><span>{t("До 20 МБ")}</span></div>
          <button disabled={!file || busy || catalogLoading || (!!project&&!part)} className="report-button report-button-secondary w-full justify-center">{busy ? <Loader2 size={15} className="animate-spin"/> : <Upload size={15}/>}{busy ? t("Загрузка…") : t("Добавить в список отчётов")}</button>
          {success && <div role="status" className="report-success"><Check size={16}/><div><p>{t("Отчёт добавлен")}</p><p className="text-xs text-slate-400 mt-1">{success.total_hosts} {t("хостов ·")} {success.total_ports} {t("портов")}</p><Link className="inline-block text-xs underline mt-2" to={`/scan/${success.id}`}>{t("Открыть отчёт #")}{success.id}</Link></div></div>}
          <details className="report-formats"><summary>{t("Поддерживаемые форматы")}</summary><ul><li>{t("Nmap — XML и greppable")}</li><li>{t("Masscan — XML, JSON и list")}</li><li>RustScan — greppable</li><li>{t("FastScan (magisterquis) — TXT: строки SUCCESS и баннеры")}</li><li>{t("WebScanner — JSON и XML")}</li><li>{t("CSV — колонки IP и порт; без порта импортируются только хосты")}</li></ul></details>
        </form>
      </dialog>
    </div>
    {result && <section ref={resultPanel} className="report-panel scroll-mt-24" aria-live="polite">
      <div className="report-panel-heading"><div><h2>{t("Результат сравнения")}</h2><p className="break-all">{t("Первый:")} {reportName(firstReport, before)}<br/>{t("Второй:")} {reportName(secondReport, after)}</p></div><button onClick={download} className="report-button report-button-secondary"><Download size={15}/>JSON</button></div>
      <div className="grid grid-cols-2 md:grid-cols-4 border-b border-border">
        {[[t("Хосты только во втором"),result.added_hosts.length],[t("Хосты только в первом"),result.removed_hosts.length],[t("Хосты с изменениями"),result.changed_hosts.length],[t("Хосты без изменений"),result.unchanged_hosts]].map(([label,count])=><div key={String(label)} className="px-5 py-4"><div className="text-xs text-slate-500">{label}</div><div className="text-2xl font-semibold tabular-nums mt-1">{count}</div></div>)}
      </div>
      <div className="px-5 py-3 text-xs text-slate-500 border-b border-border">{t("«Только во втором» означает: найден во втором отчёте, отсутствует в первом. «Не найден» означает отсутствие записи в файле; это не подтверждает закрытие порта. Сравнивайте одинаковые цели и наборы портов.")}</div>
      <div className="overflow-x-auto"><table className="report-table"><thead><tr><th>{t("Хост")}</th><th>{t("Различие")}</th><th>{t("Первый отчёт #")}{before}<div className="normal-case tracking-normal text-slate-500 mt-1 max-w-[220px] truncate">{firstReport?.target}</div></th><th>{t("Второй отчёт #")}{after}<div className="normal-case tracking-normal text-slate-500 mt-1 max-w-[220px] truncate">{secondReport?.target}</div></th></tr></thead><tbody>
        {result.added_hosts.map(h=><tr key={`added-${h.ip}`}><td className="font-mono">{h.ip}</td><td><span className="report-tag added">{t("Хост найден только во втором")}</span></td><td className="text-slate-500 text-xs">{t("Хост не найден в отчёте")}</td><td className="font-mono text-xs">{h.ports.map(portLabel).join(', ') || t("Нет данных о портах")}</td></tr>)}
        {result.removed_hosts.map(h=><tr key={`removed-${h.ip}`}><td className="font-mono">{h.ip}</td><td><span className="report-tag removed">{t("Хост найден только в первом")}</span></td><td className="font-mono text-xs">{h.ports.map(portLabel).join(', ') || t("Нет данных о портах")}</td><td className="text-slate-500 text-xs">{t("Хост не найден в отчёте")}</td></tr>)}
        {result.changed_hosts.map(h=><HostChanges key={h.ip} host={h}/>)}
      </tbody></table></div>
      {!result.added_hosts.length && !result.removed_hosts.length && !result.changed_hosts.length && <div className="report-empty"><Check size={25}/><p>{t("Различий не найдено")}</p><span>{t("Записи хостов и портов совпадают.")}</span></div>}
    </section>}
  </div>;
}
const date = (timestamp: string) => formatDateTime(timestamp);
const profiles: Record<string,string> = {get quick() {
  return t("Быстрое");
},get top100() {
  return t("100 популярных портов");
},get top1000() {
  return t("1000 популярных портов");
},get web() {
  return t("Веб-порты");
},get full() {
  return t("Все порты");
},get custom() {
  return t("Свои порты");
}};
const source = (type: string) => type.startsWith('import-') ? t("Из файла · {v0}", {
  v0: type.slice(7)
}) : t("Сканирование · {v0}", {
  v0: profiles[type] || type
});
const labels: Record<string,string> = {get hostname() {
  return t("Имя хоста");
},get os() {
  return t("ОС");
},get service() {
  return t("Сервис");
},get version() {
  return t("Версия");
},get banner() {
  return t("Баннер");
},get state() {
  return t("Состояние");
},url:'URL',get status_code() {
  return t("HTTP-статус");
},get title() {
  return t("Заголовок");
},get technologies() {
  return t("Технологии");
},ssl:'TLS'};
function HostChanges({host}: {host: Difference['changed_hosts'][number]}) {
  const row = (key: string, label: string, before: string, after: string) => <tr key={key}><td className="font-mono whitespace-nowrap">{host.ip}</td><td><span className="report-tag changed">{label}</span></td><td className="text-xs break-all">{before}</td><td className="text-xs break-all">{after}</td></tr>;
  return <>
    {host.added_ports.map(p=>row(`add-${portLabel(p)}`,t("{v0} · порт только во втором", {
  v0: portLabel(p)
}),t("Порт не найден в отчёте"),p.service || t("Открытый порт")))}
    {host.removed_ports.map(p=>row(`remove-${portLabel(p)}`,t("{v0} · порт только в первом", {
  v0: portLabel(p)
}),p.service || t("Открытый порт"),t("Порт не найден в отчёте")))}
    {Object.entries(host.metadata).map(([key,c])=>row(key,t("Изменилось: {v0}", {
  v0: labels[key] || key
}),value(c.before),value(c.after)))}
    {host.changed_ports.flatMap(p=>Object.entries(p.fields).map(([key,c])=>row(`${portLabel(p)}-${key}`,t("{v0} · изменилось: {v1}", {
  v0: portLabel(p),
  v1: labels[key] || key
}),value(c.before),value(c.after))))}
  </>;
}
