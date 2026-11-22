const assert=require('node:assert/strict');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
const css=require('postcss').parse(require('node:fs').readFileSync(require('node:path').join(__dirname,'../src/index.css'),'utf8'));
css.walkRules(rule=>{
 if(rule.selector.includes('.has-selection')&&rule.selector.includes('.smb-table')&&rule.nodes.some(node=>node.prop==='display'&&node.value==='none')){
  assert(rule.selectors.every(selector=>selector.includes('.smb-share-overview')),'compact share mode must not hide file-search or history columns');
 }
});
const entry={share:'Docs',path:'HR/vault.kdbx',parent:'HR',name:'vault.kdbx',kind:'file',metadata:{size:'12 KB'}};
const reports=[{id:'one',host:'192.0.2.1',account:'LAB\\one',coverage:'files'},{id:'two',host:'192.0.2.1',account:'LAB\\two',coverage:'files'}];
let calls=[],active=false,opened=null,resolvers=[];
const search=createHarness('components/SmbFileSearch.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:{isAxiosError:()=>false}};
 if(name.includes('api/client'))return {searchSmbFiles:(scan,query,offset)=>{calls.push({scan,query,offset});return new Promise(resolve=>resolvers.push(resolve));}};
 throw Error(name);
});
const result=(name='HR/vault.kdbx')=>({items:[{host:'192.0.2.1',entry:{...entry,path:name},sources:[{report_id:'one',account:'LAB\\one'},{report_id:'two',account:'LAB\\two'}]}],total:101,covered_hosts:1,hosts:1,partial:true,truncated:false});
const render=()=>search.render({scanId:7,reports,onActive:value=>active=value,onOpen:(report,file)=>opened={report,file}});
const submit=(tree,value)=>{get(tree,n=>n.type==='input').props.onChange({target:{value}});tree=render();get(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});tree=render();search.effects();return render();};
(async()=>{
 let tree=render();search.effects();assert.equal(calls.length,0,'search requires an explicit submit');assert.match(text(tree),/Списки файлов: 1 из 1/);
 tree=submit(tree,'*.kdbx');assert.equal(active,true);assert.equal(calls[0].query,'*.kdbx');
 resolvers.shift()(result());await tick();tree=render();assert.match(text(tree),/vault.kdbx/);assert.match(text(tree),/Результат неполный/);
 get(tree,n=>n.type==='button'&&text(n)==='LAB\\two').props.onClick();assert.equal(opened.report.id,'two');assert.equal(opened.file.parent,'HR');
 get(tree,n=>n.props['aria-label']==='Следующая страница файлов').props.onClick();tree=render();search.effects();assert.equal(calls[1].offset,100);
 const stale=resolvers.shift();tree=submit(tree,'new.txt');const current=resolvers.shift();current(result('new.txt'));await tick();tree=render();stale(result('stale.txt'));await tick();tree=render();assert.match(text(tree),/new.txt/);assert(!text(tree).includes('stale.txt'));
 get(tree,n=>n.type==='button'&&text(n)==='Очистить').props.onClick();tree=render();search.effects();tree=render();assert.equal(active,false);assert(!text(tree).includes('new.txt'));
 console.log('PASS: explicit network-wide saved file search, coverage, account-specific opening, paging, stale-response guard and return to shares');
})().catch(error=>{console.error(error);process.exitCode=1;});
