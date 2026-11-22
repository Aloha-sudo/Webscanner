const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),vm=require('vm'),babel=require('@babel/core');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
const source=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/utils/smbCommander.ts'),'utf8'),{filename:'smbCommander.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
const commander={exports:{}};vm.runInNewContext(source,commander);
const file={share:'Docs',path:'hello.txt',parent:'',name:'hello.txt',kind:'file',metadata:{size:'6 B'}};
const second={...file,path:'second.txt',name:'second.txt'};
const folder={...file,path:'folder',name:'folder',kind:'directory'};
let bodies=[],clicks=0,downloaded=0,timerId=0,timers=new Map(),lateResolve=null,defer=false;
const jobResult=body=>body.action==='list'?{items:[folder,file,second],total:3,offset:0,limit:100}:body.action==='preview'?{preview:{supported:true,text:body.path==='hello.txt'?'<script>example</script>':'SECOND FILE'}}:body.action==='permissions'?{rights:[{right:'READ',status:'allowed'},{right:'WRITE',status:'denied'}]}:{filename:'hello.txt',size:6};
const api={startSmbFileAction:async(scan,id,token,body)=>{assert.equal(token,'session');bodies.push(body);if(defer&&body.action==='preview'){defer=false;return new Promise(resolve=>lateResolve=resolve);}return {id:'job',status:'completed',result:jobResult(body)};},downloadSmbFile:async()=>{downloaded++;return 'blob';},closeSmbSession:async()=>{}};
const explorer=createHarness('components/SmbExplorer.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:{isAxiosError:()=>false}};
 if(name.includes('api/client'))return api;
 if(name.includes('smbCommander'))return commander.exports;
 if(name.includes('clipboard'))return {copyText:async()=>{}};
 throw Error(name);
},{setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},window:{document:{createElement:()=>({click(){clicks++;},remove(){}}),body:{appendChild(){}}}}});
const props={scanId:1,report:{id:'report',host:'192.0.2.1',account:'LAB\\reader'},share:'Docs',session:{token:'session',account:'LAB\\reader'},onSession(){},onClose(){}};
const render=()=>explorer.render(props);
const flush=async(max=500)=>{const selected=[...timers].filter(([,timer])=>timer.delay<=max);for(const [id,timer] of selected){timers.delete(id);timer.fn();}await tick();};
const row=(tree,name)=>get(tree,n=>n.type==='tr'&&text(n).includes(name));
(async()=>{
 let tree=render();assert(!elements(tree).some(n=>n.props?.name==='secret'||n.props?.name==='username'),'file explorer must not contain a second credential form');explorer.effects();explorer.replayEffects();await flush(0);tree=render();assert.equal(bodies[0].action,'list');assert.equal(bodies.filter(b=>b.action==='list').length,1,'StrictMode effect replay must not connect twice');assert.match(text(tree),/hello.txt/);
 assert.equal(elements(tree).filter(n=>n.type==='dialog'||String(n.type)==='WorkspaceDialog').length,0,'file preview uses no nested modal');
 defer=true;get(row(tree,'hello.txt'),n=>n.type==='button').props.onClick({stopPropagation(){}});tree=render();explorer.effects();await flush();assert.equal(bodies.filter(b=>b.action==='preview').length,1,'click plus automatic preview must share one in-flight request');lateResolve({id:'first',status:'completed',result:jobResult({action:'preview',path:'hello.txt'})});await tick();tree=render();assert.match(text(get(tree,n=>n.type==='pre')),/script/);assert(!elements(tree).some(n=>n.props.dangerouslySetInnerHTML));
 assert.equal(bodies.filter(b=>b.action==='preview').length,1,'one file selection uses one preview operation');
 await get(tree,n=>n.type==='button'&&text(n)==='Права').props.onClick();tree=render();assert.match(text(tree),/Разрешено/);assert.match(text(tree),/Запрещено/);
 await get(tree,n=>n.type==='button'&&text(n)==='Скачать').props.onClick();tree=render();assert.equal(clicks,1);assert.equal(downloaded,1);assert.match(text(tree),/передан браузеру/);
 // An in-flight preview for the previous selection must never replace the current file.
 defer=true;row(tree,'second.txt').props.onClick();tree=render();explorer.effects();await flush();
 tree=render();row(tree,'hello.txt').props.onClick();tree=render();explorer.effects();await flush();
 lateResolve({id:'late',status:'completed',result:{preview:{supported:true,text:'STALE SECRET'}}});await tick();tree=render();assert(!text(tree).includes('STALE SECRET'));assert.match(text(tree),/script/);
 const before=bodies.filter(b=>b.action==='preview').length;tree.props.onKeyDown({key:'ArrowDown',target:{tagName:'SECTION'},preventDefault(){}});tree=render();explorer.effects();await flush();tree=render();assert.match(text(tree),/SECOND FILE/);assert.equal(bodies.filter(b=>b.action==='preview').length,before+1);
 get(tree,n=>n.type==='button'&&text(n)==='Командная строка').props.onClick();tree=render();get(tree,n=>n.props['aria-label']==='Команда SMB').props.onChange({target:{value:'pwd'}});tree=render();await get(tree,n=>n.type==='form'&&elements(n).some(c=>c.props['aria-label']==='Команда SMB')).props.onSubmit({preventDefault(){}});tree=render();assert.match(text(tree),/192\.0\.2\.1/);
 console.log('PASS: dense commander list, single-click inline preview, keyboard navigation, preview caching/deduplication, stale-response isolation, rights, download and SMB commands');
})().catch(e=>{console.error(e);process.exitCode=1;});
