import axios from 'axios';
import catalog from './api.en.json';
import { getLanguage } from './core';
const messages:Record<string,string>=catalog;
const patterns=Object.entries(messages).filter(([key])=>key.includes('{v')).map(([key,value])=>{
  const names:string[]=[];
  const parts=key.split(/(\{v\d+\})/g).map(part=>{
    if(/^\{v\d+\}$/.test(part)){names.push(part.slice(1,-1));return '([\\s\\S]*?)';}
    return part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  });
  return {regex:new RegExp('^'+parts.join('')+'$'),names,value};
});
/** Only call for application-owned diagnostics, never for user data. */
export function apiText(message:string):string{
  if(getLanguage()!=='en')return message;
  if(messages[message])return messages[message];
  if(message.startsWith('Value error, '))return 'Value error, '+apiText(message.slice(13));
  for(const {regex,names,value} of patterns){const match=message.match(regex);if(match)return value.replace(/\{(v\d+)\}/g,(token,key)=>{const i=names.indexOf(key);return i<0?token:match[i+1];});}
  return message;
}
export function localizeDiagnostics(data:unknown):void{
  if(!data||typeof data!=='object')return;
  const row=data as Record<string,unknown>;
  for(const key of ['detail','error_message']){
    if(typeof row[key]==='string')row[key]=apiText(row[key] as string);
  }
  if(Array.isArray(row.detail))for(const item of row.detail){if(item&&typeof item.msg==='string')item.msg=apiText(item.msg);}
  if(Array.isArray(row.warnings))row.warnings=row.warnings.map(value=>typeof value==='string'?apiText(value):value);
  if(row.dns_summary&&typeof row.dns_summary==='object'){
    const summary=row.dns_summary as Record<string,unknown>;if(typeof summary.error==='string')summary.error=apiText(summary.error);
  }
  if(Array.isArray(row.scans))row.scans.forEach(localizeDiagnostics);
  if(row.scan)localizeDiagnostics(row.scan);
}
export function installLocaleInterceptors(client:typeof axios|ReturnType<typeof axios.create>){
  client.interceptors.request.use(config=>{config.headers.set('Accept-Language',getLanguage());return config;});
  client.interceptors.response.use(response=>{localizeDiagnostics(response.data);return response;},error=>{localizeDiagnostics(error.response?.data);return Promise.reject(error);});
}
