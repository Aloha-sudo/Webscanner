import { uiText, t, formatDateTime, formatNumber } from '../i18n/core';
import { useProject } from '../context/ProjectContext';
import axios from 'axios';
import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { stageLabel, speedLabel, profileLabel, formatDuration } from '../utils/format';
import { getScan, updateScanComment } from '../api/client';
import type { ScanDetail } from '../types';
import ScanHosts from '../components/ScanHosts';
import DnsResults from '../components/DnsResults';
import ScreenshotGallery from '../components/ScreenshotGallery';
import {
  ArrowLeft, Loader2, Server, Globe, Camera, AlertCircle,
  Pencil, Save, X, MessageSquare, Timer, Tag, Download, ChevronDown,
} from 'lucide-react';

export default function ScanDetailPage() {
  const {projects}=useProject();
  const exportMenu=useRef<HTMLDetailsElement>(null);
  useEffect(()=>{
    const close=(event:MouseEvent)=>{if(exportMenu.current && event.target instanceof Node && !exportMenu.current.contains(event.target))exportMenu.current.open=false;};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape' && exportMenu.current){exportMenu.current.open=false;}};
    document.addEventListener('mousedown',close);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',escape);};
  },[]);
  const { id } = useParams<{ id: string }>();
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [savingSource, setSavingSource] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [sourceOpen,setSourceOpen]=useState(false);
  const [resultView,setResultView]=useState<'hosts'|'screenshots'>('hosts');
  const [recovering, setRecovering] = useState(false);
  const [recoveryMessage, setRecoveryMessage] = useState('');
  const [loading, setLoading] = useState(true);

  // Комментарий: редактирование
  const [editing, setEditing] = useState(false);
  const [commentDraft, setCommentDraft] = useState('');
  const [savingComment, setSavingComment] = useState(false);

  const fetchScan = async () => {
    if (!id) return;
    try {
      const data = await getScan(parseInt(id));
      setScan(data);
    } catch (err) {
      console.error('Failed to load scan:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setSourceOpen(false);setEditing(false);setResultView('hosts');fetchScan();
  }, [id]);

  useEffect(() => {
    if (!scan || (['completed','failed','cancelled'].includes(scan.status) && !['queued','running'].includes(scan.dns_status||''))) {
      return;
    }
    const interval = setInterval(fetchScan, 3000);
    return () => clearInterval(interval);
  }, [scan]);

  const startEditComment = () => {
    if (!scan) return;
    setCommentDraft(scan.comment || '');
    setEditing(true);
  };

  const cancelEditComment = () => {
    setEditing(false);
    setCommentDraft('');
  };

  const saveComment = async () => {
    if (!scan) return;
    setSavingComment(true);
    try {
      const updated = await updateScanComment(scan.id, commentDraft);
      setScan({ ...scan, comment: updated.comment ?? null });
      setEditing(false);
      setCommentDraft('');
    } catch (err) {
      console.error('Failed to save comment:', err);
      alert(t("Не удалось сохранить комментарий"));
    } finally {
      setSavingComment(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-accent animate-spin" />
      </div>
    );
  }

  if (!scan) {
    return (
      <div className="ui-surface border border-border rounded-xl p-12 text-center">
        <div className="text-gray-400">{t("Скан не найден")}</div>
        <Link to="/" className="text-accent hover:underline mt-2 inline-block">{t("← Вернуться к списку")} </Link>
      </div>
    );
  }

  const exportUrl = (fmt: string) => `/api/scans/${scan.id}/export?format=${fmt}`;

  return (
    <div className="space-y-5 scan-detail-workspace">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          to="/"
          className="p-2 rounded-lg text-gray-400 hover:text-accent hover:bg-accent/10 transition"
        >
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-gray-500">{t("Скан #")}{scan.id}</div>
          <div className="text-2xl font-bold font-mono text-accent">{scan.target}</div>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-xs">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md ui-subtle border border-border text-gray-300">
              <Tag className="w-3 h-3" />
              {profileLabel(scan)}
            </span>
            {!scan.scan_type.startsWith('import-') && <span className="scan-speed">{t("Скорость:")} {speedLabel(scan.speed)}</span>}
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md ui-subtle border border-border text-gray-400">
              <Timer className="w-3 h-3" />
              {formatDuration(scan.duration_seconds)}
            </span>
            {scan.created_at && (
              <span className="text-gray-600">
                {formatDateTime(scan.created_at)}
              </span>
            )}
            <details ref={exportMenu} className="scan-export">
              <summary aria-label={t("Экспорт отчёта")}><Download size={14}/>{t("Экспорт")}<ChevronDown size={13}/></summary>
              <div className="scan-export-options">
                {([['json','JSON',t("Структурированные данные")],['csv','CSV',t("Таблица для Excel")],['xml','XML',t("XML-отчёт")]] as const).map(([format,label,hint])=><a key={format} href={exportUrl(format)} download={`scan_${scan.id}.${format}`} onClick={()=>{if(exportMenu.current)exportMenu.current.open=false;}}><span>{label}</span><small>{hint}</small></a>)}
              </div>
            </details>
          </div>
        </div>
        <StatusBadge status={scan.status} />
      </div>

      <div className="scan-detail-context"><span><strong>{t("Проект:")}</strong> {scan.project?`${scan.project} / ${scan.network||t("Без части сети")}`:t("Без проекта")}</span><span><strong>{t("Источник:")}</strong> {scan.source_host||t("Не указан")}</span><button className="report-choice" aria-expanded={sourceOpen} onClick={()=>setSourceOpen(!sourceOpen)}>{t("Изменить привязку")}</button></div>
      <div className="scan-detail-summary">
        <StatBox label={t("Хосты")} value={scan.total_hosts} icon={Server}/><StatBox label={t("Порты")} value={scan.total_ports} icon={Server}/><StatBox label={t("Веб-сервисы")} value={scan.total_web} icon={Globe}/><StatBox label={t("Скриншоты")} value={scan.total_screenshots} icon={Camera}/>
        {!scan.comment&&!editing&&<button className="report-choice scan-add-comment" onClick={startEditComment}><MessageSquare size={14}/>{t("Добавить комментарий")}</button>}
      </div>
      {scan.scan_type.startsWith('import-') && <div className="ui-surface border border-border rounded-xl p-4 text-sm text-gray-400">
        <p>{t("Импортированный отчёт ·")} {scan.scan_type.replace('import-', '')}{t(". Область сканирования неизвестна; отсутствие записи не подтверждает закрытие порта.")}</p>
        <a className="text-accent underline" href={`/api/scans/${scan.id}/original`}>{t("Скачать исходный файл")}</a>
      </div>}
      {(scan.exclude_ips || scan.exclude_hosts || scan.exclude_ports) && <details className="report-panel p-4 text-sm space-y-2"><summary className="cursor-pointer font-medium">{t("Исключения сканирования")}</summary>{scan.exclude_ips && <p>{t("IP и сети:")} {scan.exclude_ips}</p>}{scan.exclude_hosts && <p>{t("Хосты:")} {scan.exclude_hosts}</p>}{scan.exclude_ports && <p>{t("TCP-порты:")} {scan.exclude_ports}</p>}</details>}
      {sourceOpen&&<section className="report-panel p-4">
        <div className="scan-detail-editor-heading"><h2>{t("Привязка скана")}</h2><button aria-label={t("Закрыть привязку скана")} disabled={savingSource} onClick={()=>setSourceOpen(false)}><X size={17}/></button></div>
        <form key={`${scan.project}-${scan.network}-${scan.source_host}`} className="team-metadata mt-4 space-y-3" onSubmit={async e=>{
          e.preventDefault();const form=new FormData(e.currentTarget);setSavingSource(true);setSourceError('');
          try {const metadata={project_id:Number(form.get('project_id'))||null,network_part_id:Number(form.get('network_part_id'))||null,source_host:String(form.get('source_host')||'').trim()||null,author:String(form.get('author')||'').trim()||null};const {data}=await axios.patch(`/api/scans/${scan.id}`,metadata);setScan({...scan,...data});setSourceOpen(false);}
          catch {setSourceError(t("Не удалось сохранить источник"));}finally{setSavingSource(false);}
        }}>
          <div className="team-form-grid"><label>{t("Проект и часть сети")}<select name="network_part_id" defaultValue={scan.network_part_id||''} onChange={e=>{const partId=Number(e.target.value);const p=projects.find(p=>p.parts.some(n=>n.id===partId));const field=e.currentTarget.form?.elements.namedItem('project_id') as HTMLInputElement|null;if(field)field.value=String(p?.id||'');}}><option value="">{t("Без проекта")}</option>{projects.map(p=><optgroup key={p.id} label={p.name}>{p.parts.map(n=><option key={n.id} value={n.id}>{p.name} / {n.name}</option>)}</optgroup>)}</select><input type="hidden" name="project_id" defaultValue={scan.project_id||''}/></label></div>
          <div className="team-form-grid"><label>{t("Точка сканирования")}<input name="source_host" defaultValue={scan.source_host||''} placeholder={t("Исходный хост")} maxLength={253}/></label><label>{t("Автор")}<input name="author" defaultValue={scan.author||''} placeholder={t("Имя участника")} maxLength={120}/></label></div>
          <button disabled={savingSource} className="report-button report-button-secondary">{savingSource?t("Сохранение…"):t("Сохранить привязку")}</button>
          {sourceError && <p role="alert" className="text-red-400 text-sm">{sourceError}</p>}
          <p className="text-xs text-gray-500">{t("Выберите существующие проект и часть сети для связанных отчётов. После этого они появятся в разделе «Карта сети».")}</p>
        </form>
      </section>}
      {/* Comment */}
      {(scan.comment||editing)&&<div className="ui-surface border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <MessageSquare className="w-4 h-4" />{t("Комментарий")} </div>
          {!editing && (
            <button
              onClick={startEditComment}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs text-gray-400 hover:text-accent hover:bg-accent/10 transition"
            >
              <Pencil className="w-3 h-3" />{t("Редактировать")} </button>
          )}
        </div>

        {!editing ? (
          <div className="text-sm text-gray-200 whitespace-pre-wrap min-h-[2em]">
            {scan.comment ? scan.comment : <span className="text-gray-600 italic">{t("Нет комментария")}</span>}
          </div>
        ) : (
          <div className="space-y-2">
            <textarea
              value={commentDraft}
              onChange={(e) => setCommentDraft(e.target.value)}
              className="w-full px-3 py-2 ui-subtle border border-border rounded-lg text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/50 resize-none"
              rows={3}
              maxLength={1000}
              autoFocus
            />
            <div className="flex items-center gap-2 justify-end">
              <button
                onClick={cancelEditComment}
                disabled={savingComment}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-gray-200 transition disabled:opacity-50"
              >
                <X className="w-3 h-3" />{t("Отмена")} </button>
              <button
                onClick={saveComment}
                disabled={savingComment}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent text-bg hover:bg-accent/80 transition disabled:opacity-50"
              >
                {savingComment ? (
                  <><Loader2 className="w-3 h-3 animate-spin" />{t("Сохранение...")}</>
                ) : (
                  <><Save className="w-3 h-3" />{t("Сохранить")}</>
                )}
              </button>
            </div>
          </div>
        )}
      </div>}

      {/* Progress */}
      {scan.status === 'running' && (
        <div className="ui-surface border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />
              <span className="text-gray-300">{stageLabel(scan.stage)}</span>
            </div>
            <span className="text-sm text-gray-400">{scan.progress}%</span>
          </div>
          <div className="h-2 ui-subtle rounded-full overflow-hidden">
            <div
              className="h-full bg-yellow-400 transition-all"
              style={{ width: `${scan.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {scan.error_message && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-red-400 font-semibold">{t("Ошибка")}</div>
            <div className="text-sm text-red-300 mt-1">{uiText(scan.error_message)}</div>
          </div>
        </div>
      )}

      {(scan.status === 'failed' || scan.status === 'cancelled') && <div className="report-panel p-4 space-y-3">
        <p className="text-sm">{t("Если скан прервался после веб-проверки, можно восстановить найденные сервисы из сохранённого файла. Это не запускает новый скан и не меняет его статус.")}</p>
        <button disabled={recovering} className="report-button report-button-secondary" onClick={async()=>{
          setRecovering(true); setRecoveryMessage('');
          try { const {data}=await axios.post<ScanDetail>(`/api/scans/${scan.id}/recover-web-results`);setScan(data);setRecoveryMessage(t("Восстановлено веб-сервисов: {v0}", {
  v0: data.total_web
})); }
          catch(e) {setRecoveryMessage(axios.isAxiosError(e) ? e.response?.data?.detail || t("Ошибка восстановления") : t("Ошибка восстановления"));}
          finally {setRecovering(false);}
        }}>{recovering ? t("Восстановление…") : t("Восстановить сохранённые веб-результаты")}</button>
        {recoveryMessage && <p role="status" className="text-sm">{uiText(recoveryMessage)}</p>}
      </div>}
      <div className="scan-result-tabs" role="tablist" aria-label={t("Результаты скана")} onKeyDown={event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        event.preventDefault();const next=event.key==='Home'?'hosts':event.key==='End'?'screenshots':resultView==='hosts'?'screenshots':'hosts';
        setResultView(next);event.currentTarget.querySelectorAll<HTMLButtonElement>('button')[next==='hosts'?0:1]?.focus();
      }}><button role="tab" tabIndex={resultView==='hosts'?0:-1} id="scan-hosts-tab" aria-selected={resultView==='hosts'} aria-controls="scan-hosts-panel" onClick={()=>setResultView('hosts')}><Server size={15}/>{t("Хосты и сервисы (")}{scan.total_hosts})</button><button role="tab" tabIndex={resultView==='screenshots'?0:-1} id="scan-screenshots-tab" aria-selected={resultView==='screenshots'} aria-controls="scan-screenshots-panel" onClick={()=>setResultView('screenshots')}><Camera size={15}/>{t("Скриншоты (")}{scan.total_screenshots})</button></div>
      {/* Hosts */}
      {resultView==='hosts'&&<section id="scan-hosts-panel" role="tabpanel" aria-labelledby="scan-hosts-tab">
      {scan.hosts.length > 0 && (
        <div className="mt-4">
          <ScanHosts key={scan.id} hosts={scan.hosts} tools={<DnsResults scan={scan} onQueued={fetchScan}/>} />
        </div>
      )}

      {!scan.hosts.length&&<p className="report-empty">{scan.status==='completed'?t("Живых хостов не найдено"):t("Результаты хостов пока отсутствуют")}</p>}
      </section>}
      {/* Screenshots */}
      {resultView==='screenshots'&&<section id="scan-screenshots-panel" role="tabpanel" aria-labelledby="scan-screenshots-tab">
      {scan.screenshots.length > 0 && (
        <div>
          <h2 className="text-xl font-bold mb-3 flex items-center gap-2">
            <Camera className="w-5 h-5 text-accent" />{t("Скриншоты (")}{scan.screenshots.length})
          </h2>
          <ScreenshotGallery screenshots={scan.screenshots} />
        </div>
      )}

      {!scan.screenshots.length&&<p className="report-empty">{t("Скриншотов пока нет. Они появятся после обнаружения веб-сервисов и создания снимков.")}</p>}
      </section>}

    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    queued:    { label: t("В очереди"),    cls: 'bg-gray-500/10 text-gray-400 border-gray-500/30' },
    running:   { label: t("Выполняется"),  cls: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30' },
    completed: { label: t("Завершён"),     cls: 'bg-accent/10 text-accent border-accent/30' },
    failed:    { label: t("Ошибка"),       cls: 'bg-red-500/10 text-red-400 border-red-500/30' },
    cancelled: { label: t("Отменён"),      cls: 'bg-gray-500/10 text-gray-500 border-gray-500/30' },
  };
  const cfg = map[status] || map.queued;
  return (
    <span className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function StatBox({label,value,icon:Icon}:{label:string;value:number;icon:typeof Server}){
  return <div className="scan-detail-stat"><Icon size={22}/><span><strong>{formatNumber(value)}</strong>{label}</span></div>;
}
