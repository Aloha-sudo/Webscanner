import { uiText, t, formatDateTime } from '../i18n/core';
import { currentMapSvg, downloadFile, fullMapSvg } from '../utils/svgExport';
import { useEffect, useLayoutEffect, useId, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Maximize2, Minimize2, ZoomIn, ZoomOut, RotateCcw, X } from 'lucide-react';
import { buildObservationGraph } from '../utils/observedPaths';
import type { ObservationData, ObservationRow, PathEdge } from '../utils/observedPaths';
import { fitMapZoom, layoutNetworkMap, MAP_LEVEL_GAP } from '../utils/networkMapLayout';
import type { MapLayout } from '../utils/networkMapLayout';
import { edgeHasAnyService, filterMapServices, layoutHostNeighborhood, mapServiceOptions } from '../utils/mapExploration';

const states:Record<string,string>={get found() {
  return t("Обнаружено");
},get unknown() {
  return t("Нет данных");
},get not_found() {
  return t("Не обнаружено");
},get not_tested() {
  return t("Не проверялось");
}};
const serviceKey=(row:ObservationRow)=>`${row.protocol}/${row.port}`;
const serviceLabel=(row:ObservationRow)=>row.protocol==='host'?t("Устройство"):`${row.port}/${row.protocol.toUpperCase()}`;

