import { uiText, t, formatDate, itemCount } from '../i18n/core';
import { Link } from 'react-router-dom';
import { Trash2, XCircle, Loader2, RotateCcw } from 'lucide-react';
import type { Scan } from '../types';
import { formatDuration, profileLabel, speedLabel } from '../utils/format';
const statuses = {get queued() {
  return t("В очереди");
},get running() {
  return t("Выполняется");
},get completed() {
  return t("Завершён");
},get failed() {
  return t("Ошибка");
},get cancelled() {
  return t("Отменён");
}};
const stages: Record<string,string> = {get queued() {
  return t("Ожидание worker");
},get starting() {
  return t("Подготовка");
},get rustscan() {
  return t("Поиск портов");
},get verifying() {
  return t("Проверка портов");
},get nmap() {
  return t("Определение сервисов");
},get parsing_nmap() {
  return t("Обработка результатов");
},get httpx() {
  return t("Проверка веб-сервисов");
},get web_fallback() {
  return t("Дополнительная проверка HTTPS · до 2 минут");
},get gowitness() {
  return t("Создание скриншотов");
},get completed() {
  return t("Завершено");
},get failed() {
  return t("Ошибка");
},get cancelled() {
  return t("Отменено");
},get imported() {
  return t("Загружен из файла");
}};
export default function ScanTable({scans,onDelete,onCancel,onRetry,retryingIds}: {scans: Scan[]; onDelete:(id:number)=>void; onCancel:(id:number)=>void; onRetry:(id:number)=>void; retryingIds:ReadonlySet<number>}) {
  if(!scans.length) return <div className="report-panel report-empty">{t("Сканов пока нет. Создайте первый скан в форме выше.")}</div>;
  return <div className="scan-history"><table className="report-table"><thead><tr><th>{t("Скан / цель")}</th><th>{t("Источник")}</th><th>{t("Статус и этап")}</th><th>{t("Результаты")}</th><th>{t("Время")}</th><th className="scan-actions">{t("Действия")}</th></tr></thead><tbody>{scans.map(scan=>{
    const active = scan.status === 'running' || scan.status === 'queued';
    return <tr key={scan.id}><td><Link className="scan-target" to={`/scan/${scan.id}`}>#{scan.id} · {scan.target}</Link><div className="scan-meta">{scan.project && <div>{t("Проект:")} {scan.project} / {scan.network||t("Без части сети")}</div>}{t("Порты:")} {profileLabel(scan)}{!scan.scan_type.startsWith('import-') && <span className="scan-speed">{t("Скорость:")} {speedLabel(scan.speed)}</span>}{(scan.exclude_ips || scan.exclude_hosts || scan.exclude_ports) && <div>{t("Есть исключения · см. детали")}</div>}</div></td>
      <td className="scan-source-cell">{scan.source_host?.trim() || t("Не указан")}</td>
      <td><span className={`scan-status ${scan.status}`}>{scan.status==='running' && <Loader2 size={13} className="animate-spin"/>}{statuses[scan.status]}</span>{active && <><div className="scan-meta">{stages[scan.stage] || scan.stage} · {scan.progress}%</div><div className="scan-row-progress" role="progressbar" aria-label={t("Прогресс скана #{v0}", {
  v0: scan.id
})} aria-valuemin={0} aria-valuemax={100} aria-valuenow={scan.progress}><span style={{width:`${Math.max(0,Math.min(100,scan.progress))}%`}}/></div></>}{scan.error_message && <div className="scan-error" title={uiText(scan.error_message)}>{uiText(scan.error_message)}</div>}</td>
      <td><div className="scan-counts"><span>{itemCount(scan.total_hosts,'host')}</span><span>{itemCount(scan.total_ports,'port')}</span></div><div className="scan-meta">{scan.total_web} {t("веб-сервисов ·")} {itemCount(scan.total_screenshots,'screenshot')}</div></td>
      <td className="whitespace-nowrap"><span>{formatDuration(scan.duration_seconds)}</span><div className="scan-meta">{formatDate(scan.created_at)}</div></td>
      <td className="scan-actions"><div className="scan-action-buttons"><Link to={`/scan/${scan.id}`} className="report-choice">{t("Открыть")}</Link>{!active&&!scan.scan_type.startsWith('import-')&&<button onClick={()=>onRetry(scan.id)} disabled={retryingIds.has(scan.id)} className="report-choice" aria-label={t("Повторить скан #{v0}", {
  v0: scan.id
})} title={t("Новый скан с теми же параметрами")}>{retryingIds.has(scan.id)?<Loader2 size={14} className="animate-spin"/>:<RotateCcw size={14}/>} {retryingIds.has(scan.id)?t("Запуск…"):t("Повторить")}</button>}{active ? <button onClick={()=>onCancel(scan.id)} className="scan-action-button" title={t("Остановить скан")}><XCircle size={15}/>{t("Остановить")}</button> : <button onClick={()=>{if(confirm(t("Удалить скан #{v0} и его файлы?", {
  v0: scan.id
})))onDelete(scan.id);}} className="scan-action-button danger" aria-label={t("Удалить скан #{v0}", {
  v0: scan.id
})} title={t("Удалить скан")}><Trash2 size={15}/></button>}</div></td>
    </tr>;
  })}</tbody></table></div>;
}
