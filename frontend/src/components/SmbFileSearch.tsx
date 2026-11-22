import {useEffect,useState} from 'react';
import axios from 'axios';
import {ArrowLeft,ArrowRight,Search,Loader2} from 'lucide-react';
import {t,uiText,formatNumber} from '../i18n/core';
import {searchSmbFiles} from '../api/client';
import type {SmbReport,SmbEntry,SmbSearchPage} from '../types/smb';

export default function SmbFileSearch({scanId,reports,onActive,onOpen,onCollect,collecting=false,collectionAccount,showResults=true}:{showResults?:boolean;collectionAccount?:string;onCollect?:()=>void;collecting?:boolean;scanId:number;reports:SmbReport[];onActive:(active:boolean)=>void;onOpen:(report:SmbReport,entry:SmbEntry)=>void}) {
  const [input,setInput]=useState('');
  const [query,setQuery]=useState('');
  const [offset,setOffset]=useState(0);
  const [revision,setRevision]=useState(0);
  const [result,setResult]=useState<SmbSearchPage|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const latest=new Map<string,SmbReport>();
  for(const report of reports){const key=JSON.stringify([report.host,(report.account||'').toLowerCase(),report.auth_method]);if(!latest.has(key))latest.set(key,report);}
  const hosts=new Set([...latest.values()].map(report=>report.host));
  const covered=new Set([...latest.values()].filter(report=>report.coverage==='files'||report.format==='netexec-spider-plus').map(report=>report.host));
  useEffect(()=>{
    if(!query){setBusy(false);setResult(null);setError('');return;}
    let active=true;setBusy(true);setError('');setResult(null);
    searchSmbFiles(scanId,query,offset).then(value=>{if(active)setResult(value);}).catch(e=>{
      if(active){const detail=axios.isAxiosError(e)?e.response?.data?.detail:null;setError(typeof detail==='string'?uiText(detail):t('Не удалось найти SMB-файлы'));}
    }).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[scanId,query,offset,revision,reports]);
  return <section className="smb-file-search" aria-label={t('Поиск файлов по сети')}>
    <form className="smb-file-search-bar" onSubmit={event=>{event.preventDefault();const value=input.trim();if(!value)return;setOffset(0);setQuery(value);setRevision(v=>v+1);onActive(true);}}>
      <Search size={16}/><input aria-label={t('Поиск файлов по сети')} placeholder={t('Файл или путь: договор, *.kdbx, web.config')} maxLength={200} value={input} onChange={event=>setInput(event.target.value)}/>
      <button className="report-choice" type="submit" disabled={!input.trim()}>{t('Найти')}</button>
      {!!query&&<button className="report-choice" type="button" onClick={()=>{setQuery('');setInput('');setOffset(0);onActive(false);}}>{t('Очистить')}</button>}
      {!!query&&!showResults&&<button className="report-choice" type="button" onClick={()=>onActive(true)}>{t('К результатам')}</button>}
    </form>
    <p className="smb-file-search-coverage">{t('Списки файлов: {covered} из {total} хостов',{covered:result?.covered_hosts??covered.size,total:result?.hosts??hosts.size})} · {t('По сохранённым именам и путям')} {onCollect&&<button type="button" className="report-choice" disabled={collecting} title={collectionAccount?t('Учётка: {account}',{account:collectionAccount}):undefined} onClick={onCollect}>{collecting?t('Запуск…'):t('Собрать список файлов')}</button>}</p>
    <div hidden={!showResults}>
    {busy&&<p role="status"><Loader2 size={14} className="animate-spin inline"/> {t('Поиск…')}</p>}
    {error&&<p role="alert" className="text-red-400">{error}</p>}
    {result&&<>
      {result.partial&&<p className="smb-search-warning" role="status">{t('Результат неполный: обход или поиск ограничен. Отсутствие файла не означает отсутствие доступа.')}</p>}
      <div className="smb-table-scroll smb-file-search-results"><table className="smb-table"><thead><tr><th>IP</th><th>{t('Шара / путь')}</th><th>{t('Размер')}</th><th>{t('Найден под учёткой')}</th></tr></thead><tbody>{result.items.map(hit=>{
        const sources=hit.sources.map(source=>({source,report:reports.find(report=>report.id===source.report_id)})).filter((item):item is {source:typeof hit.sources[number];report:SmbReport}=>!!item.report);
        const open=()=>{if(sources[0])onOpen(sources[0].report,hit.entry);};
        return <tr key={JSON.stringify([hit.host,hit.entry.share,hit.entry.path])}><td><button onClick={open} disabled={!sources.length}>{hit.host}</button></td><td><button className="smb-file-result-path" title={`${hit.entry.share} / ${hit.entry.path}`} onClick={open} disabled={!sources.length}>{hit.entry.share} / {hit.entry.path}</button></td><td>{hit.entry.metadata.size||'—'}</td><td><div className="smb-file-result-accounts">{sources.map(({source,report})=><button className="report-choice" key={source.report_id} onClick={()=>onOpen(report,hit.entry)}>{source.account||t('Без учётки')}</button>)}</div></td></tr>;
      })}</tbody></table></div>
      {!result.items.length&&<p className="smb-hint">{result.covered_hosts===0?t('Списков файлов пока нет. Нажмите «Собрать список файлов» — результаты обновятся после сбора.'):t('Совпадений по имени или пути нет. Содержимое документов этот поиск не проверяет.')}</p>}
      <div className="smb-pagination"><span>{t('Файлов: {count}',{count:`${result.truncated?'≥ ':''}${formatNumber(result.total)}`})}</span><button aria-label={t('Предыдущая страница файлов')} disabled={!offset||busy} onClick={()=>setOffset(Math.max(0,offset-100))}><ArrowLeft size={16}/></button><span>{Math.floor(offset/100)+1}</span><button aria-label={t('Следующая страница файлов')} disabled={offset+100>=result.total||busy} onClick={()=>setOffset(offset+100)}><ArrowRight size={16}/></button></div>
    </>}
    </div>
  </section>;
}
