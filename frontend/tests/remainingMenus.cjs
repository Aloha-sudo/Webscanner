const assert=require('node:assert/strict');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
const document={addEventListener(){},removeEventListener(){},getElementById(){return {scrollIntoView(){}};}};
const report=(id,source)=>({id,source_host:source,target:'10.0.0.0/24',project_id:7,network_part_id:8,project:'Lab',network:'Office',scan_type:'quick',status:'completed',created_at:'2026-10-16T10:00:00Z',observed_at:null,total_hosts:1,total_ports:1,total_web:0,total_screenshots:0});
let reports=[report(1,'10.0.0.1'),report(2,'10.0.0.2')];
const context={selection:{projectId:7,partId:8},project:{id:7,name:'Lab',parts:[{id:8,name:'Office',report_count:2}]},part:{id:8,name:'Office'},loading:false,setMapTools(tools){context.mapTools=tools;},select(value){this.selection=value;},setLocked(){},refresh:async()=>{}};
const bodyLog=[],visibilityCalls=[];
class FormData {constructor(values={}){this.values={...values};}append(k,v){this.values[k]=v;}get(k){return this.values[k];}}
const mapApi={isAxiosError:()=>false,get:async(url,options)=>{
 if(url==='/api/scans')return {data:{scans:reports,total:reports.length}};
 if(url==='/api/scans/visibility'){visibilityCalls.push(options.params);return {data:{columns:reports,rows:[],warnings:['Observed evidence only']}};}
 throw Error(url);
},post:async(url,body)=>{bodyLog.push(body.values);const item=report(3,JSON.parse(body.values.metadata).source_host);reports=[item,...reports];return {data:item};}};
const map=createHarness('pages/TeamPage.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:mapApi};if(name==='react-router-dom')return {Link:'Link'};
 if(name.includes('localDateTime'))return {validLocalDateTime:()=>true};if(name.includes('ProjectContext'))return {useProject:()=>context};if(name.includes('observedPaths'))return {initialSourceReport:()=>1};
 if(name.includes('ProjectTransfer'))return {__esModule:true,default:'ProjectTransfer'};if(name.includes('WorkspaceDialog'))return {__esModule:true,default:'WorkspaceDialog'};
 return {__esModule:true,default:name};
},{document,FormData,window:{confirm:()=>true}});
(async()=>{
 let tree=map.render();map.effects();await tick();tree=map.render();map.effects();assert.equal(elements(tree).filter(n=>n.type==='input'&&String(n.props['aria-label']).startsWith('Выбрать отчёт')).length,2);
 await get(tree,n=>n.type==='button'&&text(n)==='Построить карту').props.onClick();tree=map.render();map.effects();assert(!elements(tree).some(n=>n.props.className==='team-report-list-scroll'),'list collapses after building');assert.match(text(tree),/Найти путь/);assert.equal(visibilityCalls[0].report_ids,'1,2');assert.equal(visibilityCalls[0].network_part_id,8);
 await context.mapTools.restore({report_ids:[1,2],source:2,whole_project:false,merge_parts:false,network_part_id:8});
 tree=map.render();map.effects();await tick();tree=map.render();map.effects();await tick();tree=map.render();
 assert.equal(get(tree,n=>String(n.type).includes('VisibilityMap')).props.source,'2','restoring in the same context applies the saved source');
 console.log('PASS: saved map restores selection, source and addressing without a context change');

 get(tree,n=>n.type==='button'&&text(n)==='Выбрать отчёты').props.onClick();tree=map.render();assert(elements(tree).some(n=>n.props.className==='team-report-list-scroll'),'resizable list is still available');
 get(tree,n=>n.type==='button'&&text(n)==='Загрузить отчёты').props.onClick();tree=map.render();assert(get(tree,n=>n.type==='WorkspaceDialog').props.open);
 get(tree,n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[{name:'new.xml'}]}});tree=map.render();get(tree,n=>n.props['aria-label']==='Точка сканирования new.xml').props.onChange({target:{value:'10.0.0.3'}});tree=map.render();await get(tree,n=>n.type==='button'&&text(n)==='Загрузить отчёты'&&n.props.className.includes('mt-4')).props.onClick();tree=map.render();map.effects();
 assert.equal(get(tree,n=>n.type==='WorkspaceDialog').props.open,false);assert.match(text(tree),/Выбрано отчётов: 3/,'import keeps the previous selection and adds new report');assert.equal(JSON.parse(bodyLog[0].metadata).project_id,7);assert.equal(JSON.parse(bodyLog[0].metadata).source_host,'10.0.0.3');assert(!text(tree).includes('Удалить проект'),'project deletion removed from map');
 console.log('PASS: map selection, auto-collapse/reopen, scoped build, modal upload, preserved report selection and source');
 // Common menu: safe deletion remains default and active scans block all deletion.
 let active=1,confirmationCount=0,deleted=null;const notices=[];
 const projectContext={...context,projects:[context.project],locked:false,error:'',select:value=>notices.push(value)};
 const projectApi={isAxiosError:()=>false,get:async()=>({data:{active_count:active,report_count:2,networks:['Office']}}),delete:async(url,options)=>{deleted={url,options};return {data:{deleted_reports:0,preserved_reports:2,cleanup_errors:[]}};}};
 const picker=createHarness('components/ProjectPicker.tsx',name=>{
  if(name.includes('ProjectTransfer'))return {__esModule:true,default:'ProjectTransfer'};if(name==='axios')return {__esModule:true,default:projectApi};if(name.includes('localDateTime'))return {validLocalDateTime:()=>true};if(name.includes('ProjectContext'))return {useProject:()=>projectContext};throw Error(name);
 },{document,window:{confirm:()=>{confirmationCount++;return true;}}});
 tree=picker.render();picker.effects();await get(tree,n=>n.type==='button'&&text(n)==='Удалить проект, сохранить сканы').props.onClick();tree=picker.render();assert.equal(deleted,null);assert.equal(confirmationCount,0);assert.match(text(tree),/активных сканов/);
 active=0;await get(tree,n=>n.type==='button'&&text(n)==='Удалить проект, сохранить сканы').props.onClick();tree=picker.render();assert.equal(deleted.options.data.delete_reports,false);assert.equal(deleted.options.data.expected_count,2);assert.equal(notices[0].projectId,null);assert.match(text(tree),/Сохранено сканов: 2/);
 console.log('PASS: common project menu blocks active deletion, keeps reports by default and sends expected count');
 // Detail: results first, optional comment, editable source, and screenshot tab.
 const record={...report(99,'10.0.0.30'),hosts:[{id:1,ip:'10.0.0.31',ports:[]}],screenshots:[{id:1,url:'https://10.0.0.31',minio_path:'image.png'}],total_screenshots:1,comment:null,progress:100};let patchBody,commentBody;
 const detail=createHarness('pages/ScanDetailPage.tsx',name=>{
  if(name==='react-router-dom')return {Link:'Link',useParams:()=>({id:'99'})};
  if(name.includes('localDateTime'))return {validLocalDateTime:()=>true};if(name.includes('ProjectContext'))return {useProject:()=>({projects:[context.project]})};
  if(name.includes('api/client'))return {getScan:async()=>record,updateScanComment:async(id,comment)=>{commentBody=comment;return {...record,comment};}};
  if(name==='axios')return {__esModule:true,default:{patch:async(url,body)=>{patchBody=body;return {data:{...body,project:'Lab',network:'Office'}};}}};
  if(name.includes('utils/format'))return {stageLabel:v=>v,speedLabel:()=> 'Обычная',profileLabel:()=> 'Быстрый',formatDuration:()=> '1 мин'};
  if(name.includes('DnsResults'))return {__esModule:true,default:'DnsResults'};if(name.includes('ScanHosts'))return {__esModule:true,default:'ScanHosts'};if(name.includes('ScreenshotGallery'))return {__esModule:true,default:'ScreenshotGallery'};throw Error(name);
 },{document,FormData});
 tree=detail.render();detail.effects();await tick();tree=detail.render();detail.effects();assert(text(tree).includes('Источник: 10.0.0.30'));assert(elements(tree).some(n=>n.type==='ScanHosts'));assert.equal(get(tree,n=>n.type==='ScanHosts').props.tools.type,'DnsResults','DNS controls belong to the host filter toolbar');assert(!text(tree).includes('Нет комментария'));
 get(tree,n=>n.type==='button'&&text(n).includes('Добавить комментарий')).props.onClick();tree=detail.render();get(tree,n=>n.type==='textarea').props.onChange({target:{value:'Team note'}});tree=detail.render();await get(tree,n=>n.type==='button'&&text(n)==='Сохранить').props.onClick();tree=detail.render();assert.equal(commentBody,'Team note');assert.match(text(tree),/Team note/);
 get(tree,n=>n.type==='button'&&text(n)==='Изменить привязку').props.onClick();tree=detail.render();await get(tree,n=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{project_id:'7',network_part_id:'8',source_host:'10.0.0.40',author:'Alex'}});tree=detail.render();assert.equal(patchBody.source_host,'10.0.0.40');assert.equal(patchBody.project_id,7);assert(!elements(tree).some(n=>n.type==='form'));
 get(tree,n=>n.props.role==='tab'&&text(n).includes('Скриншоты')).props.onClick();tree=detail.render();assert(elements(tree).some(n=>n.type==='ScreenshotGallery'));assert(!elements(tree).some(n=>n.type==='ScanHosts'));
 console.log('PASS: scan project/source visibility, comment editing, source reassignment and screenshot tab');
})().catch(error=>{console.error(error);process.exitCode=1;});
// Native dialog: keep focus/escape behavior native and block closing during an operation.
let closes=0;
const dialogComponent=createHarness('components/WorkspaceDialog.tsx',()=>{throw Error('unexpected import');});
let dialogTree=dialogComponent.render({open:true,title:'Upload',busy:true,onClose(){closes++;},children:'body'});
const nativeDialog={open:false,showModal(){this.open=true;},close(){this.open=false;}};
dialogTree.props.ref.current=nativeDialog;dialogComponent.effects();assert(nativeDialog.open);
let prevented=false;dialogTree.props.onCancel({preventDefault(){prevented=true;}});assert(prevented);assert.equal(closes,0);
dialogTree=dialogComponent.render({open:true,title:'Upload',busy:false,onClose(){closes++;},children:'body'});dialogTree.props.onCancel({preventDefault(){}});assert.equal(closes,1);
dialogTree=dialogComponent.render({open:false,title:'Upload',busy:false,onClose(){},children:'body'});dialogComponent.effects();assert(!nativeDialog.open);
console.log('PASS: native upload dialog open/close and busy escape guard');
