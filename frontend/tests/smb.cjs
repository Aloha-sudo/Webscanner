const assert=require('node:assert/strict');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
const report={id:'a'.repeat(32),host:'192.0.2.1',account:'LAB\\reader',source:'192.0.2.2',observed_at:null,imported_at:'2026-11-06T12:00:00Z',filename:'host.json',shares:[{name:'Docs',files:1}],file_count:1};
let imports=0,disconnects=0,collections=0;
class File {constructor(name,size){this.name=name;this.size=size;}}
class FormData {constructor(values){this.values={...values};}get(key){return this.values[key];}set(key,value){this.values[key]=value;}}
const browser=createHarness('components/SmbBrowser.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:{isAxiosError:e=>!!e.response}};
 if(name.includes('api/client'))return {collectSmbFiles:async(scan,id,token,targets)=>{collections++;assert.equal(token,'opaque');assert.equal(targets,'192.0.2.1');return {};},listSmbReports:async()=>[report],closeSmbSession:async()=>{disconnects++;},importSmbReport:async()=>{imports++;return {...report,id:'b'.repeat(32)};}};
 for(const part of ['SmbFileSearch','SmbHistory','SmbShares','SmbExplorer','SmbScanForm','LocalDateTimeInput','WorkspaceDialog'])if(name.includes(part))return {__esModule:true,default:part};
 if(name.includes('smbSession'))return {readSmbSession:()=>null,saveSmbSession:(id,value)=>value,clearSmbSession(){},sessionApplies:(session)=>!!session};
 if(name.includes('localDateTime'))return {validLocalDateTime:()=>true};
 throw Error(name);
},{File,FormData});
const props={scan:{id:1,target:'192.0.2.1',hosts:[{id:1,ip:'192.0.2.1',ports:[]}]}};
const render=()=>browser.render(props);
(async()=>{
 let tree=render();browser.effects();await tick();tree=render();browser.effects();

 const originalScan=props.scan;
 props.scan={...originalScan,target:'192.0.2.0/24',hosts:[
  {id:1,ip:'192.0.2.1',ports:[{port:445,protocol:'tcp',state:'open'}]},
  {id:2,ip:'192.0.2.2',ports:[{port:445,protocol:'udp',state:'open'}]},
  {id:3,ip:'192.0.2.3',ports:[{port:445,protocol:'tcp',state:'open|filtered'}]},
  {id:4,ip:'192.0.2.4',ports:[{port:80,protocol:'tcp',state:'open'}]},
  {id:5,ip:'192.0.2.1',ports:[{port:445,protocol:'tcp',state:'open'}]}
 ]};tree=render();
 assert.equal(get(tree,n=>n.type==='SmbScanForm').props.defaultTargets,'192.0.2.1','only confirmed open TCP 445 hosts, deduplicated; never the whole original subnet');
 get(tree,n=>n.type==='SmbShares').props.onCheckHost('192.0.2.1');tree=render();
 assert.equal(get(tree,n=>n.type==='SmbScanForm').props.targetRequest.targets,'192.0.2.1');
 props.scan={...originalScan,target:'192.0.2.0/24'};tree=render();
 assert.equal(get(tree,n=>n.type==='SmbScanForm').props.defaultTargets,'192.0.2.1','fallback uses saved host IPs rather than rescanning the source CIDR');
 props.scan=originalScan;tree=render();
 assert.equal(get(tree,n=>n.type==='SmbShares').props.reports.length,1);
 get(tree,n=>n.type==='SmbShares').props.onOpen(report,'Docs');tree=render();assert.equal(get(tree,n=>n.type==='SmbExplorer').props.share,'Docs');
 assert.equal(get(tree,n=>n.props?.className==='smb-split-shares').props.hidden,undefined,'share list stays visible beside files');
 assert.equal(get(tree,n=>n.type==='SmbShares').props.selected.share,'Docs');
 get(tree,n=>n.type==='SmbExplorer').props.onLocationChange({path:'HR',offset:0,query:'note',selected:null,scrollTop:72});
 get(tree,n=>n.type==='SmbShares').props.onOpen(report,'Public');tree=render();
 assert.equal(elements(tree).filter(n=>n.type==='SmbExplorer').length,1,'one right-hand explorer, no workspace tabs');
 assert.equal(get(tree,n=>n.type==='SmbExplorer').props.share,'Public');
 get(tree,n=>n.type==='SmbExplorer').props.onClose();tree=render();
 assert.equal(elements(tree).filter(n=>n.type==='SmbExplorer').length,0);
 assert.equal(get(tree,n=>n.type==='SmbShares').props.reports.length,1);
 assert.equal(disconnects,0);
 get(tree,n=>n.type==='SmbShares').props.onOpen(report,'Docs');tree=render();assert.equal(get(tree,n=>n.type==='SmbExplorer').props.initialLocation.path,'HR');
 await get(tree,n=>n.type==='SmbFileSearch').props.onCollect();tree=render();assert.equal(get(tree,n=>n.type==='SmbScanForm').props.targetRequest.collectFiles,true);
 get(tree,n=>n.type==='SmbExplorer').props.onConnect();tree=render();assert.equal(get(tree,n=>n.type==='SmbScanForm').props.connectionRequest.report.id,report.id);
 get(tree,n=>n.type==='SmbScanForm').props.onSession({token:'opaque',account:'LAB\\reader',expires_in:900});tree=render();assert.equal(get(tree,n=>n.type==='SmbExplorer').props.session.token,'opaque');
 await get(tree,n=>n.type==='SmbFileSearch').props.onCollect();tree=render();assert.equal(collections,1,'existing connection starts file collection without asking for a password');
 get(tree,n=>n.type==='button'&&text(n)==='Импорт SMB').props.onClick({currentTarget:{closest:()=>null}});tree=render();
 await get(tree,n=>n.type==='form'&&n.props.className.includes('smb-import')).props.onSubmit({preventDefault(){},currentTarget:{file:new File('large.json',21*1024*1024)}});tree=render();assert.equal(imports,0);assert.match(text(tree),/не больше 20 МБ/);
 await get(tree,n=>n.type==='form'&&n.props.className.includes('smb-import')).props.onSubmit({preventDefault(){},currentTarget:{host:'192.0.2.1',file:new File('host.json',100)}});tree=render();assert.equal(imports,1);assert.equal(get(tree,n=>n.type==='SmbShares').props.reports.length,2);
 get(tree,n=>n.type==='SmbFileSearch').props.onActive(true);get(tree,n=>n.type==='SmbFileSearch').props.onOpen(report,{share:'Docs',path:'HR/note.txt',parent:'HR',name:'note.txt',kind:'file',metadata:{}});tree=render();assert.equal(get(tree,n=>n.type==='SmbExplorer').props.initialEntry.path,'HR/note.txt');assert.equal(get(tree,n=>n.type==='SmbFileSearch').props.showResults,false,'opening a result retains the search component but returns right area to the file');get(tree,n=>n.type==='SmbFileSearch').props.onActive(true);tree=render();assert.equal(get(tree,n=>n.type==='SmbFileSearch').props.showResults,true);
 get(tree,n=>n.type==='button'&&text(n)==='История и удаление').props.onClick({currentTarget:{closest:()=>null}});tree=render();
 get(tree,n=>n.type==='SmbHistory').props.onDeleted([report.id]);tree=render();assert.equal(elements(tree).filter(n=>n.type==='SmbExplorer').length,0,'deleting an open result closes its file panel');assert.equal(get(tree,n=>n.type==='SmbShares').props.reports.length,1,'unselected reports remain');
 browser.unmount();assert.equal(disconnects,0,'leaving the SMB tab must not revoke an active connection');
 console.log('PASS: SMB share list stays visible beside one selected explorer, switches shares without tabs, preserves session and guards imports');
})().catch(e=>{console.error(e);process.exitCode=1;});