type Props={mapTitle?:string;data:ObservationData;rows:ObservationRow[];source:string;setSource:(value:string)=>void;onShowPath:(from:string,to:string)=>void};
export default function VisibilityMap({data,rows,source,setSource,onShowPath,mapTitle=t("Карта сети")}:Props){
  const graph=useMemo(()=>buildObservationGraph(data,true),[data]);
  const sources=Array.from(graph.nodes.values()).filter(node=>node.isSource);
  const root=graph.reportSources.get(Number(source))||sources[0]?.id||'';
  const [exportError,setExportError]=useState('');
  const [target,setTarget]=useState('');const [service,setService]=useState('');
  const [collapsed,setCollapsed]=useState<Set<string>>(()=>new Set());
  const [expanded,setExpanded]=useState(false);const [zoom,setZoom]=useState(1);
  const [autoFit,setAutoFit]=useState(false);
  const [focused,setFocused]=useState(false);const [portFilters,setPortFilters]=useState<Set<string>>(()=>new Set());const [serviceSearch,setServiceSearch]=useState('');
  const fullView=useRef<{zoom:number;left:number;top:number;target:string}|null>(null);
  const viewport=useRef<HTMLDivElement>(null);const expandButton=useRef<HTMLButtonElement>(null);
  const drag=useRef<{x:number;y:number;left:number;top:number}|null>(null);
  const marker=useId().replace(/:/g,'');
  const branch=useMemo(()=>layoutNetworkMap(graph,root,collapsed),[graph,root,collapsed]);
  const chosen=graph.nodes.get(target);
  const serviceOptions=useMemo(()=>mapServiceOptions(graph),[graph]);
  const activeFilters=useMemo(()=>serviceOptions.filter(option=>portFilters.has(option.key)).map(option=>option.key),[serviceOptions,portFilters]);
  const activeFilterSet=useMemo(()=>new Set(activeFilters),[activeFilters]);
  const neighborhood=useMemo(()=>layoutHostNeighborhood(graph,target),[graph,target]);
  const services=data.rows.filter(row=>row.device_id===target);
  const selectedService=services.find(row=>serviceKey(row)===service);
  const reverse=!!selectedService;
  const evidence=selectedService?data.columns.map(column=>({column,cell:selectedService.cells.find(cell=>cell.report_id===column.id)})):[];
  const foundReports=new Set(evidence.filter(e=>e.cell?.state==='found').map(e=>e.column.id));
  const ownReports=data.columns.filter(column=>graph.reportSources.get(column.id)===target);
  const incoming=Array.from(graph.outgoing.values()).flat().filter(edge=>edge.to===target);
  const matched=new Set(rows.map(row=>row.device_id));
  const filtered=matched.size<new Set(data.rows.map(row=>row.device_id)).size;
  const layout=useMemo(()=>{
    if(!selectedService)return filterMapServices(focused?neighborhood:branch,focused?target:root,activeFilters);
    const fromIds=Array.from(new Set(selectedService.cells.filter(cell=>cell.state==='found').map(cell=>graph.reportSources.get(cell.report_id)).filter((id):id is string=>!!id)));
    const height=Math.max(240,fromIds.length*96+80);
    const positions:MapLayout['positions']=new Map();
    fromIds.filter(id=>id!==target).forEach((id,i)=>positions.set(id,{id,level:0,x:32,y:52+i*96}));
    positions.set(target,{id:target,level:1,x:32+MAP_LEVEL_GAP,y:height/2-36});
    const edges=fromIds.filter(id=>id!==target).map(id=>graph.outgoing.get(id)?.find(edge=>edge.to===target)).filter((edge):edge is PathEdge=>!!edge);
    return {positions,edges,width:MAP_LEVEL_GAP+304,height,levels:2};
  },[branch,neighborhood,focused,selectedService,graph,target,root,activeFilters]);
  const changeZoom=(value:number)=>{setAutoFit(false);setZoom(Math.max(.001,Math.min(2.5,value)));};
  const fit=()=>{
    setAutoFit(true);
    const el=viewport.current;if(el){setZoom(fitMapZoom(el.clientWidth,el.clientHeight,layout.width,layout.height));el.scrollTo(0,0);}
  };
  useLayoutEffect(()=>{
    const el=viewport.current;if(!el||!autoFit)return;
    const update=()=>{
      if(el.clientWidth<=30||el.clientHeight<=30)return;
      setZoom(fitMapZoom(el.clientWidth,el.clientHeight,layout.width,layout.height));el.scrollTo(0,0);
    };
    update();
    if(typeof ResizeObserver==='undefined')return;
    const observer=new ResizeObserver(update);observer.observe(el);
    return()=>observer.disconnect();
  },[autoFit,root,layout.width,layout.height,!!chosen,expanded]);
  // Start at readable 100% with the root visible, even in a tall branch.
  // Opening a device panel must not reframe the viewport.
  useLayoutEffect(()=>{
    const position=branch.positions.get(root);
    if(position)viewport.current?.scrollTo(0,Math.max(0,position.y-60));
  },[root]);
  useLayoutEffect(()=>{
    if(focused&&!reverse){const position=neighborhood.positions.get(target);if(position)viewport.current?.scrollTo(Math.max(0,(position.x+240)*zoom-(viewport.current?.clientWidth||900)+40),Math.max(0,position.y*zoom-60));}
    else if(!focused&&fullView.current){const view=fullView.current;fullView.current=null;viewport.current?.scrollTo(view.left,view.top);}
  },[focused,target,reverse]);
  const showNeighborhood=()=>{
    if(!chosen)return;
    if(!focused)fullView.current={zoom,left:viewport.current?.scrollLeft||0,top:viewport.current?.scrollTop||0,target};
    setAutoFit(false);setZoom(1);setService('');setFocused(true);
  };
  const showBranches=()=>{setService('');setFocused(false);setAutoFit(false);if(fullView.current){setZoom(fullView.current.zoom);setTarget(fullView.current.target);}};
  const resetScale=()=>{
    setAutoFit(false);setZoom(1);
    const position=layout.positions.get(focused?target:root);
    viewport.current?.scrollTo(position?Math.max(0,position.x+240-(viewport.current?.clientWidth||900)+40):0,Math.max(0,(position?.y||0)-60));
  };
  const selectSource=(id:string)=>{
    const report=data.columns.find(column=>graph.reportSources.get(column.id)===id);
    fullView.current=null;setFocused(false);setPortFilters(new Set());if(report)setSource(String(report.id));setTarget('');setService('');setCollapsed(new Set());setAutoFit(false);setZoom(1);viewport.current?.scrollTo(0,0);
  };
  const selectDevice=(id:string)=>{setAutoFit(false);setTarget(id);setService('');};
  const toggle=(id:string)=>setCollapsed(old=>{const next=new Set(old);if(next.has(id))next.delete(id);else next.add(id);return next;});
  useEffect(()=>{
    if(!expanded)return;
    const previous=document.body.style.overflow;document.body.style.overflow='hidden';
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){setExpanded(false);expandButton.current?.focus();}};
    document.addEventListener('keydown',escape);
    return()=>{document.body.style.overflow=previous;document.removeEventListener('keydown',escape);};
  },[expanded]);
  useEffect(()=>{
    const el=viewport.current;if(!el)return;
    const wheel=(event:WheelEvent)=>{if(event.ctrlKey){event.preventDefault();setAutoFit(false);setZoom(old=>Math.max(.001,Math.min(2.5,old*(event.deltaY<0?1.12:1/1.12))));}};
    el.addEventListener('wheel',wheel,{passive:false});return()=>el.removeEventListener('wheel',wheel);
  },[]);
  return <div className={`network-map-workspace ${expanded?'map-expanded':''}`} aria-label={t("Рабочее пространство карты")}>
    {exportError&&<p role="alert" className="report-alert">{uiText(exportError)}</p>}
    <div className="network-map-toolbar"><label className="text-sm">{t("Начальный источник")}<select value={root} onChange={e=>selectSource(e.target.value)}>{sources.map(node=><option key={node.id} value={node.id}>{node.label} · {node.network}</option>)}</select></label>
      <div className="network-map-actions"><details><summary className="report-choice">{t("Экспорт SVG")}</summary><button className="report-choice" onClick={()=>{setExportError('');try{const svg=viewport.current?.querySelector('svg');if(!svg)throw new Error(t("Карта ещё не готова к экспорту"));downloadFile(currentMapSvg(svg,t("{v0} · источник {v1}", {
  v0: mapTitle,
  v1: graph.nodes.get(root)?.label || ''
}),JSON.stringify({reports:data.columns,services:activeFilters,collapsed:[...collapsed],mode:reverse?'service':focused?'neighborhood':'branches',sharedAddressing:data.merge_parts})),'network-map-view.svg','image/svg+xml');}catch(error){setExportError(error instanceof Error?error.message:t("Не удалось сохранить SVG"));}}}>{t("Скачать SVG текущего вида")}</button><button className="report-choice" onClick={()=>downloadFile(fullMapSvg(data,t("{v0} · все выбранные отчёты", {
  v0: mapTitle
})),'network-map-full.svg','image/svg+xml')}>{t("Скачать SVG всей карты")}</button></details><button className="report-choice" aria-label={t("Уменьшить масштаб")} onClick={()=>changeZoom(zoom*.8)}><ZoomOut size={15}/></button><span className="text-xs text-gray-500">{zoom<.1?(zoom*100).toFixed(1):Math.round(zoom*100)}%</span><button className="report-choice" aria-label={t("Увеличить масштаб")} onClick={()=>changeZoom(zoom*1.25)}><ZoomIn size={15}/></button><button className="report-choice" onClick={fit}>{t("Вместить в окно")}</button><button className="report-choice" onClick={()=>{if(focused)showBranches();setCollapsed(new Set());setService('');}}>{t("Раскрыть все ветки")}</button><button className="report-choice" title={t("Масштаб 100% и начальный источник")} onClick={resetScale}><RotateCcw size={14}/>{t("Сбросить масштаб")}</button><button ref={expandButton} className="report-choice" onClick={()=>setExpanded(!expanded)}>{expanded?<Minimize2 size={15}/>:<Maximize2 size={15}/>} {expanded?t("Свернуть"):t("Развернуть")}</button></div>
    </div>
    <div className="map-exploration-tools">
      {!reverse?<details className="map-services-menu" onKeyDown={e=>{if(e.key==='Escape'){e.currentTarget.open=false;e.currentTarget.querySelector('summary')?.focus();}}}>
        <summary>{t("Сервисы на схеме:")} {activeFilters.length?t("выбрано {v0}", {
  v0: activeFilters.length
}):t("все")}</summary>
        <div className="map-services-popover"><input aria-label={t("Поиск сервисов")} placeholder={t("Найти порт или сервис…")} value={serviceSearch} onChange={e=>setServiceSearch(e.target.value)}/><button className="report-choice" disabled={!activeFilters.length} onClick={()=>{setAutoFit(false);setPortFilters(new Set());}}>{t("Все сервисы")}</button><p>{t("Показывать совпадения по любому отмеченному сервису.")}</p><div className="map-service-options">{serviceOptions.filter(option=>option.label.toLowerCase().includes(serviceSearch.trim().toLowerCase())).map(option=><label key={option.key}><input type="checkbox" aria-label={t("Сервис {v0}", {
  v0: option.key.split('/').reverse().join('/').toUpperCase()
})} checked={activeFilterSet.has(option.key)} onChange={e=>{setAutoFit(false);const checked=e.target.checked;setPortFilters(previous=>{const next=new Set(previous);if(checked)next.add(option.key);else next.delete(option.key);return next;});}}/><span>{option.label}</span></label>)}</div>{!serviceOptions.some(option=>option.label.toLowerCase().includes(serviceSearch.trim().toLowerCase()))&&<p>{t("Сервисы не найдены.")}</p>}</div>
      </details>:<span>{t("Сервис выбран в карточке устройства.")}</span>}
      {!reverse&&!!activeFilters.length&&<div className="map-selected-services">{activeFilters.map(key=><button className="report-choice" key={key} aria-label={t("Убрать сервис {v0}", {
  v0: key.split('/').reverse().join('/').toUpperCase()
})} onClick={()=>{setAutoFit(false);setPortFilters(previous=>{const next=new Set(previous);next.delete(key);return next;});}}>{key.split('/').reverse().join('/').toUpperCase()} <X size={12}/></button>)}</div>}
      {focused&&<button className="report-choice" onClick={showBranches}>{t("Вся карта")}</button>}{focused&&!reverse&&<span>{t("Окружение")} {chosen?.label}{t(": входящие и исходящие наблюдения, один шаг.")}</span>}{!!activeFilters.length&&!reverse&&<span>{t("Серые линии «Контекст» оставлены для ориентации; отмеченные сервисы на них не обнаружены.")}</span>}
    </div>
    {reverse?<div className="service-map-mode" role="status">{t("Кто видит")} {chosen?.label} · {serviceLabel(selectedService!)}<button className="report-choice" onClick={()=>setService('')}>{focused?t("Вернуться к окружению"):t("Вернуться к веткам")}</button></div>:<div className="network-map-summary"><span>{t("На схеме:")} {layout.positions.size} {t("узлов · отчётов:")} {data.columns.length} · {autoFit?t("Масштаб по размеру окна"):t("Ручной масштаб")}</span><span>{focused?t("Нажмите соседний хост для его окружения. «Вся карта» возвращает прежний вид."):t("«Есть сканы» — из хоста загружены отчёты. Кнопки + и − раскрывают ветки.")}</span></div>}
    <p className="text-xs text-gray-500 map-help">{t("Пунктир показывает обнаруженную доступность, а не физический маршрут или подтверждённый переход. Нажмите устройство для сервисов и отчётов. Карта открывается в масштабе 100%; полный обзор — «Вместить в окно». Перемещайте карту за свободное пространство; Ctrl + колесо меняет масштаб.")}{filtered?t(" Поиск подсвечивает совпадения, сохраняя промежуточные узлы."):''}</p>
    {!!graph.unmatchedSources.length&&<details className="network-map-unmatched"><summary>{t("Не сопоставлены с найденными устройствами:")} {graph.unmatchedSources.length} {t("источников")}</summary><p>{t("Из этих точек можно начать карту. Для продолжения ветки источник должен совпадать с IP или точным именем найденного устройства в той же части сети. Между частями сопоставление доступно в режиме общей адресации, если адреса обозначают одни и те же устройства.")}</p><ul>{graph.unmatchedSources.map((name,i)=><li key={i}>{name}</li>)}</ul></details>}
    <div className={`network-map-body ${chosen?'has-service-panel':''}`}>
      <div ref={viewport} className="visibility-map network-map-canvas multilevel-map-canvas" tabIndex={0} aria-label={t("Многоуровневая карта доступности")} onPointerDown={e=>{
        if(e.button!==0||(e.target instanceof Element&&e.target.closest('[role="button"]')))return;
        const el=e.currentTarget;drag.current={x:e.clientX,y:e.clientY,left:el.scrollLeft,top:el.scrollTop};el.setPointerCapture(e.pointerId);el.classList.add('is-dragging');
      }} onPointerMove={e=>{if(!drag.current)return;e.currentTarget.scrollLeft=drag.current.left-(e.clientX-drag.current.x);e.currentTarget.scrollTop=drag.current.top-(e.clientY-drag.current.y);}} onPointerUp={e=>{drag.current=null;e.currentTarget.classList.remove('is-dragging');if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={e=>{drag.current=null;e.currentTarget.classList.remove('is-dragging');}}>
        <svg role="group" aria-label={reverse?t("Кто обнаружил выбранный сервис"):t("Связи по выбранным отчётам")} viewBox={`0 0 ${layout.width} ${layout.height}`} style={{width:layout.width*zoom,height:layout.height*zoom,display:'block',flexShrink:0}}>
          <defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="var(--accent)"/></marker></defs>
          {Array.from({length:layout.levels},(_,level)=><text key={level} x={32+level*MAP_LEVEL_GAP} y="24" fill="var(--map-secondary, var(--text-secondary))" fontSize="13" fontWeight="500">{reverse?(level?t("Выбранное устройство"):t("Кто обнаружил")):focused?[t("Кто обнаружил"),t("Выбранное устройство"),t("Обнаружено из устройства")][level]:level===0?t("Начальный источник"):level===1?t("Обнаружено из источника"):t("Уровень {v0} · обнаружено дальше", {
  v0: level
})}</text>)}
          {layout.edges.map(edge=>{
            const a=layout.positions.get(edge.from)!;const b=layout.positions.get(edge.to)!;
            const forward=b.level>a.level;
            const aCenter=a.y+(graph.nodes.get(edge.from)?.isSource?34:26),bCenter=b.y+(graph.nodes.get(edge.to)?.isSource?34:26);
            const d=forward?`M ${a.x+240} ${aCenter} C ${a.x+275} ${aCenter}, ${b.x-35} ${bCenter}, ${b.x} ${bCenter}`:`M ${a.x+120} ${a.y} C ${a.x+120} ${a.y-40}, ${b.x+120} ${b.y-40}, ${b.x+120} ${b.y}`;
            const context=!!activeFilters.length&&!reverse&&!edgeHasAnyService(edge,activeFilterSet);
            const items=reverse?edge.evidence.filter(item=>foundReports.has(item.report.id)&&item.port===selectedService!.port&&item.protocol===selectedService!.protocol):activeFilters.length&&!context?edge.evidence.filter(item=>activeFilterSet.has(`${item.protocol}/${item.port}`)):edge.evidence;
            const ports=new Set(items.filter(item=>item.protocol!=='host').map(item=>`${item.port}/${item.protocol.toUpperCase()}`));
            const title=t("{v0}{v1} → {v2}: {v3} · отчёты {v4}", {
  v0: context ? t("Контекст: выбранные сервисы на этой связи не обнаружены. ") : '',
  v1: graph.nodes.get(edge.from)?.label,
  v2: graph.nodes.get(edge.to)?.label,
  v3: ports.size ? Array.from(ports).join(', ') : t("устройство обнаружено"),
  v4: Array.from(new Set(items.map(item => `#${item.report.id}`))).join(', ')
});
            return <g key={`${edge.from}-${edge.to}`}><path d={d} fill="none" stroke={context?'var(--muted)':'var(--map-line, var(--accent))'} opacity={context?.35:target&&edge.from!==target&&edge.to!==target? .3:1} strokeWidth="1.8" strokeDasharray="5 4" markerEnd={`url(#${marker})`}><title>{title}</title></path>{forward&&<text x={(a.x+240+b.x)/2} y={(a.y+b.y)/2+25} textAnchor="middle" fill="var(--map-secondary, var(--text-secondary))" fontSize="11">{context?t("Контекст"):ports.size>0&&ports.size<=2?Array.from(ports).join(' · '):ports.size?t("{v0} порт(ов)", {
  v0: ports.size
}):t("Хост")}</text>}</g>;
          })}
          {Array.from(layout.positions.values()).map(position=>{
            const node=graph.nodes.get(position.id)!;const reports=data.columns.filter(column=>graph.reportSources.get(column.id)===node.id);
            const children=graph.outgoing.get(node.id)?.length||0;const selected=node.id===target;
            return <g key={node.id}>
              <g role="button" tabIndex={0} aria-label={t("Открыть устройство {v0}, {v1}", {
  v0: node.label,
  v1: node.network
})} aria-pressed={selected} onClick={()=>selectDevice(node.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectDevice(node.id);}}} style={{cursor:'pointer'}}>
                <rect x={position.x} y={position.y} width="240" height={reports.length?68:52} rx="9" fill={selected||node.id===root||(filtered&&matched.has(node.id))?'var(--selected)':'var(--surface)'} stroke={selected||node.isSource||(filtered&&matched.has(node.id))?'var(--accent)':'var(--map-node-border, var(--border))'} strokeWidth={selected?2:1}/>
                <text x={position.x+14} y={position.y+22} fill="var(--text)" fontSize="14" fontWeight="500">{node.label.slice(0,27)}</text>
                <text x={position.x+14} y={position.y+40} fill="var(--map-secondary, var(--text-secondary))" fontSize="12">{node.network.slice(0,31)}</text>
                {!!reports.length&&<text x={position.x+14} y={position.y+60} fill="var(--accent)" fontSize="12">{t("Есть сканы · {v0}{v1}", {
  v0: reports.length,
  v1: collapsed.has(node.id) ? t(" · свёрнуто") : ''
})}</text>}<title>{node.label} · {node.network}</title>
              </g>
              {!reverse&&!focused&&children>0&&<g role="button" tabIndex={0} aria-label={t("{v0} ветку {v1}", {
  v0: collapsed.has(node.id) ? t("Раскрыть") : t("Свернуть"),
  v1: node.label
})} aria-expanded={!collapsed.has(node.id)} onClick={()=>toggle(node.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle(node.id);}}} style={{cursor:'pointer'}}><circle cx={position.x+222} cy={position.y+19} r="11" fill="var(--surface)" stroke="var(--border)"/><text x={position.x+222} y={position.y+23} textAnchor="middle" fill="var(--text)" fontSize="15">{collapsed.has(node.id)?'+':'−'}</text></g>}
            </g>;
          })}
        </svg>
        {!activeFilters.length&&!focused&&layout.positions.size===1&&!graph.outgoing.get(root)?.length&&<p className="network-map-no-children">{t("Из этого источника в выбранных отчётах нет обнаруженных устройств.")}</p>}
        {!!activeFilters.length&&!reverse&&!layout.edges.some(edge=>edgeHasAnyService(edge,activeFilterSet))&&<p className="map-service-empty" role="status">{t("В этом виде нет наблюдений выбранных сервисов. Измените набор сервисов или начальный источник.")}</p>}
      </div>
      {chosen&&<aside className="service-visibility-panel" aria-label={reverse?t("Кто видит этот сервис?"):t("Сведения об устройстве")}>
        <button className="map-device-close" aria-label={t("Закрыть карточку устройства")} onClick={()=>{if(focused)showBranches();setTarget('');setService('');}}><X size={18}/></button>
        <h3>{reverse?t("Кто видит этот сервис?"):t("Устройство")}</h3><p className="service-device-name">{chosen.label}</p><p className="text-xs text-gray-500">{chosen.network}</p>
        {!reverse&&<>
          <div className="network-map-device-facts"><span>{t("Обнаружен из:")} {incoming.length} {t("точек")}</span><span>{t("Отчётов из хоста:")} {ownReports.length}</span><span>{t("Найдено из него:")} {graph.outgoing.get(target)?.length||0} {t("устройств")}</span></div>
          {!!ownReports.length&&<div className="network-map-own-reports"><h4>{t("Отчёты из этого хоста")}</h4>{ownReports.map(report=><Link key={report.id} to={`/scan/${report.id}`}>{t("Отчёт #")}{report.id} · {report.source_host}</Link>)}</div>}
          <button className="report-choice" onClick={focused?showBranches:showNeighborhood}>{focused?t("Вся карта"):t("Показать окружение")}</button>
          {!focused&&!!graph.outgoing.get(target)?.length&&<button className="report-choice" onClick={()=>toggle(target)}>{collapsed.has(target)?t("Раскрыть"):t("Свернуть")} {t("ветку")}</button>}
          {chosen.ip&&<button className="report-choice" onClick={()=>onShowPath(root,target)}>{t("Показать путь до хоста")}</button>}
          <h4 className="text-sm font-medium">{t("Кто видит сервис? Выберите порт")}</h4>
          {!services.length&&<p className="text-xs text-gray-500">{t("Для этого источника нет отчётов, где он сам указан обнаруженным устройством.")}</p>}
        </>}
        <div className="service-port-picker" aria-label={t("Выберите сервис")}>{services.map(row=><button key={serviceKey(row)} className="report-choice" aria-pressed={service===serviceKey(row)} onClick={()=>{setPortFilters(new Set());setAutoFit(false);setService(serviceKey(row));}}>{serviceLabel(row)}</button>)}</div>
        {reverse&&<><div className="service-result-summary" role="status"><strong>{serviceLabel(selectedService!)}</strong><span>{t("Обнаружено в")} {foundReports.size} {t("из")} {data.columns.length} {t("отчётов")}</span></div><div className="service-evidence-list">{[...evidence].sort((a,b)=>Number(b.cell?.state==='found')-Number(a.cell?.state==='found')).map(({column,cell})=><article key={column.id} className="service-evidence"><div className="service-evidence-heading"><strong>{column.source_host}</strong><span className={`visibility-state ${cell?.state||'unknown'}`}>{states[cell?.state||'unknown']}</span></div><p className="text-xs text-gray-500">{column.network} · {column.author||t("Автор не указан")}</p><p className="text-xs text-gray-500">{column.observed_at?<time dateTime={column.observed_at}>{formatDateTime(column.observed_at)}</time>:t("Время сканирования неизвестно")}</p>{cell?.service&&<p className="text-xs">{cell.service} {cell.version}</p>}<Link className="text-accent text-xs" to={`/scan/${column.id}`}>{t("Открыть отчёт #")}{column.id}</Link></article>)}</div><button className="report-choice" onClick={()=>setService('')}>{focused?t("Вернуться к окружению"):t("Вернуться к веткам")}</button></>}
        <p className="text-xs text-gray-500">{t("Связи относятся ко времени отчётов. Отсутствие записи — не доказательство недоступности. Наличие сканов из хоста не подтверждает способ получения доступа к нему.")}</p>
      </aside>}
    </div>
  </div>;
}
