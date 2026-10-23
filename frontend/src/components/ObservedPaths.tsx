import { t, formatDateTime } from '../i18n/core';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Route } from 'lucide-react';
import { buildObservationGraph, shortestObservedPath } from '../utils/observedPaths';
import type { ObservationData, PathNode } from '../utils/observedPaths';

export default function ObservedPaths({data,initialFrom,initialTo}:{data:ObservationData;initialFrom?:string;initialTo?:string}) {
  const graph=useMemo(()=>buildObservationGraph(data),[data]);
  const sources=Array.from(graph.nodes.values()).filter(n=>n.isSource);
  const targets=Array.from(graph.nodes.values()).filter(n=>n.ip);
  const [from,setFrom]=useState(initialFrom&&sources.some(node=>node.id===initialFrom)?initialFrom:sources[0]?.id||'');
  const [targetText,setTargetText]=useState(initialTo&&graph.nodes.get(initialTo)?`${graph.nodes.get(initialTo)!.label} · ${graph.nodes.get(initialTo)!.network}`:'');
  const [query,setQuery]=useState<{from:string;to:string}|null>(initialFrom&&initialTo?{from:initialFrom,to:initialTo}:null);
  const path=useMemo(()=>query?shortestObservedPath(graph,query.from,query.to):null,[graph,query]);
  const label=(node:PathNode)=>`${node.label} · ${node.network}`;
  const matches=targets.filter(node=>label(node)===targetText.trim());
  const matchingIps=targets.filter(node=>node.ip===targetText.trim());
  const candidates=matches.length?matches:matchingIps;
  const to=candidates.length===1?candidates[0].id:'';
  const targetHint=!targetText.trim()?t("Начните вводить IP и выберите устройство из подсказок."):to?t("Выбрана цель: {v0}", {
  v0: label(graph.nodes.get(to)!)
}):matchingIps.length>1?t("Этот IP есть в нескольких частях сети. Выберите нужное устройство из подсказок."):t("Выберите устройство из подсказок — путь строится до конкретного хоста.");
  const chain=path&&query?[graph.nodes.get(query.from)!,...path.map(edge=>graph.nodes.get(edge.to)!)]:[];
  const change=()=>setQuery(null);
  return <div className="observed-paths">
    <header><h3>{t("Пути по сканам")}</h3><p>{t("Найдите кратчайшую цепочку обнаруженных сервисов от источника до цели.")}</p></header>
    <div className="observed-path-controls">
      <label>{t("Источник скана")}<select aria-label={t("Источник скана для поиска пути")} value={from} onChange={e=>{setFrom(e.target.value);change();}}>{sources.map(node=><option key={node.id} value={node.id}>{label(node)}</option>)}</select></label>
      <label className="observed-path-target">{t("Целевой хост")}<input aria-label={t("Целевой хост")} aria-describedby="observed-path-target-help" list="observed-path-targets" value={targetText} onChange={e=>{setTargetText(e.target.value);change();}} placeholder={t("Введите IP или выберите устройство")} autoComplete="off"/></label>
      <datalist id="observed-path-targets">{targets.map(node=><option key={node.id} value={label(node)}/>)}</datalist>
      <button className="report-button report-button-primary" disabled={!from||!to} onClick={()=>setQuery({from,to})}><Route size={16}/>{t("Найти путь")}</button>
    </div>
    <p id="observed-path-target-help" className="observed-path-target-help" role="status">{targetHint}</p>
    <p className="observed-path-notice">{t("Это возможная цепочка по отчётам, а не подтверждённый маршрут или доступ для перехода. Каждый промежуточный хост должен быть доступен команде отдельно. Все связи направленные; сканы разных дат не подтверждают одновременную доступность.")}</p>
    {!!graph.unmatchedSources.length&&<details className="observed-path-unmatched"><summary>{t("Не сопоставлены с устройствами:")} {graph.unmatchedSources.length} {t("источников")}</summary><p>{t("Из этих точек можно начать поиск, но автоматически продолжить путь через них нельзя. Для сопоставления укажите в источнике IP устройства (можно с подписью после пробела) или его точное имя из отчёта. Сопоставление выполняется внутри части сети; между частями — только при включённой общей адресации.")}</p><ul>{graph.unmatchedSources.map((name,i)=><li key={i}>{name}</li>)}</ul></details>}
    {!query&&<div className="observed-path-empty">{t("Выберите источник скана, укажите целевой хост и нажмите «Найти путь». Используются все выбранные отчёты.")}</div>}
    {query&&path===null&&<div role="status" className="observed-path-empty">{t("По выбранным отчётам путь не найден. Это не означает, что хост недоступен: может не хватать сканов или сопоставления источников.")}</div>}
    {query&&path?.length===0&&<div role="status" className="observed-path-empty">{t("Источник и цель — одно устройство. Переход не требуется.")}</div>}
    {!!path?.length&&<>
      <div className="observed-path-summary" role="status">{t("Найдена цепочка · связей:")} {path.length} {t("· требуется проверка возможности переходов")}</div>
      <div className="observed-path-graph" tabIndex={0} aria-label={t("Схема пути; для длинной цепочки прокрутите вправо")}><svg width={chain.length*270-30} height="180" role="img" aria-label={chain.map(n=>n.label).join(' → ')}>
        <defs><marker id="observed-path-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="var(--accent)"/></marker></defs>
        {path.map((edge,i)=><g key={`${edge.from}-${edge.to}`}><path d={`M ${i*270+205} 80 H ${(i+1)*270+10}`} stroke="var(--accent)" strokeWidth="2" strokeDasharray="5 4" markerEnd="url(#observed-path-arrow)"/><text x={i*270+235} y="42" textAnchor="middle" fill="var(--muted)" fontSize="10">{edge.evidence.length===1?`${edge.evidence[0].port}/${edge.evidence[0].protocol}`:t("{v0} порт(ов)", {
  v0: new Set(edge.evidence.map(e => `${e.port}/${e.protocol}`)).size
})}</text></g>)}
        {chain.map((node,i)=><g key={node.id}><rect x={i*270+10} y="54" width="195" height="64" rx="8" fill={i===chain.length-1?'var(--selected)':'var(--surface)'} stroke={i===chain.length-1?'var(--accent)':'var(--border)'}/><text x={i*270+24} y="80" fill="var(--text)" fontSize="13">{node.label.slice(0,23)}</text><text x={i*270+24} y="101" fill="var(--muted)" fontSize="10">{node.network.slice(0,26)}</text><title>{label(node)}</title></g>)}
        <text x="12" y="155" fill="var(--muted)" fontSize="11">{t("Пунктир — обнаруженная доступность сервиса, возможность перехода не подтверждена")}</text>
      </svg></div>
      <div className="observed-path-evidence">{path.map((edge,i)=><section key={`${edge.from}-${edge.to}`}><h4>{i+1}. {graph.nodes.get(edge.from)?.label} → {graph.nodes.get(edge.to)?.label}</h4>{Array.from(new Set(edge.evidence.map(e=>e.report.id))).map(id=>{
        const items=edge.evidence.filter(e=>e.report.id===id);const report=items[0].report;
        return <div className="observed-path-report" key={id}><Link to={`/scan/${id}`}>{t("Отчёт #")}{id}</Link><span>{report.observed_at?formatDateTime(report.observed_at):t("Время сканирования неизвестно")} · {report.author||t("Автор не указан")}</span><p>{items.map(e=>`${e.port}/${e.protocol.toUpperCase()}${e.service?` · ${e.service}`:''}`).join(', ')}</p></div>;
      })}</section>)}</div>
    </>}
  </div>;
}
