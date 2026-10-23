import english from './en.json';
import apiEnglish from './api.en.json';
export type Language = 'ru' | 'en';
const translations: Record<string,string> = english;
const listeners = new Set<() => void>();
const stored = ():Language => {try{return localStorage.getItem('webscanner-language')==='en'?'en':'ru';}catch{return 'ru';}};
let language:Language=stored();
export const getLanguage=():Language=>language;
export const subscribeLanguage=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener);};};
export function setLanguage(next:Language){
  if(next!=='ru'&&next!=='en')return;
  language=next;
  try{localStorage.setItem('webscanner-language',next);}catch{}
  if(typeof document!=='undefined')document.documentElement.lang=next==='en'?'en-GB':'ru';
  listeners.forEach(listener=>listener());
}
if(typeof document!=='undefined')document.documentElement.lang=language==='en'?'en-GB':'ru';
if(typeof window!=='undefined')window.addEventListener('storage',event=>{if(event.key==='webscanner-language')setLanguage(stored());});
/** Russian source messages are readable, stable keys; parameters are never translated. */
export function t(message:string,values:Record<string,unknown>={}):string{
  const template=language==='en'?(translations[message]??message):message;
  return template.replace(/\{(v\d+|\w+)\}/g,(match,key)=>Object.prototype.hasOwnProperty.call(values,key)?String(values[key]??''):match);
}
export const locale=()=>language==='en'?'en-GB':'ru-RU';
/** h23 is deliberate: 00:00–23:59 in every language and browser locale. */
export function formatDateTime(value:string|number|Date):string{
  const date=value instanceof Date?value:new Date(value);if(Number.isNaN(date.getTime()))return '—';
  return new Intl.DateTimeFormat(locale(),{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date);
}
export function formatDate(value:string|number|Date):string{
  const date=value instanceof Date?value:new Date(value);if(Number.isNaN(date.getTime()))return '—';
  return new Intl.DateTimeFormat(locale(),{day:'2-digit',month:'2-digit',year:'numeric'}).format(date);
}
export function formatNumber(value:number,options:Intl.NumberFormatOptions={}):string{return new Intl.NumberFormat(locale(),options).format(value);}

type CountKind='host'|'port'|'report'|'screenshot'|'device';
const countWords:Record<CountKind,[string,string,string,string,string]>={
  host:['хост','хоста','хостов','host','hosts'],
  port:['порт','порта','портов','port','ports'],
  report:['отчёт','отчёта','отчётов','report','reports'],
  screenshot:['скриншот','скриншота','скриншотов','screenshot','screenshots'],
  device:['устройство','устройства','устройств','device','devices'],
};
export function itemCount(count:number,kind:CountKind):string{
  const words=countWords[kind];
  if(language==='en')return `${formatNumber(count)} ${words[count===1?3:4]}`;
  const last=count%10,lastTwo=count%100;
  const index=last===1&&lastTwo!==11?0:last>=2&&last<=4&&(lastTwo<12||lastTwo>14)?1:2;
  return `${formatNumber(count)} ${words[index]}`;
}
export const hostCount=(count:number)=>itemCount(count,'host');

/** Re-localize existing application messages after a language change, without resetting state. */
const messageCatalog:Record<string,string>={...apiEnglish,...translations};
const messagePairs=Object.entries(messageCatalog);
const messagePatterns=messagePairs.flatMap(([ru,en])=>{
  if(!ru.includes('{v')||ru.replace(/\{v\d+\}/g,'').length<10)return [];
  return [[ru,en],[en,ru]].map(([source,target])=>{
    const names:string[]=[];
    const pattern=source.split(/(\{v\d+\})/g).map(part=>{
      if(/^\{v\d+\}$/.test(part)){names.push(part.slice(1,-1));return '([\\s\\S]*?)';}
      return part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    }).join('');
    return {source,target,names,regex:new RegExp('^'+pattern+'$')};
  });
});
export function uiText(message:string):string{
  if(language==='en'&&messageCatalog[message])return messageCatalog[message];
  if(language==='ru'){const pair=messagePairs.find(([,en])=>en===message);if(pair)return pair[0];}
  for(const {source,target,names,regex} of messagePatterns){
    if(language==='en'&&!messageCatalog[source]||language==='ru'&&messageCatalog[source])continue;
    const match=message.match(regex);if(match)return target.replace(/\{(v\d+)\}/g,(token,key)=>{const index=names.indexOf(key);return index<0?token:match[index+1];});
  }
  return message;
}
