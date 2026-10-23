import { t, formatNumber, hostCount } from '../i18n/core';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, SlidersHorizontal, X, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Host } from '../types';
import HostCard from './HostCard';
import { filterScanHosts, HOSTS_PAGE_SIZE, hostPage } from '../utils/scanHostFilters';

const keys = ['host_q', 'host_ports', 'host_protocol', 'host_page'];

export default function ScanHosts({ hosts, tools }: { hosts: Host[]; tools?: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const query = params.get('host_q') || '';
  const ports = params.get('host_ports') || '';
  const rawProtocol = params.get('host_protocol') || '';
  const protocols = Array.from(new Set(hosts.flatMap(host => host.ports.map(port => port.protocol.toLowerCase())))).sort();
  const protocol = protocols.includes(rawProtocol) ? rawProtocol : '';
  const result = filterScanHosts(hosts, query, ports, protocol);
  const { page, pages } = hostPage(params.get('host_page'), result.matches.length);
  const start = (page - 1) * HOSTS_PAGE_SIZE;
  const filtered = !!(query || ports || rawProtocol);
  const availablePorts = Array.from(new Set(hosts.flatMap(host => host.ports.map(port => port.port)))).sort((a, b) => a - b);
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'host_page') next.delete('host_page');
    setParams(next, { replace: true, preventScrollReset: true });
  };
  const reset = () => {
    const next = new URLSearchParams(params);
    keys.forEach(key => next.delete(key));
    setParams(next, { replace: true, preventScrollReset: true });
  };
  const pagination = <nav className="scan-host-pagination" aria-label={t("Страницы хостов")}>
    <span>{result.matches.length ? t("{v0}–{v1} из {v2}", {
  v0: start + 1,
  v1: Math.min(start + HOSTS_PAGE_SIZE, result.matches.length),
  v2: result.matches.length
}) : t("0 хостов")}</span>
    <div><button type="button" className="report-choice" aria-label={t("Предыдущая страница хостов")} disabled={page <= 1} onClick={() => update('host_page', String(page - 1))}><ChevronLeft size={16}/></button>
      <label>{t("Страница")} <input aria-label={t("Номер страницы хостов")} type="number" min={1} max={pages} value={page} onChange={event => { if (event.target.value) update('host_page', String(hostPage(event.target.value, result.matches.length).page)); }}/></label><span>{t("из")} {pages}</span>
      <button type="button" className="report-choice" aria-label={t("Следующая страница хостов")} disabled={page >= pages} onClick={() => update('host_page', String(page + 1))}><ChevronRight size={16}/></button></div>
  </nav>;

  return <div className="scan-host-results">
    <div className="scan-host-filters">
      <label className="scan-host-search"><span><Search size={16}/>{t("Поиск по хостам и сервисам")}</span>
        <input type="search" aria-label={t("Поиск по хостам и сервисам")} placeholder={t("IP, имя хоста, сервис или версия…")} value={query} onChange={event => update('host_q', event.target.value)}/></label>
      <label><span>{t("Порты")}</span><input aria-label={t("Фильтр по портам")} aria-invalid={!!result.error} aria-describedby="scan-host-port-help" list="scan-host-port-options" placeholder={t("Например: 80, 443")} value={ports} onChange={event => update('host_ports', event.target.value)}/></label>
      <datalist id="scan-host-port-options">{availablePorts.map(port => <option key={port} value={port}/>)}</datalist>
      <label><span>{t("Протокол")}</span><select aria-label={t("Фильтр по протоколу")} value={protocol} onChange={event => update('host_protocol', event.target.value)}><option value="">{t("Любой")}</option>{protocols.map(item => <option key={item} value={item}>{item.toUpperCase()}</option>)}</select></label>
      <div className="scan-host-filter-actions">{tools}<button type="button" className="report-button report-button-secondary" disabled={!filtered && !params.has('host_page')} onClick={reset}><X size={15}/>{t("Сбросить")}</button></div>
      <p id="scan-host-port-help" className={result.error ? 'scan-host-filter-error' : 'scan-host-filter-help'} role={result.error ? 'alert' : undefined}>{result.error || t("Порты — точные номера через запятую. Несколько портов: любой из указанных. Поиск работает по всему скану.")}</p>
      <div className="scan-host-count" role="status" aria-live="polite"><SlidersHorizontal size={15}/>{t('Найдено {v0} из {v1} · Подходящих портов: {v2}',{v0:formatNumber(result.matches.length),v1:hostCount(hosts.length),v2:formatNumber(result.portCount)})}</div>
    </div>
    {result.matches.length > 0 ? <>
      {pages > 1 && pagination}
      <div className="space-y-4">{result.matches.slice(start, start + HOSTS_PAGE_SIZE).map(({ host, ports: matchedPorts }) => <HostCard key={`${host.id}:${query}:${ports}:${protocol}`} host={host} matchedPorts={matchedPorts}/>)}</div>
      {pages > 1 && pagination}
    </> : <div className="report-empty"><Search size={24}/><p>{result.error ? t("Проверьте номера портов") : t("По выбранным условиям хостов не найдено")}</p>{filtered && <button type="button" className="report-choice" onClick={reset}>{t("Сбросить фильтры")}</button>}</div>}
  </div>;
}
