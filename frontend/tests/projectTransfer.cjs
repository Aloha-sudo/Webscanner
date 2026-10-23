const assert=require('node:assert/strict');
const {createHarness,get,text,tick}=require('./helpers/componentHarness.cjs');
(async()=>{
let refreshed=0,selected=null,locked=false,fail=false;const calls=[];
const context={project:{id:7,name:'Project'},refresh:async()=>{refreshed++;},select:value=>selected=value,setLocked:value=>locked=value};
const api={isAxiosError:e=>!!e?.response,get:async()=>({data:{description:'Existing notes',map_view:null}}),put:async(url,body)=>{calls.push({url,body});return {data:body};},post:async(url,body)=>{calls.push({url,body:Object.fromEntries(body.entries())});if(fail)throw {response:{data:{detail:'Название уже существует'}}};return {data:body.get('preview')==='true'?{name:'Imported',parts:2,reports:4,files:8,bytes:1024}:{project_id:99}};}};
const ui=createHarness('components/ProjectTransfer.tsx',name=>{if(name==='axios')return {__esModule:true,default:api};if(name.includes('ProjectContext'))return {useProject:()=>context};if(name.includes('WorkspaceDialog'))return {__esModule:true,default:'WorkspaceDialog'};if(name.includes('svgExport'))return {downloadFile(){}};throw Error(name);},{FormData,Blob});
const view={report_ids:[1],source:1,network_part_id:2,whole_project:true,merge_parts:false};
const props={currentView:view,onRestore(){}};
let tree=ui.render(props);ui.effects();await tick();tree=ui.render(props);
assert.equal(get(tree,n=>n.type==='textarea'&&n.props['aria-label']==='Описание проекта').props.value,'Existing notes');
await get(tree,n=>n.type==='button'&&text(n)==='Сохранить').props.onClick();assert.equal(calls[0].body.map_view,view);
get(tree,n=>n.type==='button'&&text(n)==='Импорт проекта').props.onClick();tree=ui.render(props);assert(get(tree,n=>n.type==='WorkspaceDialog'&&n.props.title==='Импорт проекта').props.open);
await get(tree,n=>n.props['aria-label']==='Архив проекта').props.onChange({target:{files:[new Blob(['zip'])]}});tree=ui.render(props);assert.match(text(tree),/отчётов — 4/);assert.equal(locked,false);
fail=true;await get(tree,n=>n.type==='button'&&text(n)==='Создать проект').props.onClick();tree=ui.render(props);assert.match(text(tree),/Название уже существует/);assert(get(tree,n=>n.type==='WorkspaceDialog'&&n.props.title==='Импорт проекта').props.open);assert.equal(selected,null);
fail=false;get(tree,n=>n.props['aria-label']==='Название импортируемого проекта').props.onChange({target:{value:'Copy'}});tree=ui.render(props);await get(tree,n=>n.type==='button'&&text(n)==='Создать проект').props.onClick();tree=ui.render(props);assert.equal(selected.projectId,99);assert.equal(refreshed,1);assert(!get(tree,n=>n.type==='WorkspaceDialog'&&n.props.title==='Импорт проекта').props.open);assert.equal(locked,false);
console.log('PASS: project notes and map save, archive preview, collision correction, import and context selection');
})().catch(e=>{console.error(e);process.exit(1);});
