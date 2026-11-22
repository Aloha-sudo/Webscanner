const assert=require('node:assert/strict');
const {createHarness,text,get,tick}=require('./helpers/componentHarness.cjs');
const file={id:'c'.repeat(40),host:'192.0.2.1',share:'Docs',path:'id_rsa',name:'id_rsa',rule:'Key',kind:'name',severity:'Black'};
const job={id:'a'.repeat(32),scan_id:1,status:'completed',source:'smb',targets:'192.0.2.1',created_at:'2026-11-10T10:00:00Z',stats:{}};
function fixture({session=true,response={status:'completed',result:{preview:{supported:true,text:'fictional-preview'}}},legacy=false}={}){
 let capability=session?{token:'ACTIVE'}:null,reads=0,reconnected=0;
 const item=legacy?{...file,id:undefined,report_id:'b'.repeat(32)}:file;
 const api={getScan:async()=>({target:job.targets}),getSecretJob:async()=>job,secretHistory:async()=>[],secretFindings:async()=>({items:[item],total:1}),secretFile:async()=>{assert(!legacy);reads++;return response;},startSmbFileAction:async(scan,report,token,request)=>{assert(legacy);assert.equal(request.path,'id_rsa');reads++;return response;},connectSecretSource:async()=>{reconnected++;return {token:'RECONNECTED'};}};
 const page=createHarness('pages/SecretsPage.tsx',name=>{
  if(name==='react-router-dom')return {Link:'Link',useSearchParams:()=>[{get:key=>key==='scan'?'1':key==='job'?job.id:null},()=>{}]};
  if(name==='axios')return {__esModule:true,default:{isAxiosError:error=>!!error?.isAxiosError}};
  if(name.includes('api/client'))return api;
  if(name.includes('SecretSearchForm'))return {__esModule:true,default:'SecretSearchForm'};
  if(name.includes('smbSession'))return {readSmbSession:()=>capability,saveSmbSession:(_scan,value)=>capability=value};
  throw Error(name);
 },{setTimeout:fn=>{Promise.resolve().then(fn);return 1;},clearTimeout(){},setInterval:()=>1,clearInterval(){}});
 const render=()=>page.render();
 const ready=async()=>{for(let i=0;i<5;i++){render();page.effects();await tick();}return render();};
 return {page,render,ready,reads:()=>reads,reconnected:()=>reconnected};
}
(async()=>{
 const expired=fixture({session:false});let tree=await expired.ready();await get(tree,n=>n.type==='button'&&text(n)==='id_rsa').props.onClick();tree=expired.render();assert.match(text(get(tree,n=>n.type==='pre')),/Подключение истекло/);assert.equal(expired.reads(),0);
 await get(tree,n=>n.type==='SecretSearchForm').props.onSubmit({targets:'192.0.2.1'},true);tree=expired.render();assert.equal(expired.reconnected(),1);assert.equal(expired.reads(),1);assert.match(text(get(tree,n=>n.type==='pre')),/fictional-preview/);expired.page.unmount();
 const denied=fixture({response:{status:'failed',error:'access_denied'}});tree=await denied.ready();await get(tree,n=>n.type==='button'&&text(n)==='id_rsa').props.onClick();tree=denied.render();assert.match(text(get(tree,n=>n.type==='pre')),/Нет прав на чтение/);denied.page.unmount();
 const empty=fixture({response:{status:'completed',result:{preview:{supported:true,text:''}}}});tree=await empty.ready();await get(tree,n=>n.type==='button'&&text(n)==='id_rsa').props.onClick();assert.equal(text(get(empty.render(),n=>n.type==='pre')),'Файл пуст');empty.page.unmount();
 const legacy=fixture({legacy:true});tree=await legacy.ready();await get(tree,n=>n.type==='button'&&text(n)==='id_rsa').props.onClick();assert.equal(legacy.reads(),1);assert.match(text(get(legacy.render(),n=>n.type==='pre')),/fictional-preview/);legacy.page.unmount();
 console.log('PASS: expired preview explains reconnection, selected file auto-opens after login, inline access failure, empty text and legacy SMB finding preview');
})().catch(error=>{console.error(error);process.exitCode=1;});
