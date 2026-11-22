import {useEffect,useRef,useState} from 'react';
import axios from 'axios';
import {ArrowLeft,ArrowRight,Folder,FileText,Download,Eye,Shield,Copy,Loader2,RefreshCw,Terminal} from 'lucide-react';
import {t,uiText,formatDateTime} from '../i18n/core';
import {browseSmbReport,startSmbFileAction,getSmbFileAction,downloadSmbFile} from '../api/client';
import {copyText} from '../utils/clipboard';
import {parseSmbCommand} from '../utils/smbCommander';
import type {SmbReport,SmbEntry,SmbSession,SmbPage,SmbFileAction,SmbExplorerLocation} from '../types/smb';

type Lane='list'|'preview'|'rights'|'download';
type Result=NonNullable<SmbFileAction['result']>;
const codeText=(code:string)=>({access_denied:t('Доступ запрещён'),authentication_failed:t('Учётка отклонена'),account_locked:t('Учётка заблокирована'),account_disabled:t('Учётка отключена'),session_expired:t('Сессия истекла. Подключитесь снова.'),file_too_large:t('Файл больше 20 МБ'),action_timeout:t('Сервер не ответил за 60 секунд'),reparse_blocked:t('Ссылки и junction не открываются'),path_not_found:t('Файл или папка больше не существуют'),file_changed:t('Файл изменился во время скачивания. Повторите запрос.')} as Record<string,string>)[code]||t('Не удалось выполнить действие с файлом');
function errorText(e:unknown){const detail=axios.isAxiosError(e)?e.response?.data?.detail:null;return typeof detail==='string'?uiText(detail):t('Не удалось выполнить действие с файлом');}

