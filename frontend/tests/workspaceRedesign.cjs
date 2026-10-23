// Run: node frontend/tests/workspaceRedesign.cjs
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),babel=require('@babel/core');
const base=path.join(__dirname,'../src');
const React={createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(v=>v!==null&&v!==undefined&&v!==false)};}};
const elements=n=>n&&typeof n==='object'?[n,...n.children.flatMap(elements)]:[];
const text=n=>n&&typeof n==='object'?n.children.map(text).join(''):String(n??'');
const get=(tree,p)=>{const found=elements(tree).find(p);assert(found,'element not found');return found;};
function createHarness(filename,dependencies,globals={}){
 let slots=[],cursor=0,pending=[];
 const hooks={
 useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},
 useRef(initial){const i=cursor++;if(!(i in slots))slots[i]={current:initial};return slots[i];},
 useEffect(callback,deps){const i=cursor++;const prev=slots[i];if(!prev||deps.some((d,j)=>!Object.is(d,prev.deps[j])))pending.push(()=>{prev?.cleanup?.();slots[i]={deps,cleanup:callback()};});}
 };
 const code=babel.transformSync(fs.readFileSync(path.join(base,filename),'utf8'),{filename,presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-react-jsx','@babel/plugin-transform-modules-commonjs']}).code;
 const ctx={exports:{},React,console,...globals,require(name){if(name.includes('i18n/core'))return require('./helpers/i18n.cjs');if(name==='react')return hooks;if(name==='lucide-react')return new Proxy({},{get:(_,key)=>String(key)});if(name==='react-router-dom')return {Link:'Link'};return dependencies(name);}};
 vm.runInNewContext(code,ctx);
 return {render(props){cursor=0;return ctx.exports.default(props);},effects(){const jobs=pending;pending=[];jobs.forEach(fn=>fn());}};
}
const report=(id,source='10.0.0.1')=>({id,target:'10.20.0.0/24',project_id:7,network_part_id:8,project:'Lab',network:'Office',source_host:source,scan_type:'quick',status:'completed',created_at:'2026-10-16T10:00:00Z',total_hosts:4,total_ports:8,total_web:2,total_screenshots:1});
let context={selection:{projectId:7,partId:8},project:{name:'Lab'},part:{name:'Office'},loading:false,setLocked(){}};
const listCalls=[],compareCalls=[],uploadBodies=[];let closed=0,allProjects=false,showUpload=false;
const mockApi={listScans:async(skip,limit,scope)=>{listCalls.push({skip,scope});return skip===0?{total:2,scans:[report(1,'pivot-one')]}:{total:2,scans:[report(2,'pivot-two')]};}};
const axios={get:async(url,options)=>{compareCalls.push(options.params);return {data:{added_hosts:[],removed_hosts:[],changed_hosts:[],unchanged_hosts:4}};},post:async(url,body)=>{uploadBodies.push(body);return {data:report(3)};},isAxiosError:()=>false};
class FakeFormData {constructor(){this.values={};}append(k,v){this.values[k]=v;}}
const reports=createHarness('components/ReportTools.tsx',name=>{
 if(name.includes('ProjectContext'))return {useProject:()=>context};if(name==='axios')return {__esModule:true,default:axios};if(name.includes('api/client'))return mockApi;if(name.includes('ImportNotice'))return {__esModule:true,default:'ImportNotice'};throw Error(name);
},{FormData:FakeFormData});
const props=()=>({allProjects,showUpload,onCloseUpload(){closed++;showUpload=false;}});
const tick=async()=>{await new Promise(resolve=>setImmediate(resolve));};
(async()=>{
 let tree=reports.render(props());const dialog={open:false,showModal(){this.open=true;},close(){this.open=false;}};
 get(tree,n=>n.type==='dialog').props.ref.current=dialog;reports.effects();await tick();tree=reports.render(props());reports.effects();
 assert.equal(listCalls.length,2,'load all pages');assert.equal(listCalls[0].scope.project_id,7);assert.equal(listCalls[0].scope.network_part_id,8);
 get(tree,n=>n.props['aria-label']==='Поиск отчётов').props.onChange({target:{value:'pivot-two'}});tree=reports.render(props());assert(!elements(tree).some(n=>n.props.to==='/scan/1'));assert(elements(tree).some(n=>n.props.to==='/scan/2'),'search includes source');
 get(tree,n=>n.props['aria-label']==='Поиск отчётов').props.onChange({target:{value:''}});tree=reports.render(props());
 get(tree,n=>n.props['aria-label']==='Первый отчёт').props.onChange({target:{value:'1'}});tree=reports.render(props());get(tree,n=>n.props['aria-label']==='Второй отчёт').props.onChange({target:{value:'2'}});tree=reports.render(props());
 assert(get(tree,n=>n.props['aria-label']==='Первый отчёт').children.some(n=>n.type==='option'&&n.props.value===2&&n.props.disabled),'same report disabled on other side');
 await get(tree,n=>n.type==='button'&&text(n)==='Показать различия').props.onClick();tree=reports.render(props());assert.equal(compareCalls[0].before,'1');assert.equal(compareCalls[0].after,'2');assert.match(text(tree),/Различий не найдено/);
 allProjects=true;tree=reports.render(props());reports.effects();await tick();tree=reports.render(props());reports.effects();assert.equal(listCalls.at(-1).scope.project_id,null);assert.equal(get(tree,n=>n.props['aria-label']==='Первый отчёт').props.value,'','scope change clears comparison');
 showUpload=true;tree=reports.render(props());reports.effects();assert(dialog.open,'upload opens native dialog');
 get(tree,n=>n.props['aria-label']==='Файл отчёта').props.onChange({target:{files:[{name:'scan.xml',size:100}]}});tree=reports.render(props());await get(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});tree=reports.render(props());reports.effects();
 assert.equal(closed,1);assert.equal(dialog.open,false);const metadata=JSON.parse(uploadBodies[0].values.metadata);assert.equal(metadata.project_id,7,'all-projects view does not change import destination');assert.equal(metadata.network_part_id,8);assert(elements(tree).some(n=>n.props.to==='/scan/3'),'import immediately joins list');
 context={...context,selection:{projectId:9,partId:10}};allProjects=false;tree=reports.render(props());reports.effects();await tick();tree=reports.render(props());assert.equal(listCalls.at(-1).scope.project_id,9);assert.equal(listCalls.at(-1).scope.network_part_id,10);
 console.log('PASS: report pagination, project filters, source search, distinct comparison selection, result rendering, scope reset, upload dialog and import destination');
 // Scan form: keep source, custom ports, speed and exclusions in the launch payload.
 let created=0,launch;
 const form=createHarness('components/ScanForm.tsx',name=>{
  if(name.includes('ProjectContext'))return {useProject:()=>context};if(name.includes('utils/format'))return {speedLabel:v=>({normal:'Обычная',fast:'Быстрая',hard:'Интенсивная'}[v])};
  if(name.includes('api/client'))return {createScan:async(...args)=>{launch=args;},getPortProfiles:async()=>({}),getSpeedProfiles:async()=>({}),listScans:async()=>({scans:[]})};throw Error(name);
 });
 let scan=form.render({onCreated(){created++;}});
 get(scan,n=>n.props.id==='new-scan-source').props.onChange({target:{value:' 10.0.0.10 '}});get(scan,n=>n.props['aria-label']==='Цель сканирования').props.onChange({target:{value:'10.30.0.0/24'}});get(scan,n=>n.props['aria-label']==='Профиль портов').props.onChange({target:{value:'custom'}});scan=form.render({onCreated(){created++;}});
 get(scan,n=>n.props['aria-label']==='Свои TCP-порты').props.onChange({target:{value:'22,443'}});get(scan,n=>n.type==='button'&&text(n)==='Интенсивная').props.onClick();get(scan,n=>n.props['aria-label']==='Исключённые порты').props.onChange({target:{value:'9100'}});scan=form.render({onCreated(){created++;}});await scan.props.onSubmit({preventDefault(){}});
 assert.equal(launch[0],'10.30.0.0/24');assert.equal(launch[2],'22,443');assert.equal(launch[4],'hard');assert.equal(launch[5].exclude_ports,'9100');assert.equal(launch[6].source_host,'10.0.0.10');assert.equal(launch[6].project_id,9);assert.equal(created,1);
 scan=form.render({onCreated(){}});assert.equal(get(scan,n=>n.props.id==='new-scan-source').props.value,' 10.0.0.10 ');assert(!elements(scan).some(n=>n.type==='textarea'&&n.props.maxLength===1000));
 console.log('PASS: compact scan source, custom ports, selected speed, exclusions, project destination and source retention');
})().catch(error=>{console.error(error);process.exitCode=1;});
