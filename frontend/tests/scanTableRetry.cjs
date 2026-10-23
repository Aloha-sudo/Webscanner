const assert=require('node:assert/strict');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
const scan=(id,status='completed',scan_type='quick')=>({id,status,scan_type,target:'10.0.0.0/24',stage:status,progress:100,created_at:'2026-10-17T10:00:00Z',total_hosts:0,total_ports:0,total_web:0,total_screenshots:0});
let retried;
const table=createHarness('components/ScanTable.tsx',name=>{
 if(name==='react-router-dom')return {Link:'Link'};
 if(name.includes('utils/format'))return {formatDuration:()=>'',profileLabel:()=>'',speedLabel:()=>''};
 throw Error(name);
});
const props={scans:[scan(1),scan(2,'failed'),scan(3,'cancelled'),scan(4,'running'),scan(5,'queued'),scan(6,'completed','import-nmap')],retryingIds:new Set([2]),onDelete(){},onCancel(){},onRetry:id=>retried=id};
let tree=table.render(props);
const retries=elements(tree).filter(n=>n.type==='button'&&String(n.props['aria-label']).startsWith('Повторить скан #'));
assert.equal(retries.length,3);
get(tree,n=>n.props['aria-label']==='Повторить скан #1').props.onClick();assert.equal(retried,1);
assert(get(tree,n=>n.props['aria-label']==='Повторить скан #2').props.disabled);
assert(!elements(tree).some(n=>['Повторить скан #4','Повторить скан #5','Повторить скан #6'].includes(n.props['aria-label'])));
let resolveRetry,retryCalls=0;
const api={listScans:async()=>({scans:[scan(1)],total:1}),retryScan:()=>{retryCalls++;return new Promise(r=>resolveRetry=r);}};
const home=createHarness('pages/HomePage.tsx',name=>{
 if(name.includes('ProjectContext'))return {useProject:()=>({selection:{projectId:null,partId:null}})};
 if(name==='axios')return {__esModule:true,default:{isAxiosError:()=>true}};
 if(name==='react-router-dom')return {Link:'Link'};
 if(name.includes('api/client'))return api;
 if(name.includes('ScanForm'))return {__esModule:true,default:'ScanForm'};
 if(name.includes('ScanTable'))return {__esModule:true,default:'ScanTable'};
 throw Error(name);
},{localStorage:{getItem:()=>null,setItem(){}},setInterval:()=>1,clearInterval(){}});
(async()=>{
 tree=home.render();home.effects();await tick();tree=home.render();
 const handler=get(tree,n=>n.type==='ScanTable').props.onRetry;
 const operation=handler(1);await handler(1);assert.equal(retryCalls,1,'double click must not enqueue twice');
 tree=home.render();assert(get(tree,n=>n.type==='ScanTable').props.retryingIds.has(1));
 resolveRetry(scan(7,'queued'));await operation;tree=home.render();assert.match(text(tree),/Создан повтор скана #1/);assert(get(tree,n=>n.type==='Link'&&n.props.to==='/scan/7'));assert(!get(tree,n=>n.type==='ScanTable').props.retryingIds.has(1));
 api.retryScan=async()=>{throw {response:{data:{detail:'Очередь недоступна'}}};};
 await get(tree,n=>n.type==='ScanTable').props.onRetry(1);tree=home.render();assert.match(text(get(tree,n=>n.props.role==='alert')),/Очередь недоступна/);
 console.log('PASS: retry from history, terminal-only availability, busy state, duplicate-submit guard, result link and server error');
})().catch(e=>{console.error(e);process.exitCode=1;});
