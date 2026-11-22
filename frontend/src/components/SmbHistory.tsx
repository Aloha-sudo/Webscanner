import {useEffect,useRef,useState} from 'react';
import axios from 'axios';
import {t,uiText,formatDateTime} from '../i18n/core';
import {deleteSmbReports} from '../api/client';
import type {SmbReport} from '../types/smb';

export default function SmbHistory({scanId,reports,onDeleted,expanded=false}:{expanded?:boolean;scanId:number;reports:SmbReport[];onDeleted:(ids:string[])=>void}) {
  const [selected,setSelected]=useState<string[]>([]);
  const [confirming,setConfirming]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{
    setSelected(items=>items.filter(id=>reports.some(report=>report.id===id)));
    setConfirming(false);
  },[reports]);
  const remove=async()=>{
    if(busy||!selected.length)return;
    setBusy(true);setError('');
    try{
      const result=await deleteSmbReports(scanId,selected);
      if(!mounted.current)return;
      onDeleted(result.deleted);setSelected([]);setConfirming(false);
    }catch(e){
      if(mounted.current){const detail=axios.isAxiosError(e)?e.response?.data?.detail:null;setError(typeof detail==='string'?uiText(detail):t('Не удалось удалить SMB-результаты'));}
    }finally{if(mounted.current)setBusy(false);}
  };
  return <details className="smb-history" open={expanded||undefined}><summary>{t('История проверок и другие учётки')} · {reports.length}</summary>
    <div className="smb-history-toolbar">
      <label><input type="checkbox" aria-label={t('Выбрать все SMB-результаты')} checked={!!reports.length&&selected.length===reports.length} disabled={busy||confirming} onChange={event=>{setSelected(event.target.checked?reports.map(report=>report.id):[]);setError('');}}/>{t('Выбрать все')}</label>
      <span>{t('Выбрано: {count}',{count:selected.length})}</span>
      <button type="button" className="report-choice" disabled={busy||!selected.length||confirming} onClick={()=>{setConfirming(true);setError('');}}>{t('Удалить выбранные')}</button>
    </div>
    {confirming&&<div className="smb-delete-confirm" role="group" aria-label={t('Удаление SMB-результатов')}>
      <p>{t('Удалить выбранные SMB-результаты: {count}?',{count:selected.length})}</p>
      <p className="smb-hint">{t('Будут удалены сохранённые отчёты и списки файлов. Основной скан и файлы на компьютерах останутся.')}</p>
      <div className="smb-actions"><button type="button" className="report-choice" disabled={busy} onClick={remove}>{busy?t('Удаление…'):t('Подтвердить удаление')}</button><button type="button" className="report-choice" disabled={busy} onClick={()=>setConfirming(false)}>{t('Отмена')}</button></div>
    </div>}
    {error&&<p role="alert" className="text-red-400">{error}</p>}
    <div className="smb-table-scroll smb-history-results"><table className="smb-table"><thead><tr><th/><th>IP</th><th>{t('Учётка')}</th><th>{t('Время проверки (местное)')}</th><th>{t('Шары')}</th><th>{t('Файлы')}</th><th/></tr></thead><tbody>{reports.map(report=><tr key={report.id}>
      <td><input type="checkbox" aria-label={`${t('Выбрать SMB-результат')}: ${report.host} · ${report.account||t('Без учётки')} · ${formatDateTime(report.observed_at||report.imported_at)}`} checked={selected.includes(report.id)} disabled={busy||confirming} onChange={event=>{setSelected(items=>event.target.checked?[...items,report.id]:items.filter(id=>id!==report.id));setError('');}}/></td>
      <td>{report.host}</td><td>{report.account||t('Без учётки')}</td><td>{formatDateTime(report.observed_at||report.imported_at)}</td><td>{report.shares.length}</td><td>{report.file_count}</td><td><a className="text-accent underline" href={`/api/scans/${scanId}/smb/${report.id}/original`}>JSON</a></td>
    </tr>)}</tbody></table></div>
  </details>;
}
