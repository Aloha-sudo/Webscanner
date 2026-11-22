const assert=require('node:assert/strict');
const {createHarness,elements,get,text,tick}=require('./helpers/componentHarness.cjs');
let created=0,requests=[],saved,workspace;
const secret={value:'fixture-password'};
class FormData {constructor(form){this.data=form.values;}get(name){return this.data[name];}}
const form=createHarness('components/SmbScanForm.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:{isAxiosError:()=>false}};
 if(name.includes('api/client'))return {createSecretWorkspace:async targets=>{created++;assert.equal(targets,'192.0.2.0/29');return {id:77,targets};},startSmbScan:async(id,body)=>{requests.push({id,body});return {id:'job',status:'queued',completed:0,report_ids:[],options:{targets:['192.0.2.1']},browse_session:{token:'cap',account:'LAB\\reader'}};}};
 throw Error(name);
},{FormData});
const props={scanId:0,purpose:'secrets',initiallyOpen:true,defaultTargets:'',onReports(){},onSession:(value,id)=>saved={value,id},onWorkspace:value=>workspace=value};
(async()=>{
 let tree=form.render(props);form.effects();await tick();tree=form.render(props);assert.equal(get(tree,n=>n.type==='fieldset').props.disabled,false);
 get(tree,n=>n.type==='select').props.onChange({target:{value:'password'}});tree=form.render(props);
 assert.equal(elements(get(tree,n=>n.props.className==='smb-credential-grid has-credentials')).filter(n=>n.type==='label').length,4,'main fields share one compact grid');assert(!text(tree).includes('Только найти шары'),'secret preparation must not offer an ineffective shares-only action');
 await get(tree,n=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{values:{targets:'192.0.2.0/29',username:'reader',domain:'LAB',password:'fixture-password'},elements:{namedItem:()=>secret}}});
 assert.equal(created,1);assert.equal(requests[0].id,77);assert.equal(requests[0].body.spider,true);assert.equal(saved.id,77);assert.equal(saved.value.token,'cap');assert.equal(workspace.id,77);assert.equal(secret.value,'');
 console.log('PASS: standalone secrets flow needs no project or port scan, prepares SMB files with one credential submission and saves the new context capability');
})().catch(error=>{console.error(error);process.exitCode=1;});
