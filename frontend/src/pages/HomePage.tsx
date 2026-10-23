import { uiText, t, formatNumber } from '../i18n/core';
import { useProject } from '../context/ProjectContext';
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { listScans, deleteScan, cancelScan, retryScan } from '../api/client';
import type { Scan } from '../types';
import ScanForm from '../components/ScanForm';
import ScanTable from '../components/ScanTable';
import { Activity, RefreshCw, CheckCircle2, AlertCircle, Layers } from 'lucide-react';

export default function HomePage() {
  const {selection,project,part}=useProject();
  const [showAll,setShowAll]=useState(()=>{try{return localStorage.getItem('scanner-show-all')==='true';}catch{return false;}});
  const requestId=useRef(0);
  const filterProject=showAll?null:selection.projectId;
  const filterPart=showAll?null:selection.partId;
  useEffect(()=>{try{localStorage.setItem('scanner-show-all',String(showAll));}catch{}},[showAll]);
  const [scans, setScans] = useState<Scan[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [retryingIds,setRetryingIds]=useState<Set<number>>(new Set());
  const retryLocks=useRef(new Set<number>());
  const [retryError,setRetryError]=useState('');
  const [repeated,setRepeated]=useState<{id:number;original:number}|null>(null);
  const pageRef=useRef(page);pageRef.current=page;

  const fetchScans = async () => {
    const request=++requestId.current;
    setLoading(true);
    try {
      const data = await listScans(page * 50, 50,{project_id:filterProject,network_part_id:filterPart});
      if(request!==requestId.current)return;
      setScans(data.scans);
      setTotal(data.total);
      setLoadError('');
    } catch (err) {
      if(request===requestId.current)setLoadError(t("Не удалось загрузить историю"));
    } finally {
      if(request===requestId.current)setLoading(false);
    }
  };
  const refreshRef=useRef(fetchScans);refreshRef.current=fetchScans;

  const handleRetry=async(id:number)=>{
    if(retryLocks.current.has(id))return;
    retryLocks.current.add(id);setRetryingIds(new Set(retryLocks.current));
    setRetryError('');setRepeated(null);
    try{
      const next=await retryScan(id);
      setRepeated({id:next.id,original:id});
      if(pageRef.current!==0)setPage(0);
      else await refreshRef.current();
    }catch(error){
      setRetryError(axios.isAxiosError(error)&&typeof error.response?.data?.detail==='string'?error.response.data.detail:t("Не удалось повторить скан. Проверьте подключение к серверу."));
    }finally{
      retryLocks.current.delete(id);setRetryingIds(new Set(retryLocks.current));
    }
  };

  useEffect(()=>{setPage(0);},[filterProject,filterPart,showAll]);
  useEffect(() => {
    fetchScans();
  }, [page,filterProject,filterPart,showAll]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchScans, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh,page,filterProject,filterPart,showAll]);

  const handleDelete = async (id: number) => {
    try {
      await deleteScan(id);
      fetchScans();
    } catch (err) {
      setLoadError(t("Не удалось удалить отчёт. Активный скан нужно сначала отменить."));
    }
  };

  const handleCancel = async (id: number) => {
    try {
      await cancelScan(id);
      fetchScans();
    } catch (err) {
      setLoadError(t("Не удалось отменить скан"));
    }
  };

  const runningCount = scans.filter((s) => ['running','queued'].includes(s.status)).length;
  const completedCount = scans.filter((s) => s.status === 'completed').length;

  return (
    <div className="space-y-6">
      {loadError && <p role="alert" className="text-red-400">{loadError}</p>}
      <div><h1 className="text-2xl font-semibold">{t("Сканирование")}</h1></div>
      <div className="scan-summary-strip" aria-label={t("Статистика сканов")}>
        <div><Layers size={22}/><span>{t("Всего")}<strong>{formatNumber(total)}</strong></span></div>
        <div title={t("В текущем списке")}><Activity size={22}/><span>{t("В работе")}<strong>{formatNumber(runningCount)}</strong></span></div>
        <div title={t("В текущем списке")}><CheckCircle2 size={22}/><span>{t("Завершено")}<strong>{formatNumber(completedCount)}</strong></span></div>
        <div title={t("В текущем списке")}><AlertCircle size={22}/><span>{t("Ошибки")}<strong>{scans.filter(scan=>scan.status==='failed').length}</strong></span></div>
        <small>{t("Статусы — по списку ниже")}</small>
      </div>

      {/* Form */}
      <ScanForm onCreated={fetchScans} />

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Activity className="w-5 h-5 text-accent" />{t("Сканы")} </h2>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer"><input type="checkbox" checked={showAll} onChange={e=>{setShowAll(e.target.checked);setPage(0);}} className="w-4 h-4 accent-accent"/>{t("Показать все сканы")}</label>
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 accent-accent"
            />{t("Автообновление")} </label>
          <button
            onClick={fetchScans}
            disabled={loading}
            className="p-2 rounded-lg text-gray-400 hover:text-accent hover:bg-accent/10 transition"
            title={t("Обновить")}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-500">{showAll||!project?t("Показаны сканы всех проектов и сканы без проекта."):t("Показаны сканы: {v0}{v1}.", {
  v0: project.name,
  v1: part ? ` / ${part.name}` : ''
})} {t("Выбор проекта для новых сканов не меняется.")}</p>
      {/* Table */}
      {retryError&&<p role="alert" className="report-alert">{uiText(retryError)}</p>}
      {repeated&&<div role="status" className="report-success">{t("Создан повтор скана #")}{repeated.original}: <Link className="text-accent" to={`/scan/${repeated.id}`}>{t("скан #")}{repeated.id} →</Link></div>}
      <ScanTable scans={scans} onDelete={handleDelete} onCancel={handleCancel} onRetry={handleRetry} retryingIds={retryingIds} />
      <div className="flex gap-4 items-center text-sm">
        <button disabled={page === 0} onClick={() => setPage(page - 1)} className="text-accent disabled:opacity-30">{t("← Назад")}</button>
        <span>{t("Страница")} {page + 1} {t("· Отчётов:")} {total}</span>
        <button disabled={(page + 1) * 50 >= total} onClick={() => setPage(page + 1)} className="text-accent disabled:opacity-30">{t("Далее →")}</button>
      </div>
    </div>
  );
}

