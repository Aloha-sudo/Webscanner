const assert=require('node:assert/strict');
const {createHarness,text,get,tick}=require('./helpers/componentHarness.cjs');
let timers=[],bodies=[];
const entry={share:'Docs',path:'HR/note.txt',parent:'HR',name:'note.txt',kind:'file',metadata:{size:'1 KB'}};
const buildExplorer=()=>createHarness('components/SmbExplorer.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:{isAxiosError:()=>false}};
 if(name.includes('api/client'))return {browseSmbReport:async(scan,id,params)=>{bodies.push(params);return {items:[entry],total:1};},startSmbFileAction:async(scan,id,token,body)=>{bodies.push(body);return {status:'completed',result:body.action==='list'?{items:[entry],total:1}:{preview:{supported:true,text:'SEARCH FILE CONTENT'}}};}};
 if(name.includes('clipboard'))return {copyText:async()=>{}};
 if(name.includes('smbCommander'))return {parseSmbCommand(){}};
 throw Error(name);
},{setTimeout:fn=>{const task={fn,active:true};timers.push(task);return task;},clearTimeout:task=>{if(task)task.active=false;}});
const explorer=buildExplorer();
const props={scanId:1,report:{id:'one',host:'192.0.2.1',account:'LAB\\reader'},share:'Docs',initialEntry:entry,session:null,onSession(){},onClose(){}};
const render=()=>explorer.render(props);
const flush=async()=>{const tasks=timers;timers=[];for(const task of tasks)if(task.active)task.fn();await tick();};
(async()=>{
 let tree=render();explorer.effects();await flush();tree=render();explorer.effects();assert.equal(bodies[0].parent,'HR');assert.match(text(tree),/note.txt/);assert.equal(get(tree,n=>n.type==='tr'&&text(n).includes('note.txt')).props['aria-selected'],true);
 props.session={token:'session',account:'LAB\\reader'};tree=render();explorer.effects();await flush();tree=render();explorer.effects();await flush();tree=render();assert(bodies.some(body=>body.action==='preview'&&body.path==='HR/note.txt'));assert.match(text(tree),/SEARCH FILE CONTENT/);
 timers=[];const restored=buildExplorer();const restoreProps={...props,session:null,initialEntry:undefined,initialLocation:{path:'HR',offset:100,query:'note',selected:entry,scrollTop:224}};
 let restoredTree=restored.render(restoreProps);const scroll=get(restoredTree,n=>n.props.className==='smb-commander-list-scroll').props.ref;scroll.current={scrollTop:0};restored.effects();await flush();restoredTree=restored.render(restoreProps);restored.effects();
 assert.equal(bodies[bodies.length-1].parent,'HR');assert.equal(bodies[bodies.length-1].offset,100);assert.equal(bodies[bodies.length-1].query,'note');assert.equal(scroll.current.scrollTop,224);assert.equal(get(restoredTree,n=>n.type==='tr'&&text(n).includes('note.txt')).props['aria-selected'],true);
 console.log('PASS: share navigation restores folder, page, filter, selection and list scroll');
 console.log('PASS: search opens the containing folder, selects the exact file and previews it after connecting');
})().catch(error=>{console.error(error);process.exitCode=1;});
