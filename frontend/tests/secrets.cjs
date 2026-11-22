const assert=require('node:assert/strict');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
let job={id:'b'.repeat(32),scan_id:1,status:'queued',targets:'192.0.2.1',account:'LAB\\reader',created_at:'2026-11-09T10:00:00Z',stats:{},findings:[]};
const finding={id:'c'.repeat(40),host:'192.0.2.1',share:'Docs',path:'id_rsa',name:'id_rsa',rule:'KeepSSHKeysByFileName',kind:'name',severity:'Black',evidence:'[redacted]'};
let timer,removed=0,previewed=0,searched=0,lastQuery='';
const api={getScan:async()=>({target:'192.0.2.1'}),secretHistory:async()=>[],getSecretJob:async()=>job,searchSecrets:async(options,fast)=>{searched++;assert.equal(options.targets,'192.0.2.1');assert(fast);return {job,session:{token:'CAPABILITY'}};},secretFindings:async(scan,id,query)=>{lastQuery=query;return {items:[finding],total:1};},deleteSecretJob:async()=>{removed++;},secretFile:async()=>{previewed++;return {status:'completed',result:{preview:{text:'fixture-only document'}}};}};
const page=createHarness('pages/SecretsPage.tsx',name=>{
 if(name==='react-router-dom')return {Link:'Link',useSearchParams:()=>[{get:key=>key==='scan'?'1':null},()=>{}]};
 if(name==='axios')return {__esModule:true,default:{isAxiosError:()=>false}};
 if(name.includes('api/client'))return api;
 if(name.includes('SecretSearchForm'))return {__esModule:true,default:'SecretSearchForm'};
 if(name.includes('smbSession'))return {saveSmbSession:()=>{},readSmbSession:()=>({token:'CAPABILITY'})};
 throw Error(name);
},{setInterval:fn=>{timer=fn;return 1;},clearInterval(){},setTimeout:fn=>{Promise.resolve().then(fn);return 1;},clearTimeout(){}});
(async()=>{
 let tree=page.render();page.effects();await tick();tree=page.render();page.effects();
 assert(!text(tree).includes('Шары для проверки'));assert(!text(tree).includes('Сохранённая проверка'));
 await get(tree,n=>n.type==='SecretSearchForm').props.onSubmit({targets:'192.0.2.1'},true);assert.equal(searched,1);tree=page.render();page.effects();await tick();tree=page.render();assert.match(text(tree),/В очереди/);
 job={...job,status:'completed',finding_count:1,stats:{considered:600}};await timer();tree=page.render();page.effects();await tick();tree=page.render();assert.match(text(tree),/KeepSSHKeysByFileName/);
 const input=get(tree,n=>n.props['aria-label']==='Поиск по находкам: имя файла, путь или правило');input.props.onChange({target:{value:'id_rsa'}});tree=page.render();page.effects();await tick();assert.equal(lastQuery,'id_rsa');tree=page.render();
 await get(tree,n=>n.type==='button'&&text(n)==='id_rsa').props.onClick();tree=page.render();assert.equal(previewed,1);assert.match(text(tree),/fixture-only document/);
 get(tree,n=>n.type==='button'&&text(n)==='Удалить результат').props.onClick();tree=page.render();assert.equal(removed,0);await get(tree,n=>n.type==='button'&&text(n)==='Подтвердить удаление').props.onClick();assert.equal(removed,1);
 page.unmount();console.log('PASS: single native search launch, automatic progress, server-side finding search, on-demand preview and confirmed deletion');
})().catch(error=>{console.error(error);process.exitCode=1;});
