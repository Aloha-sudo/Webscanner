import {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {Folder, Upload, Loader2, MoreHorizontal, Shield} from 'lucide-react';
import {t, uiText} from '../i18n/core';
import {listSmbReports, importSmbReport, collectSmbFiles, checkSmbAccess} from '../api/client';
import SmbScanForm from './SmbScanForm';
import SmbShares from './SmbShares';
import SmbHistory from './SmbHistory';
import SmbFileSearch from './SmbFileSearch';
import SmbExplorer from './SmbExplorer';
import {readSmbSession,saveSmbSession,clearSmbSession,sessionApplies} from '../utils/smbSession';
import {closeSmbSession} from '../api/client';
import LocalDateTimeInput from './LocalDateTimeInput';
import {validLocalDateTime} from '../utils/localDateTime';
import type {ScanDetail} from '../types';
import type {SmbReport, SmbSession, SmbEntry, SmbExplorerLocation} from '../types/smb';

function failure(error: unknown): string {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
  return typeof detail === 'string' ? uiText(detail) : t('Не удалось загрузить SMB-данные');
}

export default function SmbBrowser({scan}: {scan: ScanDetail}) {
  const smbHosts=[...new Set(scan.hosts.filter(host=>host.ports.some(port=>port.port===445&&port.protocol.toLowerCase()==='tcp'&&port.state==='open')).map(host=>host.ip))];
  const defaults=(smbHosts.length?smbHosts:scan.hosts.map(host=>host.ip)).slice(0,256).join(', ');
  const [targetRequest,setTargetRequest]=useState<{targets:string;nonce:number;collectFiles?:boolean}|null>(null);
  const selectTargets=(targets:string)=>setTargetRequest(previous=>({targets,nonce:(previous?.nonce||0)+1}));
  const [connectionRequest,setConnectionRequest]=useState<{report:SmbReport;nonce:number}|null>(null);
  const [jobBusy,setJobBusy]=useState(false);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [jobRefresh,setJobRefresh]=useState(0);
  const [collecting,setCollecting]=useState(false);
  const [session,setSession] = useState<SmbSession|null>(()=>readSmbSession(scan.id));
  const [opened,setOpened] = useState<{report:SmbReport;share:string;entry?:SmbEntry, SmbExplorerLocation}|null>(null);
  const openShare=(report:SmbReport,share:string)=>{setOpened({report,share});setFileSearch(false);};
  const [fileSearch,setFileSearch] = useState(false);
  const [revision, setRevision] = useState(0);
  const [reports, setReports] = useState<SmbReport[]>([]);
  const [observedAt, setObservedAt] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [error, setError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const mounted = useRef(true);
  const openedLink=useRef(false);
  const locations=useRef(new Map<string,SmbExplorerLocation>());
  const updateSession=(value:SmbSession|null)=>{
    if(!value){clearSmbSession(scan.id);setSession(null);return;}
    if(session&&session.token!==value.token)closeSmbSession(scan.id,'',session.token).catch(()=>{});
    setSession(saveSmbSession(scan.id,value));
  };
  const connect=(report?:SmbReport)=>{
    const selected=report||opened?.report||reports.find(item=>item.account===session?.account)||reports[0];
    if(selected)setConnectionRequest(previous=>({report:selected,nonce:(previous?.nonce||0)+1}));
    else selectTargets(defaults);
  };
  const runWithSession=async(action:'collect'|'check',host?:string)=>{
    if(collecting||jobBusy)return;
    const eligible=reports.filter(report=>(!host||report.host===host)&&sessionApplies(session,report));
    if(!session||!eligible.length){
      setTargetRequest(previous=>({targets:host||defaults,nonce:(previous?.nonce||0)+1,collectFiles:action==='collect'}));
      return;
    }
    setCollecting(true);setError('');
    try{
      const targets=[...new Set(eligible.map(report=>report.host))].slice(0,256).join(', ');
      const operation=action==='collect'?collectSmbFiles:checkSmbAccess;
      const job=await operation(scan.id,eligible[0].id,session.token,targets);
      if(!mounted.current)return;
      if(job.browse_session)updateSession(job.browse_session);
      setJobRefresh(value=>value+1);
      setRevision(value=>value+1);
    }catch(e){if(mounted.current){setError(failure(e));if(axios.isAxiosError(e)&&e.response?.status===401)updateSession(null);}}
    finally{if(mounted.current)setCollecting(false);}
  };
  useEffect(()=>{
    if(!session||typeof window==='undefined')return;
    if(!session.expires_at){setSession(saveSmbSession(scan.id,session));return;}
    const timer=window.setTimeout(()=>{clearSmbSession(scan.id);setSession(null);},Math.max(0,(session.expires_at||Date.now())-Date.now()));
    return()=>window.clearTimeout(timer);
  },[scan.id,session?.token,session?.expires_at]);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    listSmbReports(scan.id).then(items => {
      if (!active) return;
      setReports(items);
    }).catch(e => {if (active) setError(failure(e));}).finally(() => {if (active) setLoading(false);});
    return () => {active = false; mounted.current = false;};
  }, [scan.id, revision]);

  useEffect(()=>{
    if(openedLink.current||!reports.length||typeof window==='undefined'||!window.location?.search)return;
    openedLink.current=true;
    const params=new URLSearchParams(window.location.search);
    const report=reports.find(report=>report.id===params.get('report'));
    const share=params.get('share'),path=params.get('file');
    if(!report||!share||!report.shares.some(item=>item.name===share))return;
    const entry:SmbEntry|undefined=path?{share,path,parent:path.split('/').slice(0,-1).join('/'),name:path.split('/').slice(-1)[0],kind:'file',metadata:{}}:undefined;
    setOpened({report,share,entry});
  },[reports]);

  return <div className="smb-workspace space-y-2">
    <header className="smb-workbench-header">
      <div className="smb-workbench-title"><Shield size={18}/><h2>SMB</h2><span>{t('Хостов: {count}',{count:smbHosts.length||scan.hosts.length})}</span></div>
      <button className={`smb-identity ${session?'ready':''}`} onClick={()=>connect()} disabled={collecting||jobBusy} title={t('Изменить учётку или восстановить подключение')}><span className="smb-identity-dot"/>{session?t('Учётка: {account}',{account:session.account||t('Без учётки')}):t('Подключить учётку')}</button>
      {session&&<button className="report-choice" onClick={async()=>{try{await closeSmbSession(scan.id,'',session.token);}catch(e){setError(failure(e));return;}updateSession(null);}}>{t('Отключиться')}</button>}
      <button className="report-button report-button-primary" disabled={collecting||jobBusy||!defaults} onClick={()=>runWithSession('check')}>{collecting?t('Запуск…'):t('Проверить доступ')}</button>
      <details className="smb-tools-menu"><summary aria-label={t('Действия SMB')}><MoreHorizontal size={18}/></summary><div>
        <button disabled={!scan.hosts.length||loading||uploading} onClick={event=>{setImportOpen(value=>!value);setHistoryOpen(false);event.currentTarget.closest('details')?.removeAttribute('open');}}><Upload size={14}/>{t('Импорт SMB')}</button>
        <button onClick={event=>{setHistoryOpen(value=>!value);setImportOpen(false);event.currentTarget.closest('details')?.removeAttribute('open');}}>{t('История и удаление')}</button>
        <button onClick={event=>{selectTargets(defaults);event.currentTarget.closest('details')?.removeAttribute('open');}}>{t('Настройки проверки')}</button>
      </div></details>
    </header>
    <SmbScanForm onBusy={setJobBusy} connectionRequest={connectionRequest} refreshKey={jobRefresh} scanId={scan.id} defaultTargets={defaults} targetRequest={targetRequest} onReports={()=>setRevision(v=>v+1)} onSession={updateSession}/>
    {historyOpen&&<SmbHistory expanded scanId={scan.id} reports={reports} onDeleted={ids=>{
      setReports(items=>items.filter(item=>!ids.includes(item.id)));
      if(opened&&ids.includes(opened.report.id))setOpened(null);
    }}/>}
    {importOpen && <form className="report-panel smb-import" onSubmit={async event => {
      event.preventDefault(); if (uploading) return;
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const file = form.get('file');
      if (!(file instanceof File) || !file.size) {setUploadError(t('Выберите JSON spider_plus')); return;}
      if (file.size > 20 * 1024 * 1024) {setUploadError(t('SMB-файл должен быть не больше 20 МБ')); return;}
      const date = String(form.get('observed_at') || '');
      if (!validLocalDateTime(date)) {setUploadError(t('Укажите корректное время проверки')); return;}
      if (date) {
        const timestamp = new Date(date);
        if (!Number.isFinite(timestamp.getTime())) {setUploadError(t('Укажите корректное время проверки')); return;}
        form.set('observed_at', timestamp.toISOString());
      }
      setUploading(true); setUploadError('');
      try {
        const item = await importSmbReport(scan.id, form);
        if (!mounted.current) return;
        setReports(items => [item, ...items]); setImportOpen(false); setError('');
      } catch (e) {if (mounted.current) setUploadError(failure(e));}
      finally {if (mounted.current) setUploading(false);}
    }}>
      <fieldset disabled={uploading}>
        <div className="smb-form-grid">
          <label>{t('Хост отчёта')}<select name="host" required>{scan.hosts.map(host => <option key={host.id} value={host.ip}>{host.ip}{host.hostname ? ` · ${host.hostname}` : ''}</option>)}</select></label>
          <label>{t('Учётная запись проверки')}<input name="account" placeholder="DOMAIN\\user" maxLength={253}/></label>
          <label>{t('Точка проверки')}<input name="source" placeholder={t('Исходный хост')} maxLength={253}/></label>
          <label>{t('Автор')}<input name="author" maxLength={253}/></label>
          <div className="smb-date-field"><span>{t('Время проверки (местное)')}</span><LocalDateTimeInput label={t('Время проверки (местное)')} value={observedAt} onChange={setObservedAt} disabled={uploading}/><input type="hidden" name="observed_at" value={observedAt}/></div>
          <label>{t('JSON spider_plus')}<input name="file" type="file" accept=".json,application/json" required/></label>
        </div>
        <p className="smb-hint">{t('Указывайте учётку без пароля. Время импорта хранится отдельно от времени проверки.')}</p>
        <div className="smb-actions"><button type="submit" className="report-button report-button-primary">{uploading ? t('Импорт…') : t('Импортировать')}</button><button type="button" className="report-button report-button-secondary" onClick={() => setImportOpen(false)}>{t('Отмена')}</button></div>
      </fieldset>
      {uploadError && <p role="alert" className="text-red-400">{uploadError}</p>}
    </form>}
    {error&&<p role="alert" className="smb-workbench-error">{error}</p>}
    <div className="smb-split-workspace has-selection smb-workbench"><aside className="smb-split-shares" aria-label={t('Хосты и шары')}>
      {loading&&<p role="status"><Loader2 size={16} className="animate-spin inline"/> {t('Загрузка…')}</p>}
      <SmbShares reports={reports} discoveredHosts={smbHosts} onCheckHost={ip=>runWithSession('check',ip)} onOpen={openShare} selected={opened?{reportId:opened.report.id,share:opened.share}:null}/>
    </aside>
    <div className="smb-split-files" aria-label={t('Файлы и результаты поиска')}>
      <SmbFileSearch showResults={fileSearch} collectionAccount={session?(session.account||t('Без учётки')):undefined} onCollect={()=>runWithSession('collect')} collecting={collecting||jobBusy} scanId={scan.id} reports={reports} onActive={setFileSearch} onOpen={(report,entry)=>{setOpened({report,share:entry.share,entry});setFileSearch(false);}}/>
      <div hidden={fileSearch}>
        {opened?<SmbExplorer key={JSON.stringify([opened.report.id,opened.share,opened.entry?.path])} scanId={scan.id} report={opened.report} share={opened.share} initialLocation={opened.entry?undefined:locations.current.get(JSON.stringify([opened.report.id,opened.share]))} onLocationChange={value=>{
          const key=JSON.stringify([opened.report.id,opened.share]);locations.current.set(key,value);
          if(locations.current.size>20)locations.current.delete(locations.current.keys().next().value!);
        }} initialEntry={opened.entry} session={sessionApplies(session,opened.report)?session:null} onSession={updateSession} onConnect={()=>connect(opened.report)} onCollect={()=>runWithSession('collect',opened.report.host)} onClose={()=>setOpened(null)}/>:<div className="smb-workbench-welcome"><Folder size={36}/><h3>{t('Выберите шару слева')}</h3><p>{reports.length?t('Папки и файлы откроются здесь. Или найдите файл строкой выше.'):t('Хосты уже добавлены из скана. Нажмите «Проверить доступ», чтобы получить шары и права.')}</p><button className="report-choice" disabled={jobBusy||collecting||!defaults} onClick={()=>runWithSession('check')}>{t('Проверить доступ')}</button></div>}
      </div>
    </div></div>
  </div>;
}
