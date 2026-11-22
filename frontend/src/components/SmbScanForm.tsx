import {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {Play, Square, Loader2} from 'lucide-react';
import {t, uiText} from '../i18n/core';
import {startSmbScan, getSmbJob, cancelSmbScan, openSmbSession, createSecretWorkspace} from '../api/client';
import type {SmbJob, SmbSession, SmbReport, SmbStart} from '../types/smb';

export interface SmbFileRequest {host: string; account: string|null; method?: string; nonce: number;}
function errorText(error: unknown) {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
  return typeof detail === 'string' ? uiText(detail) : t('Не удалось выполнить SMB-запрос. Проверьте параметры и доступность сервера.');
}

export default function SmbScanForm({scanId, defaultTargets, onReports, fileRequest, onSession, targetRequest, refreshKey, connectionRequest, onBusy, purpose='smb', initiallyOpen=false, onWorkspace, defaultAccount, disabled=false}: {
  disabled?:boolean;
  defaultAccount?:string|null;
  purpose?:'smb'|'secrets';
  initiallyOpen?:boolean;
  onWorkspace?:(workspace:{id:number;targets:string})=>void;
  connectionRequest?:{report:SmbReport;nonce:number}|null;
  onBusy?:(busy:boolean)=>void;
  refreshKey?:number;
  targetRequest?:{targets:string;nonce:number;collectFiles?:boolean}|null;
  scanId: number; defaultTargets: string; onReports: () => void; fileRequest?: SmbFileRequest|null; onSession?: (session:SmbSession,scanId?:number)=>void;
}) {
  const [connectReport,setConnectReport]=useState<SmbReport|null>(null);
  const [settingsOpen,setSettingsOpen] = useState(initiallyOpen);
  const [mode, setMode] = useState<'anonymous'|'credentials'>(defaultAccount?'credentials':'anonymous');
  const [credentialType, setCredentialType] = useState<'password'|'ntlm'|'kerberos'>('password');
  const [username, setUsername] = useState((defaultAccount||'').split('\\').slice(-1)[0]);
  const [domain, setDomain] = useState((defaultAccount||'').includes('\\')?(defaultAccount||'').split('\\')[0]:'');
  const [spider, setSpider] = useState(purpose==='secrets');
  const [job, setJob] = useState<SmbJob|null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const callback = useRef(onReports); callback.current = onReports;
  const mounted = useRef(true);
  const generation = useRef(0);
  const panel = useRef<HTMLElement>(null);
  const targetField = useRef<HTMLInputElement>(null);
  const secretField = useRef<HTMLInputElement>(null);
  const busy = job?.status === 'queued' || job?.status === 'running';
  useEffect(()=>{if(defaultTargets&&targetField.current&&!targetField.current.value)targetField.current.value=defaultTargets;},[defaultTargets]);
  useEffect(()=>{onBusy?.(!!busy||sending);},[busy,sending]);
  useEffect(()=>{
    if(!connectionRequest)return;
    const report=connectionRequest.report;
    setConnectReport(report);setSettingsOpen(true);
    if(targetField.current)targetField.current.value=report.host;
    setMode(report.account?'credentials':'anonymous');
    setCredentialType(report.auth_method==='ntlm'?'ntlm':report.auth_method==='kerberos'?'kerberos':'password');
    const parts=(report.account||'').split('\\');setUsername(parts[parts.length-1]||'');setDomain(parts.length>1?parts[0]:'');
    panel.current?.scrollIntoView?.({behavior:'smooth',block:'nearest'});
  },[connectionRequest]);
  useEffect(()=>{
    if(!targetRequest||busy||sending)return;
    setConnectReport(null);
    if(targetField.current)targetField.current.value=targetRequest.targets;
    setSettingsOpen(true);
    if(targetRequest.collectFiles)setSpider(true);
    panel.current?.scrollIntoView?.({behavior:'smooth',block:'nearest'});
  },[targetRequest]);
  useEffect(() => {
    if (!fileRequest) return;
    if (targetField.current) targetField.current.value = fileRequest.host;
    setSpider(true);setSettingsOpen(true);
    const authenticated = !!fileRequest.account;
    setMode(authenticated ? 'credentials' : 'anonymous');
    setCredentialType(fileRequest.method === 'ntlm' ? 'ntlm' : fileRequest.method === 'kerberos' ? 'kerberos' : 'password');
    const parts = (fileRequest.account || '').split('\\');
    setUsername(parts[parts.length-1] || ''); setDomain(parts.length > 1 ? parts[0] : '');
    panel.current?.scrollIntoView?.({behavior:'smooth', block:'start'});
  }, [fileRequest]);
  useEffect(()=>{if(connectionRequest&&settingsOpen&&mode==='credentials')secretField.current?.focus?.();},[connectionRequest,settingsOpen,mode,credentialType]);
  useEffect(() => {if (fileRequest && mode==='credentials') secretField.current?.focus?.();}, [fileRequest, mode, credentialType]);
  useEffect(() => {
    if(!scanId){mounted.current=true;setReady(true);return()=>{mounted.current=false;};}
    let active = true; let inFlight = false; let fingerprint = '';
    mounted.current = true;
    const refresh = async () => {
      if (inFlight) return;
      inFlight = true;
      const requestGeneration = generation.current;
      try {
        const value = await getSmbJob(scanId);
        if (!active || requestGeneration !== generation.current) return;
        setJob(value); setReady(true);
        const next = JSON.stringify(value?.report_ids || []);
        if (next !== fingerprint && value?.report_ids.length) callback.current();
        fingerprint = next;
      } catch (e) {if (active) {setError(errorText(e)); setReady(true);}}
      finally {inFlight = false;}
    };
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => {active = false; mounted.current = false; clearInterval(timer);};
  }, [scanId,refreshKey]);
  const status = (value: string) => (({queued:t('В очереди'),running:t('Выполняется'),completed:t('Завершён'),partial:t('SMB: частичный результат'),failed:t('Ошибка'),cancelled:t('Отменено')} as Record<string,string>)[value] || value);
  const choice = mode==='anonymous' ? 'anonymous' : credentialType;

  return <section ref={panel} className={`report-panel smb-scan-panel${settingsOpen?'':' is-collapsed'}${!settingsOpen&&!job&&!error?' smb-panel-empty':''}`}>
    <details className="smb-scan-setup" open={settingsOpen} onToggle={event=>setSettingsOpen(event.currentTarget.open)}>
    <summary>{connectReport?t('Подключение к файлам'):purpose==='secrets'?t('Цели и учётка'):t('Проверка доступа')}{purpose!=='secrets'&&<span>{t('Сеть · учётная запись · настройки')}</span>}</summary>
    {connectReport&&<p className="smb-hint">{t('Учётка используется для просмотра и сбора файлов. Подключение действует 15 минут.')}</p>}
    <form onSubmit={async event => {
      event.preventDefault(); if (busy || sending || disabled) return;
      const element = event.currentTarget;
      const form = new FormData(element);
      generation.current++;
      let workspace:{id:number;targets:string}|null=null;
      setSending(true); setError('');
      try {
        const serverNames: Record<string,string> = {};
        if (mode==='credentials' && credentialType==='kerberos') {
          for (const line of String(form.get('server_names')||'').split(/[\n,;]+/).map(s=>s.trim()).filter(Boolean)) {
            const pair = line.split('=');
            if (pair.length!==2 || !pair[0].trim() || !pair[1].trim() || serverNames[pair[0].trim()]) throw Error('invalid mapping');
            serverNames[pair[0].trim()] = pair[1].trim();
          }
        }
        const request:SmbStart = {targets:String(form.get('targets')||''),mode,credential_type:credentialType,
          username:mode==='credentials'?String(form.get('username')||''):'',domain:mode==='credentials'?String(form.get('domain')||''):'',
          password:mode==='credentials'&&credentialType==='password'?String(form.get('password')||''):'',
          nt_hash:mode==='credentials'&&credentialType==='ntlm'?String(form.get('nt_hash')||''):'',
          aes_key:mode==='credentials'&&credentialType==='kerberos'?String(form.get('aes_key')||''):'',
          kdc_host:mode==='credentials'&&credentialType==='kerberos'?String(form.get('kdc_host')||''):'',server_names:serverNames,
          spider:purpose==='secrets'?true:spider,depth:Number(form.get('depth')||3),max_entries:Number(form.get('max_entries')||10000),include_admin:form.get('include_admin')==='on'};
        let value:SmbJob|null=null;
        if(connectReport){const connected=await openSmbSession(scanId,connectReport.id,request);if(mounted.current)onSession?.(connected);}
        else {if(!scanId){workspace=await createSecretWorkspace(request.targets);}value=await startSmbScan(workspace?.id||scanId,request);}
        for (const name of ['password','nt_hash','aes_key']) {
          const field = element.elements.namedItem(name) as HTMLInputElement|null;
          if (field) field.value = '';
        }
        if (mounted.current) {if(value)setJob(value);setSettingsOpen(false);if(value?.browse_session)onSession?.(value.browse_session,workspace?.id||scanId);if(workspace)onWorkspace?.(workspace);}
      } catch (e) {if (mounted.current) {setError(errorText(e));if(workspace)onWorkspace?.(workspace);}}
      finally {if (mounted.current) setSending(false);}
    }}>
      <fieldset disabled={busy || sending || disabled || !ready} className="space-y-3 mt-3">
        <div className={`smb-credential-grid${mode==='credentials'?' has-credentials':''}`}>
          <label>{t('Сеть или IP')}<input ref={targetField} name="targets" readOnly={!!connectReport} defaultValue={defaultTargets} required maxLength={4000} placeholder="192.168.1.0/24"/></label>
          <label>{t('Как подключаться')}<select aria-label={t('Как подключаться')} value={choice} onChange={e=>{const v=e.target.value;setMode(v==='anonymous'?'anonymous':'credentials');if(v!=='anonymous')setCredentialType(v as typeof credentialType);}}>
            <option value="anonymous">{t('Без учётки')}</option><option value="password">{t('Логин и пароль')}</option><option value="ntlm">{t('Логин и NTLM-хэш')}</option><option value="kerberos">{t('Логин и Kerberos-ключ')}</option>
          </select></label>
        {mode==='credentials' && <>
          <label>{t('Логин')}<input name="username" value={username} onChange={e=>setUsername(e.target.value)} maxLength={253} required autoComplete="off" placeholder="DOMAIN\user"/></label>
          {credentialType==='password' ? <label>{t('Пароль')}<input ref={secretField} key="password" type="text" name="password" spellCheck={false} autoCapitalize="none" maxLength={1024} autoComplete="new-password"/></label> : credentialType==='ntlm' ? <label>{t('NT-хэш или LM:NT')}<input ref={secretField} key="ntlm" type="password" name="nt_hash" required minLength={32} maxLength={65} autoComplete="new-password"/></label> : <label>{t('AES-ключ Kerberos')}<input ref={secretField} key="kerberos" type="password" name="aes_key" required minLength={32} maxLength={64} autoComplete="new-password"/></label>}
        </>}
        </div>
        {connectReport&&mode==='credentials'&&credentialType!=='kerberos'&&<label>{t('Домен, если не указан в логине')}<input name="domain" value={domain} onChange={event=>setDomain(event.target.value)} maxLength={253}/></label>}
        {mode==='credentials' && credentialType==='kerberos' && <div className="smb-form-grid">
          <label>{t('Домен')}<input name="domain" value={domain} onChange={e=>setDomain(e.target.value)} required maxLength={253}/></label>
          <label>{t('Контроллер домена (KDC)')}<input name="kdc_host" required maxLength={253} placeholder="192.168.1.10"/></label>
          <label>{t('Имена серверов для SPN: IP=DNS-имя')}<textarea name="server_names" required rows={3} maxLength={16000} placeholder="192.168.1.20=fs01.example.local"/></label>
        </div>}
        <div className="smb-preparation-footer">
        {!connectReport&&<details className="smb-advanced"><summary>{t('Дополнительные настройки')}</summary><div className="space-y-3 mt-3">
          {mode==='credentials' && credentialType!=='kerberos' && <label>{t('Домен, если не указан в логине')}<input name="domain" value={domain} onChange={e=>setDomain(e.target.value)} maxLength={253}/></label>}
          <div className="smb-scan-options">{purpose!=='secrets'&&<label><input type="checkbox" name="spider" checked={spider} onChange={e=>setSpider(e.target.checked)}/>{t('Собрать список файлов')}</label>}<label><input type="checkbox" name="include_admin"/>{t('Обходить C$, D$, ADMIN$')}</label></div>
          <div className="smb-start-grid"><label>{t('Глубина вложенных папок')}<input type="number" name="depth" min={0} max={20} defaultValue={3}/></label><label>{t('Лимит записей на хост')}<input type="number" name="max_entries" min={1} max={100000} defaultValue={10000}/></label></div>
          <p className="smb-hint">{t('Проверка идёт с worker: TCP 445, до 256 адресов, до 15 минут. По одной попытке входа на хост; при ошибке учётки запуск останавливается.')}</p>
        </div></details>}
        {fileRequest && spider && <p role="status" className="smb-hint">{t('Компьютер выбран для обхода файлов. Для входа с учёткой введите секрет повторно.')}</p>}
        <div className="smb-actions"><button className="report-button report-button-primary" type="submit"><Play size={15}/>{sending?t('Запуск…'):connectReport?t('Подключиться'):purpose==='secrets'?t('Найти шары и файлы'):spider?t('Собрать список файлов'):t('Проверить доступ')}</button>{spider && purpose!=='secrets' && !connectReport && <button type="button" className="report-choice" onClick={()=>setSpider(false)}>{t('Только найти шары')}</button>}</div>
        </div>
      </fieldset>
    </form>
    </details>
    {job && <div className="smb-job mt-4" role="status"><span>{status(job.status)} · {job.completed}/{job.options.targets.length}{job.current_host?` · ${job.current_host}`:''}</span>{job.phase==='discovery' && busy && <span>{t('Поиск компьютеров с SMB…')}</span>}{job.skipped!==undefined && <span>{t('Не ответили по TCP 445: {count}',{count:job.skipped})}</span>}{busy && <><Loader2 size={15} className="animate-spin"/><button className="report-button report-button-secondary" disabled={sending} onClick={async()=>{generation.current++;setSending(true);try {const value=await cancelSmbScan(scanId,job.id);if(mounted.current)setJob(value);}catch(e){if(mounted.current)setError(errorText(e));}finally{if(mounted.current)setSending(false);}}}><Square size={13}/>{t('Остановить SMB')}</button></>}{job.error && <p className="text-red-400">{uiText(job.error)}</p>}</div>}
    {error && <p role="alert" className="text-red-400 mt-3">{error}</p>}
  </section>;
}