export default function SmbExplorer({scanId,report,share,session,onSession,onClose,initialEntry,onConnect,onCollect,initialLocation,onLocationChange}:{initialLocation?:SmbExplorerLocation;onLocationChange?:(value:SmbExplorerLocation)=>void;onConnect?:()=>void;onCollect?:()=>void;initialEntry?:SmbEntry;scanId:number;report:SmbReport;share:string;session:SmbSession|null;onSession:(session:SmbSession|null)=>void;onClose:()=>void}) {
  const [path,setPath]=useState(initialEntry?.parent||initialLocation?.path||'');
  const pendingInitial=useRef(initialEntry||initialLocation?.selected||undefined);
  const listScroll=useRef<HTMLDivElement>(null);
  const restoreScroll=useRef<number|null>(initialEntry?0:initialLocation?.scrollTop||0);
  const [offset,setOffset]=useState(initialEntry?0:initialLocation?.offset||0);
  const [page,setPage]=useState<SmbPage|null>(null);
  const [query,setQuery]=useState(initialEntry?'':initialLocation?.query||'');
  const [appliedQuery,setAppliedQuery]=useState(initialEntry?'':initialLocation?.query||'');
  const [selected,setSelected]=useState<SmbEntry|null>(null);
  const [tab,setTab]=useState<'preview'|'rights'>('preview');
  const [document,setDocument]=useState<{path:string;result:Result}|null>(null);
  const [rights,setRights]=useState<Record<string,Result>>({});
  const [loading,setLoading]=useState<Record<Lane,boolean>>({list:false,preview:false,rights:false,download:false});
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [commandOpen,setCommandOpen]=useState(false);
  const [command,setCommand]=useState('');
  const [commandOutput,setCommandOutput]=useState('');
  const mounted=useRef(true);
  const versions=useRef<Record<Lane,number>>({list:0,preview:0,rights:0,download:0});
  const tokenRef=useRef(session?.token);tokenRef.current=session?.token;
  const selectionRef=useRef(selected?.path);selectionRef.current=selected?.path;
  const section=useRef<HTMLElement>(null);
  const search=useRef<HTMLInputElement>(null);
  const saveLocation=()=>onLocationChange?.({path,offset,query:appliedQuery,selected,scrollTop:listScroll.current?.scrollTop||0});
  useEffect(()=>{saveLocation();},[path,offset,appliedQuery,selected?.path]);
  useEffect(()=>{
    if(!page||restoreScroll.current===null)return;
    if(listScroll.current)listScroll.current.scrollTop=restoreScroll.current;
    restoreScroll.current=null;
  },[page]);
  const previews=useRef(new Map<string,Result>());
  const previewFlight=useRef<{path:string;token:string;id:number}|null>(null);
  const previewSerial=useRef(0);
  const directories=useRef(new Map<string,{page:SmbPage;time:number}>());
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;for(const lane of Object.keys(versions.current) as Lane[])versions.current[lane]++;};},[]);
  const laneBusy=(lane:Lane,value:boolean)=>{if(mounted.current)setLoading(previous=>({...previous,[lane]:value}));};
  const request=async(lane:Lane,action:string,entryPath:string,directory=false,filter='',start=0):Promise<SmbFileAction|null>=>{
    const token=session?.token;
    if(!token){setError(t('Введите данные входа один раз в строке подключения.'));return null;}
    const version=++versions.current[lane];
    const valid=()=>mounted.current&&versions.current[lane]===version&&tokenRef.current===token;
    laneBusy(lane,true);setError('');
    try{
      let job=await startSmbFileAction(scanId,report.id,token,{action,share,path:entryPath,directory,query:filter,offset:start});
      const deadline=Date.now()+70000;
      while(job.status==='queued'||job.status==='running'){
        if(!valid())return null;
        if(Date.now()>deadline)throw Error('timeout');
        await new Promise(resolve=>setTimeout(resolve,300));
        if(!valid())return null;
        job=await getSmbFileAction(scanId,report.id,token,job.id);
      }
      if(!valid())return null;
      if(job.status==='failed'){
        if(['session_expired','authentication_failed','account_locked','account_disabled'].includes(job.error||''))onSession(null);
        setError(codeText(job.error||''));return null;
      }
      return job;
    }catch(e){if(valid()){setError(errorText(e));if(axios.isAxiosError(e)&&e.response?.status===401)onSession(null);}return null;}
    finally{if(valid())laneBusy(lane,false);}
  };
  const resetSelection=()=>{
    versions.current.preview++;versions.current.rights++;
    selectionRef.current=undefined;previewFlight.current=null;
    setSelected(null);setDocument(null);setTab('preview');laneBusy('preview',false);laneBusy('rights',false);
  };
  const listing=async(folder:string,start=0,filter='',force=false)=>{
    resetSelection();setError('');
    const key=`${folder}\0${filter}\0${start}`;
    const cached=directories.current.get(key);
    if(!force&&cached&&Date.now()-cached.time<30000){setPage(cached.page);return;}
    setPage(null);
    let data:SmbPage|null=null;
    if(session){const job=await request('list','list',folder,true,filter,start);if(job?.result)data={items:job.result.items||[],total:job.result.total||0,offset:start,limit:100,partial:job.result.partial};}
    else{
      const version=++versions.current.list;laneBusy('list',true);
      try{const result=await browseSmbReport(scanId,report.id,{share,parent:folder,query:filter,offset:start});if(mounted.current&&versions.current.list===version)data=result;}
      catch(e){if(mounted.current&&versions.current.list===version)setError(errorText(e));}
      finally{if(mounted.current&&versions.current.list===version)laneBusy('list',false);}
    }
    if(!data||!mounted.current)return;
    directories.current.set(key,{page:data,time:Date.now()});
    if(directories.current.size>20)directories.current.delete(directories.current.keys().next().value!);
    setPage(data);
    const initial=pendingInitial.current;
    if(initial&&initial.parent===folder&&filter===appliedQuery&&start===offset){pendingInitial.current=undefined;choose(initial);}
  };
  const previousToken=useRef(session?.token);
  useEffect(()=>{
    if(selected)pendingInitial.current=selected;
    const lost=previousToken.current&&!session;previousToken.current=session?.token;
    for(const lane of Object.keys(versions.current) as Lane[])versions.current[lane]++;
    previews.current.clear();directories.current.clear();setRights({});resetSelection();
    setLoading({list:false,preview:false,rights:false,download:false});
    if(lost)return;
    const timer=setTimeout(()=>listing(path,offset,appliedQuery,true),0);
    return()=>clearTimeout(timer);
  },[report.id,share,session?.token]);
  const navigate=(folder:string)=>{
    if(loading.list)return;
    setPath(folder);setOffset(0);setQuery('');setAppliedQuery('');setCommandOutput('');listing(folder);
    section.current?.focus?.({preventScroll:true});
  };
  const choose=(entry:SmbEntry)=>{
    if(selectionRef.current!==entry.path){previewFlight.current=null;versions.current.preview++;versions.current.rights++;setDocument(null);laneBusy('preview',false);laneBusy('rights',false);}
    selectionRef.current=entry.path;setSelected(entry);setTab('preview');section.current?.focus?.({preventScroll:true});
  };
  const preview=async(entry:SmbEntry,force=false)=>{
    if(entry.kind==='directory'||entry.metadata.reparse_point)return;
    if(!session){setError(t('Введите данные входа один раз в строке подключения.'));return;}
    const cached=previews.current.get(entry.path);
    if(cached&&!force){setDocument({path:entry.path,result:cached});return;}
    if(!force&&previewFlight.current?.path===entry.path&&previewFlight.current.token===session.token)return;
    const flight=++previewSerial.current;
    previewFlight.current={path:entry.path,token:session.token,id:flight};
    try {
      const job=await request('preview','preview',entry.path);
      if(job?.result&&selectionRef.current===entry.path){
        previews.current.set(entry.path,job.result);
        if(previews.current.size>20)previews.current.delete(previews.current.keys().next().value!);
        setDocument({path:entry.path,result:job.result});
      }
    }finally{if(previewFlight.current?.id===flight)previewFlight.current=null;}
  };
  useEffect(()=>{
    if(!selected||selected.kind==='directory'||!session)return;
    const cached=previews.current.get(selected.path);
    if(cached){setDocument({path:selected.path,result:cached});return;}
    const timer=setTimeout(()=>preview(selected),180);
    return()=>clearTimeout(timer);
  },[selected?.path,session?.token]);
  const download=async(entry:SmbEntry)=>{
    if(entry.kind==='directory'||entry.metadata.reparse_point||loading.download)return;
    const job=await request('download','download',entry.path);
    if(!job?.result||!session)return;
    const token=session.token;laneBusy('download',true);
    try{
      const blob=await downloadSmbFile(scanId,report.id,token,job.id);
      if(!mounted.current||tokenRef.current!==token)return;
      const url=URL.createObjectURL(blob);const link=window.document.createElement('a');link.href=url;link.download=job.result.filename||entry.name;window.document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);setNotice(t('Файл передан браузеру для скачивания'));
    }catch(e){if(mounted.current)setError(errorText(e));}finally{laneBusy('download',false);}
  };
  const inspectRights=async(entry:SmbEntry)=>{
    if(entry.metadata.reparse_point)return;
    setTab('rights');
    if(rights[entry.path])return;
    const job=await request('rights','permissions',entry.path,entry.kind==='directory');
    if(job?.result)setRights(previous=>({...previous,[entry.path]:job.result!}));
  };
  const open=(entry:SmbEntry)=>{if(entry.metadata.reparse_point)return;if(entry.kind==='directory')navigate(entry.path);else{choose(entry);preview(entry);}};
  const refresh=()=>{previews.current.clear();directories.current.clear();listing(path,offset,appliedQuery,true);};
  const parent=path.split('/').slice(0,-1).join('/');
  const permissionLabel=(name:string)=>({READ:t('Чтение'),WRITE:t('Запись'),APPEND:t('Добавление'),DELETE:t('Удаление'),READ_ACL:t('Просмотр ACL'),CHANGE_ACL:t('Изменение ACL'),CHANGE_OWNER:t('Смена владельца')} as Record<string,string>)[name]||name;
  const currentPreview=selected&&document?.path===selected.path?document.result.preview:null;
  const currentRights=selected?rights[selected.path]:null;
  const keyboard=(event:React.KeyboardEvent<HTMLElement>)=>{
    const target=event.target as HTMLElement;
    if(['INPUT','TEXTAREA','SELECT','BUTTON','A'].includes(target.tagName)||target.isContentEditable)return;
    const rows=page?.items||[];const index=rows.findIndex(row=>row.path===selected?.path);
    if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&rows.length){
      event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(event.key==='ArrowDown'?1:-1)));choose(rows[next]);section.current?.querySelector(`[data-entry-index="${next}"]`)?.scrollIntoView?.({block:'nearest'});
    }else if(event.key==='Enter'&&selected){event.preventDefault();open(selected);}
    else if(event.key==='Backspace'){event.preventDefault();if(path)navigate(parent);}
    else if(event.key==='F3'&&selected){event.preventDefault();setTab('preview');preview(selected,true);}
    else if(event.key==='F5'){event.preventDefault();refresh();}
    else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'&&selected){event.preventDefault();download(selected);}
    else if(event.key==='/'){event.preventDefault();search.current?.focus?.();}
    else if(event.key==='Escape'){event.preventDefault();onClose();}
  };
  const executeCommand=async()=>{
    const value=command;setCommand('');
    try{
      const parsed=parseSmbCommand(value,path,selected?.path);
      if(parsed.action==='help'){setCommandOutput('ls · cd "folder" · cd .. · cat "file.txt" · get "file.txt" · rights "file" · pwd');return;}
      if(parsed.action==='pwd'){setCommandOutput(`\\\\${report.host}\\${share}\\${path.replace(/\//g,'\\')}`);return;}
      if(parsed.action==='list'){navigate(parsed.path||'');return;}
      const target=page?.items.find(entry=>entry.path===parsed.path)||{share,path:parsed.path!,parent:parsed.path!.split('/').slice(0,-1).join('/'),name:parsed.path!.split('/').slice(-1)[0],kind:'file' as const,metadata:{}};
      choose(target);selectionRef.current=target.path;
      if(parsed.action==='preview'){setTab('preview');await preview(target);}
      else if(parsed.action==='download')await download(target);
      else await inspectRights(target);
      setCommandOutput('');
    }catch{setCommandOutput(t('Не удалось разобрать команду. Введите help.'));}
  };

  return <section ref={section} className={`smb-commander${selected?' has-file':''}`} tabIndex={0} onKeyDown={keyboard} aria-label={t('SMB файловый менеджер')}>
    <header className="smb-commander-header"><button className="report-choice" onClick={onClose} aria-label={t('Закрыть просмотр')}>×</button><strong>{report.host} / {share}</strong><a className="report-choice" href={`/secrets?scan=${scanId}&report=${report.id}&share=${encodeURIComponent(share)}`}>{t('Найти секреты')}</a><span>{t('Результат учётки: {account}',{account:report.account||t('Без учётки')})}</span>{onCollect&&<button className="report-choice" onClick={onCollect}>{t('Обновить файлы хоста')}</button>}</header>
    {!session&&<div className="smb-connect-notice"><span>{t('Сохранённые результаты доступны. Для чтения файлов подключите учётку сверху.')}</span><button className="report-choice" onClick={onConnect}>{t('Подключиться')}</button></div>}
    {error&&<p role="alert" className="smb-commander-error">{error}</p>}
    <div className="smb-commander-toolbar"><button className="report-choice" disabled={!path||loading.list} onClick={()=>navigate(parent)}><ArrowLeft size={14}/>{t('Вверх')}</button><nav aria-label={t('Путь SMB')}><button onClick={()=>navigate('')}>{share}</button>{path.split('/').filter(Boolean).map((name,index,parts)=><span key={index}> / <button onClick={()=>navigate(parts.slice(0,index+1).join('/'))}>{name}</button></span>)}</nav><button className="report-choice" disabled={loading.list} aria-label={t('Обновить')} onClick={refresh}><RefreshCw size={14}/></button><form onSubmit={event=>{event.preventDefault();setAppliedQuery(query);setOffset(0);listing(path,0,query);}}><input ref={search} aria-label={t('Поиск в папке SMB')} value={query} placeholder={t('Фильтр этой папки · Enter')} title={t('Фильтр показывает только имена в текущей папке, без обхода вложенных папок.')} maxLength={200} onChange={event=>setQuery(event.target.value)}/><button className="report-choice" disabled={loading.list}>{t('Найти')}</button></form></div>
    <div className="smb-commander-panes">
      <div className="smb-commander-list">
        <div ref={listScroll} onScroll={saveLocation} className="smb-commander-list-scroll" aria-busy={loading.list}>
          {loading.list&&<p role="status" className="smb-commander-state"><Loader2 size={15} className="animate-spin"/>{t('Загрузка папки…')}</p>}
          <table className="smb-commander-table" role="grid" aria-label={t('Файлы и папки SMB')}><thead><tr><th>{t('Имя')}</th><th>{t('Размер')}</th><th>{t('Изменён')}</th></tr></thead><tbody>{page?.items.map((entry,index)=><tr key={entry.path} data-entry-index={index} aria-selected={selected?.path===entry.path} className={selected?.path===entry.path?'selected':''} onClick={()=>choose(entry)} onDoubleClick={()=>open(entry)}><td><button title={entry.name} disabled={entry.metadata.reparse_point} onClick={event=>{event.stopPropagation();open(entry);}}>{entry.kind==='directory'?<Folder size={14}/>:<FileText size={14}/>}<span>{entry.name}</span></button></td><td>{entry.kind==='directory'?t('Папка'):entry.metadata.size||'—'}</td><td>{entry.metadata.mtime_epoch?.replace('T',' ').slice(0,19)||'—'}</td></tr>)}</tbody></table>
          {!loading.list&&page&&!page.items.length&&<p className="smb-commander-state">{session?t('В папке нет файлов или совпадений'):t('Сохранённых файлов нет. Войдите для просмотра папки.')}</p>}
        </div>
        <footer><span>{t('Записей: {count}',{count:page?.total||0})}</span>{page?.partial&&<span>{t('Список неполный')}</span>}<button className="report-choice" aria-label={t('Предыдущая страница SMB')} disabled={!page||offset===0||loading.list} onClick={()=>{setOffset(Math.max(0,offset-100));listing(path,Math.max(0,offset-100),appliedQuery);}}><ArrowLeft size={13}/></button><span>{Math.floor(offset/100)+1}</span><button className="report-choice" aria-label={t('Следующая страница SMB')} disabled={!page||offset+100>=page.total||loading.list} onClick={()=>{setOffset(offset+100);listing(path,offset+100,appliedQuery);}}><ArrowRight size={13}/></button></footer>
      </div>
      <aside className="smb-commander-inspector" aria-label={t('Предпросмотр выбранного файла')}>
        {!selected?<div className="smb-commander-placeholder"><Eye size={26}/><strong>{t('Выберите файл слева')}</strong><p>{t('Один щелчок — предпросмотр. Enter — открыть папку.')}</p></div>:<>
          <div className="smb-commander-file-heading"><strong title={selected.name}>{selected.name}</strong><small>{selected.metadata.size||t('Папка')}</small></div>
          <div className="smb-commander-file-tools">{selected.kind==='file'?<button className="report-button report-button-primary" disabled={loading.download||!session||selected.metadata.reparse_point} onClick={()=>download(selected)}><Download size={14}/>{loading.download?t('Скачивание…'):t('Скачать')}</button>:<button className="report-choice" disabled={loading.list||selected.metadata.reparse_point} onClick={()=>navigate(selected.path)}><Folder size={14}/>{t('Открыть папку')}</button>}<button className={`report-choice ${tab==='preview'?'active':''}`} onClick={()=>setTab('preview')}><Eye size={14}/>{t('Просмотр')}</button><button className={`report-choice ${tab==='rights'?'active':''}`} disabled={loading.rights||!session||selected.metadata.reparse_point} onClick={()=>inspectRights(selected)}><Shield size={14}/>{t('Права')}</button><button className="report-choice" aria-label={t('Копировать UNC-путь')} onClick={async()=>{try{await copyText(`\\\\${report.host}\\${share}\\${selected.path.replace(/\//g,'\\')}`);setNotice(t('Путь скопирован'));}catch{setNotice(t('Не удалось скопировать путь'));}}}><Copy size={13}/></button></div>
          <div className="smb-commander-preview">
            {tab==='rights'?(loading.rights?<p role="status">{t('Проверка прав…')}</p>:currentRights?<><p className="smb-hint">{t('Эффективные права текущей учётки. Проверены открытием объекта без изменения файла или ACL.')}</p><dl className="smb-rights">{currentRights.rights?.map(right=><div key={right.right}><dt>{permissionLabel(right.right)}</dt><dd>{right.status==='allowed'?t('Разрешено'):right.status==='denied'?t('Запрещено'):t('Неизвестно')}</dd></div>)}</dl><small>{currentRights.checked_at&&formatDateTime(currentRights.checked_at)}</small></>:<p>{t('Нажмите «Права», чтобы проверить доступ.')}</p>):selected.kind==='directory'?<div className="smb-commander-placeholder"><Folder size={26}/><p>{t('Enter или двойной щелчок — открыть папку')}</p></div>:loading.preview?<p role="status"><Loader2 size={15} className="animate-spin inline"/> {t('Загрузка предпросмотра…')}</p>:currentPreview?.supported?<><pre>{currentPreview.text}</pre>{currentPreview.truncated&&<p>{t('Показана только начальная часть документа')}</p>}</>:currentPreview?<p>{t('Для этого формата предпросмотр недоступен. Файл можно скачать.')}</p>:<p>{session?t('Выберите файл для предпросмотра'):t('Войдите, чтобы просмотреть или скачать файл.')}</p>}
          </div>
        </>}
      </aside>
    </div>
    <footer className="smb-commander-shortcuts"><span>↑↓ {t('выбор')} · Enter {t('открыть')} · Backspace {t('вверх')} · F3 {t('просмотр')} · F5 {t('обновить')} · Ctrl+S {t('скачать')}</span><button className="report-choice" aria-expanded={commandOpen} onClick={()=>setCommandOpen(value=>!value)}><Terminal size={13}/>{t('Командная строка')}</button></footer>
    {commandOpen&&<div className="smb-commander-console"><form onSubmit={event=>{event.preventDefault();executeCommand();}}><label htmlFor="smb-command">smb&gt;</label><input id="smb-command" aria-label={t('Команда SMB')} value={command} placeholder='help · ls · cd "folder" · cat "file" · get "file"' onChange={event=>setCommand(event.target.value)} autoComplete="off" spellCheck={false}/><button className="report-choice">Enter</button></form>{commandOutput&&<pre role="status">{commandOutput}</pre>}</div>}
    {notice&&<p role="status" className="smb-commander-notice">{notice}</p>}
  </section>;
}
