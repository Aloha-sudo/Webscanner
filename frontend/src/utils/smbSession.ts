import type {SmbReport,SmbSession} from '../types/smb';

// Only a scoped, expiring capability is kept. Passwords, hashes and AES keys never enter storage.
const memory=new Map<number,SmbSession>();
const key=(id:number)=>`webscanner:smb-session:${id}`;
export function clearSmbSession(id:number):void {
  memory.delete(id);
  try {if(typeof window!=='undefined')window.sessionStorage.removeItem(key(id));}catch{}
}
export function saveSmbSession(id:number,value:SmbSession):SmbSession {
  const session:SmbSession={token:value.token,account:value.account,expires_in:value.expires_in,
    expires_at:value.expires_at || Date.now()+value.expires_in*1000,
    hosts:value.hosts?[...value.hosts]:undefined,report_id:value.report_id};
  memory.set(id,session);
  try {if(typeof window!=='undefined')window.sessionStorage.setItem(key(id),JSON.stringify(session));}catch{}
  return session;
}
export function readSmbSession(id:number):SmbSession|null {
  let stored:string|null=null;
  try {if(typeof window!=='undefined')stored=window.sessionStorage.getItem(key(id));}catch{}
  try {
    const value:unknown=stored?JSON.parse(stored):memory.get(id);
    if(value&&typeof value==='object'){
      const session=value as SmbSession;
      if(/^[a-f0-9]{32}$/.test(session.token)&&typeof session.expires_at==='number'&&Number.isFinite(session.expires_at)&&session.expires_at>Date.now()&&session.expires_at<=Date.now()+901000){
        return {token:session.token,account:session.account,expires_in:Math.ceil((session.expires_at-Date.now())/1000),expires_at:session.expires_at,hosts:session.hosts,report_id:session.report_id};
      }
    }
  }catch{}
  clearSmbSession(id);return null;
}
export function sessionApplies(session:SmbSession|null,report:Pick<SmbReport,'id'|'host'>):boolean {
  if(!session||session.expires_at!==undefined&&session.expires_at<=Date.now())return false;
  if(session.report_id)return session.report_id===report.id;
  return !session.hosts||session.hosts.includes(report.host);
}
