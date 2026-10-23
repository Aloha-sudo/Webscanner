import { t } from '../i18n/core';
import { createContext, useContext, useEffect, useState } from 'react';
import axios from 'axios';
export type Part={id:number;name:string;report_count:number};
export type Project={id:number;name:string;parts:Part[]};
export type SavedMapView={report_ids:number[];source:number|null;whole_project:boolean;merge_parts:boolean;network_part_id:number|null};
type MapTools={view:SavedMapView|null;restore:(view:SavedMapView)=>void};
type Selection={projectId:number|null;partId:number|null};
type State={mapTools:MapTools|null;setMapTools:(tools:MapTools|null)=>void;projects:Project[];project:Project|undefined;part:Part|undefined;selection:Selection;select:(value:Selection)=>void;refresh:()=>Promise<void>;loading:boolean;error:string;locked:boolean;setLocked:(value:boolean)=>void};
const Context=createContext<State|null>(null);
const initial=():Selection=>{try{const s=JSON.parse(localStorage.getItem('scanner-context')||'null');return {projectId:Number.isInteger(s?.projectId)?s.projectId:null,partId:Number.isInteger(s?.partId)?s.partId:null};}catch{return {projectId:null,partId:null};}};
export function ProjectProvider({children}:{children:React.ReactNode}){
  const [mapTools,setMapTools]=useState<MapTools|null>(null);
  const [locked,setLocked]=useState(false);
  const [projects,setProjects]=useState<Project[]>([]);const [selection,select]=useState<Selection>(initial);const [loading,setLoading]=useState(true);const [error,setError]=useState('');
  const refresh=async()=>{setLoading(true);try{const {data}=await axios.get<Project[]>('/api/catalog',{timeout:15000});setProjects(data);setError('');select(old=>{const p=data.find(p=>p.id===old.projectId);return p?{projectId:p.id,partId:p.parts.some(n=>n.id===old.partId)?old.partId:null}:{projectId:null,partId:null};});}catch{setError(t("Не удалось загрузить каталог проектов. Проверьте сервер."));}finally{setLoading(false);}};
  useEffect(()=>{refresh();const sync=(event:StorageEvent)=>{if(event.key==='scanner-context'){select(initial());refresh();}};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync);},[]);
  useEffect(()=>{try{localStorage.setItem('scanner-context',JSON.stringify(selection));}catch{}},[selection]);
  const project=projects.find(p=>p.id===selection.projectId);const part=project?.parts.find(p=>p.id===selection.partId);
  return <Context.Provider value={{mapTools,setMapTools,projects,project,part,selection,select,refresh,loading,error,locked,setLocked}}>{children}</Context.Provider>;
}
export const useProject=()=>{const value=useContext(Context);if(!value)throw new Error('ProjectProvider missing');return value;};
