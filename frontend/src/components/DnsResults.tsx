import { uiText, t } from '../i18n/core';
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Globe, Loader2, ChevronDown, X } from 'lucide-react';
import type { ScanDetail, DnsOptions } from '../types';

const labels: Record<string, string> = {get resolved() {
  return t("Получены имена");
},get no_record() {
  return t("Нет PTR-записи");
},get unreachable() {
  return t("DNS не ответил");
},get refused() {
  return t("Запрос запрещён");
},get dns_error() {
  return t("Ошибка DNS");
},get budget_exceeded() {
  return t("Не проверено: лимит времени");
},get no_server() {
  return t("Нет доступного DNS");
}};

export default function DnsResults({ scan, onQueued }: { scan: ScanDetail; onQueued: () => void }) {
  const disclosure=useRef<HTMLDetailsElement>(null);
  const [server, setServer] = useState(scan.dns_options?.server || '');
  const [transport, setTransport] = useState<DnsOptions['transport']>(scan.dns_options?.transport || 'auto');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {setServer(scan.dns_options?.server || '');setTransport(scan.dns_options?.transport || 'auto');setError('');}, [scan.id]);
  useEffect(()=>{
    if(typeof document==='undefined')return;
    const outside=(event:MouseEvent)=>{if(disclosure.current&&event.target instanceof Node&&!disclosure.current.contains(event.target))disclosure.current.open=false;};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&disclosure.current?.open){disclosure.current.open=false;disclosure.current.querySelector('summary')?.focus();}};
    document.addEventListener('mousedown',outside);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('mousedown',outside);document.removeEventListener('keydown',escape);};
  },[]);
  const working = scan.dns_status === 'queued' || scan.dns_status === 'running';
  const terminal = !['queued','running'].includes(scan.status);
  const queuedAt = scan.dns_summary?.queued_at;
  const stale = working && !!queuedAt && Date.now() - Date.parse(queuedAt) > 5 * 60 * 1000;
  const summary = scan.dns_summary;
  const run = async (event: React.FormEvent) => {
    event.preventDefault();if(busy||(working&&!stale)||!terminal||!scan.hosts.length)return;setBusy(true);setError('');
    try {await axios.post(`/api/scans/${scan.id}/resolve-names`, {enabled:true,server:server.trim()||null,transport});onQueued();}
    catch (e) {const detail=axios.isAxiosError(e)?e.response?.data?.detail:null;setError(typeof detail==='string'?detail:Array.isArray(detail)?detail.map((item:{msg:string})=>item.msg).join('; '):t("Не удалось запустить определение имён"));}
    finally {setBusy(false);}
  };
  const named=scan.hosts.filter(host=>host.dns_result?.names?.length).length;
  const status=busy?t("Запуск…"):error?t("Ошибка запроса"):working?(scan.dns_status==='queued'?t("В очереди"):t("Поиск…")):scan.dns_status==='failed'?t("Ошибка DNS"):scan.dns_status==='cancelled'?t("Отменено"):!scan.dns_status||scan.dns_status==='not_requested'?t("Не запрашивались"):t("{v0} из {v1}", {
  v0: named,
  v1: scan.hosts.length
});
  return <details ref={disclosure} className="scan-dns-control" onToggle={event=>{
    if(event.target!==event.currentTarget||!event.currentTarget.open)return;
    const bounds=event.currentTarget.getBoundingClientRect();
    const width=Math.min(420,window.innerWidth-64);
    const left=Math.max(16,Math.min(bounds.left,window.innerWidth-width-16))-bounds.left;
    event.currentTarget.style.setProperty('--dns-popover-left',`${left}px`);
    const below=window.innerHeight-bounds.bottom-16;
    const above=bounds.top-16;
    const openAbove=below<300&&above>below;
    event.currentTarget.style.setProperty('--dns-popover-top',openAbove?'auto':'calc(100% + 8px)');
    event.currentTarget.style.setProperty('--dns-popover-bottom',openAbove?'calc(100% + 8px)':'auto');
    event.currentTarget.style.setProperty('--dns-popover-height',`${Math.max(160,Math.min(window.innerHeight*.65,openAbove?above:below))}px`);
  }}>
    <summary title={t("Определить имена хостов через DNS")}><Globe size={15}/><span>{t("Имена хостов")}</span><span className="scan-dns-status" role="status" aria-live="polite">{working&&<Loader2 size={12} className="animate-spin"/>}{status}</span><ChevronDown size={13} className="scan-dns-chevron"/></summary>
    <div className="scan-dns-popover">
      <header><div><h2>{t("Имена хостов")}</h2><p>{t("DNS-запросы без повторного сканирования портов")}</p></div><button type="button" aria-label={t("Закрыть настройки имён хостов")} onClick={()=>{if(disclosure.current){disclosure.current.open=false;disclosure.current.querySelector('summary')?.focus();}}}><X size={16}/></button></header>
      {terminal?<form onSubmit={run}>
        <label>{t("DNS-сервер")}<input aria-label={t("DNS-сервер для имён")} value={server} onChange={event=>setServer(event.target.value)} placeholder={t("Автоматический выбор")} maxLength={45} disabled={busy||(working&&!stale)}/></label>
        <label>{t("Транспорт")}<select aria-label={t("Транспорт DNS для имён")} value={transport} onChange={event=>setTransport(event.target.value as DnsOptions['transport'])} disabled={busy||(working&&!stale)}><option value="auto">{t("Авто: UDP → TCP")}</option><option value="tcp">{t("Только TCP")}</option><option value="udp">UDP</option></select></label>
        <div className="scan-dns-run"><span>{t('Имена получены: {v0} из {v1}',{v0:named,v1:scan.hosts.length})}</span><button className="report-button report-button-primary" disabled={busy||(working&&!stale)||!scan.hosts.length}>{busy?<Loader2 size={15} className="animate-spin"/>:<Globe size={15}/>}{t("Получить имена")}</button></div>
      </form>:<p className="scan-dns-help">{t("Определение имён будет доступно после завершения сканирования.")}</p>}
      {error&&<p className="scan-dns-error" role="alert">{uiText(error)}</p>}
      {summary?.error&&<p className="scan-dns-error" role="alert">{uiText(summary.error)}</p>}
      {stale&&<p className="scan-dns-help">{t("Задача долго не отвечает. Можно повторить запрос или проверить worker.")}</p>}
      {summary?.budget_exceeded&&<p className="scan-dns-help">{t("Достигнут лимит 60 секунд. Полученные имена сохранены; можно повторить запрос с конкретным DNS.")}</p>}
      {!!summary?.skipped&&<p className="scan-dns-help">{t("Не проверено из-за ограничения 10000 хостов:")} {summary.skipped}.</p>}
      <details className="scan-dns-diagnostics"><summary>{t("Подробности DNS-проверки")}</summary><div>
        <p>{t("Пустое поле — автоматический выбор DNS. Указанный сервер используется без подмены системным. Отсутствие PTR-записи не означает отсутствия имени компьютера.")}</p>
        {summary?.counts&&<div className="scan-dns-counts">{Object.entries(summary.counts).map(([key,value])=><span key={key}>{labels[key]||key}: <strong>{value}</strong></span>)}</div>}
        {!!summary?.servers?.length&&<ul>{summary.servers.map(item=><li key={item.server}>{item.server} · {({manual:t("указан вручную"),saved:t("сохранён для части сети"),discovered:t("найден в отчёте"),system:t("системный DNS")} as Record<string,string>)[item.source]||item.source} {t("· имена для тестовых IP:")} {item.resolved}{!item.answered?t(" · нет подходящих ответов"):''}</li>)}</ul>}
      </div></details>
    </div>
  </details>;
}
