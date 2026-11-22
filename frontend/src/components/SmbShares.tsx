import {useEffect,useState} from 'react';
import {ArrowLeft, ArrowRight, Folder} from 'lucide-react';
import {t, formatNumber} from '../i18n/core';
import type {SmbReport} from '../types/smb';

type Share=SmbReport['shares'][number];
const shareAccess=(report:SmbReport,share:Share|null)=>share?.access||(report.format==='webscanner-smb'&&share?.listing==='listed'?['READ']:[]);
const hasAccess=(report:SmbReport,share:Share|null)=>shareAccess(report,share).some(value=>value==='READ'||value==='WRITE');

export default function SmbShares({reports,onOpen,selected,discoveredHosts=[],onCheckHost}:{discoveredHosts?:string[];onCheckHost?:(host:string)=>void;reports:SmbReport[];onOpen:(report:SmbReport,share:string)=>void;selected?:{reportId:string;share:string}|null}) {
  const [search,setSearch]=useState('');
  const [filter,setFilter]=useState('available');
  const [offset,setOffset]=useState(0);
  const [pageSize,setPageSize]=useState(100);
  useEffect(()=>{setFilter('available');setOffset(0);},[]);
  const [account,setAccount]=useState('*');
  const pending=[...new Set(discoveredHosts)].filter(ip=>ip.includes(search)&&!reports.some(report=>report.host===ip&&(account==='*'||(report.account||'')===account)));
  useEffect(()=>{setAccount(value=>value==='*'||reports.some(report=>(report.account||'')===value)?value:'*');setOffset(0);},[reports]);
  const accounts=[...new Set(reports.map(report=>report.account||''))];
  const seen=new Set<string>();
  const latest=reports.filter(r=>{const key=`${r.host}\0${r.account||''}\0${r.auth_method||''}`;if(seen.has(key))return false;seen.add(key);return true;});
  const rows=latest.flatMap<{report:SmbReport;share:SmbReport['shares'][number]|null}>(report=>report.shares.length?report.shares.map(share=>({report,share})):[{report,share:null}]);
  const matching=rows.filter(({report:r,share:s})=>{
    const needle=`${r.host} ${r.server?.name||''} ${r.account||''} ${s?.name||''} ${s?.remark||''}`.toLowerCase();
    const access=shareAccess(r,s);
    const available=!!s&&(s.type===undefined||s.type===0)&&access.some(a=>a.startsWith('READ')||a.startsWith('WRITE'));
    return (account==='*'||(r.account||'')===account)&&needle.includes(search.toLowerCase())&&(filter==='available'&&available||filter==='all'||filter==='guest'&&r.server?.guest===true||access.some(a=>a.startsWith(filter)));
  });
  const totalRows=matching.length+pending.length;
  const pendingOnPage=pageSize===0?Math.max(0,pending.length-offset):Math.min(pageSize,Math.max(0,pending.length-offset));
  const matchOffset=Math.max(0,offset-pending.length);
  return <section className="report-panel smb-share-overview">
    <div className="smb-heading p-4"><div><h2>{t('Хосты и шары')}</h2><p>{t('Все компьютеры и учётки в одной таблице. Нажмите «Открыть» напротив нужной шары.')}</p></div><span>{t('Показано: {count}',{count:formatNumber(matching.length+pending.length)})}</span></div>
    <div className="smb-search"><input aria-label={t('Поиск по всем шарам')} value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}} placeholder={t('IP, компьютер, учётка или название шары')}/><select aria-label={t('Доступ к шарам')} value={filter} onChange={e=>{setFilter(e.target.value);setOffset(0);}}><option value="available">{t('Доступные файловые шары')}</option><option value="all">{t('Все, включая недоступные')}</option><option value="READ">{t('Есть READ')}</option><option value="WRITE">{t('Есть WRITE')}</option><option value="guest">{t('Гостевой вход')}</option></select></div>
    {!!accounts.length&&<label className="smb-account-filter">{t('Результаты проверки')}<select aria-label={t('Результаты проверки')} value={account} onChange={event=>{setAccount(event.target.value);setOffset(0);}}><option value="*">{t('Все учётки')}</option>{accounts.map(value=><option key={value} value={value}>{value||t('Без учётки')}</option>)}</select></label>}
    <div className="smb-table-scroll"><table className="smb-table"><thead><tr><th>IP</th><th>{t('Компьютер')}</th><th>{t('Учётка')}</th><th>{t('Шара')}</th><th>{t('Права')}</th><th>{t('Описание')}</th><th/></tr></thead><tbody>{pending.slice(offset,pageSize===0?undefined:offset+pageSize).map(ip=><tr key={`pending:${ip}`}><td><button onClick={()=>onCheckHost?.(ip)}>{ip}</button></td><td>—</td><td>—</td><td><button className="report-choice" onClick={()=>onCheckHost?.(ip)}>{t('Не проверено')}</button></td><td>—</td><td>—</td><td><button className="report-choice" onClick={()=>onCheckHost?.(ip)}>{t('Проверить')}</button></td></tr>)}{matching.slice(matchOffset,pageSize===0?undefined:matchOffset+pageSize-pendingOnPage).map(({report:r,share:s})=><tr key={`${r.id}/${s?.name||''}`} className={`${hasAccess(r,s)?'smb-share-accessible':'smb-share-unavailable'}${selected?.reportId===r.id&&selected.share===s?.name?' smb-share-selected':''}`}><td>{s?<button className="smb-host-open" onClick={()=>onOpen(r,s.name)}>{r.host}</button>:r.host}</td><td>{r.server?.name||'—'}</td><td>{r.account||t('Без учётки')}{r.server?.guest&&<small> · {t('Гость')}</small>}</td><td>{s?<button onClick={()=>onOpen(r,s.name)}><Folder size={15}/>{s.name}</button>:'—'}{s&&account==='*'&&<small>{r.account||t('Без учётки')}</small>}</td><td>{s?(shareAccess(r,s).length?<span className="smb-access-badges">{shareAccess(r,s).map(value=><span key={value} className={`smb-access-badge${value==='READ'||value==='WRITE'?' granted':''}`} title={value==='READ'?t('Чтение'):value==='WRITE'?t('Запись'):value}>{value}</span>)}</span>:<span className="smb-access-unknown">{s.read_status==='denied'?t('Доступ запрещён'):t('Не проверено')}</span>):<span className="smb-access-unknown">{r.status==='login_failed'?t('Вход не выполнен'):r.status==='shares_failed'?t('Список шар недоступен'):t('Шары не найдены')}</span>}</td><td>{s?.remark||'—'}</td><td>{s&&<button className="report-choice" onClick={()=>onOpen(r,s.name)}>{t('Открыть')}</button>}</td></tr>)}</tbody></table></div>
    {!matching.length&&!pending.length&&<p className="report-empty">{filter==='available'?t('Доступных файловых шар не найдено. Остальные результаты можно показать отдельно.'):t('Совпадений нет')}</p>}
    {filter==='available'&&rows.length>matching.length&&<div className="smb-hidden-shares"><span>{t('Остальные результаты скрыты: {count}',{count:formatNumber(rows.length-matching.length)})}</span><button className="report-choice" onClick={()=>{setFilter('all');setSearch('');setOffset(0);}}>{t('Показать все результаты')}</button></div>}
    <div className="smb-pagination"><span>{t('Строк: {count}',{count:formatNumber(totalRows)})}</span><select className="smb-page-size" aria-label={t('Строк на экране')} value={pageSize} onChange={e=>{setPageSize(Number(e.target.value));setOffset(0);}}><option value={100}>100</option><option value={200}>200</option><option value={500}>500</option>{totalRows<=5000&&<option value={0}>{t('Все')}</option>}</select><button aria-label={t('Предыдущая страница шар')} disabled={pageSize===0||offset===0} onClick={()=>setOffset(Math.max(0,offset-pageSize))}><ArrowLeft size={16}/></button><span>{Math.floor(offset/(pageSize||1))+1}</span><button aria-label={t('Следующая страница шар')} disabled={pageSize===0||offset+pageSize>=totalRows} onClick={()=>setOffset(offset+pageSize)}><ArrowRight size={16}/></button></div>
  </section>;
}
