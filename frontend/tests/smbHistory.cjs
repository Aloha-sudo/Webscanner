const assert=require('node:assert/strict');
const {createHarness,elements,text,get,tick}=require('./helpers/componentHarness.cjs');
const reports=[{id:'a'.repeat(32),host:'192.0.2.1',account:'LAB\\one',shares:[],file_count:0,imported_at:'2026-11-07T10:00:00Z'},{id:'b'.repeat(32),host:'192.0.2.2',account:'LAB\\two',shares:[],file_count:5,imported_at:'2026-11-07T10:00:00Z'}];
let calls=[],deleted=[],fail=true,resolve;
const history=createHarness('components/SmbHistory.tsx',name=>{
 if(name==='axios')return {__esModule:true,default:{isAxiosError:e=>!!e.response}};
 if(name.includes('api/client'))return {deleteSmbReports:async(scan,ids)=>{calls.push({scan,ids});if(fail)throw {response:{data:{detail:'Сначала остановите SMB-проверку'}}};await new Promise(r=>resolve=r);return {deleted:ids};}};
 throw Error(name);
});
const render=()=>history.render({scanId:7,reports,onDeleted:ids=>deleted=ids});
(async()=>{
 let tree=render();history.effects();tree=render();
 assert.equal(get(tree,n=>n.type==='button'&&text(n)==='Удалить выбранные').props.disabled,true);
 get(tree,n=>n.type==='input'&&n.props['aria-label']?.startsWith('Выбрать SMB-результат: 192.0.2.1')).props.onChange({target:{checked:true}});tree=render();
 get(tree,n=>n.type==='button'&&text(n)==='Удалить выбранные').props.onClick();tree=render();assert.equal(calls.length,0,'selection requires explicit confirmation');
 get(tree,n=>n.type==='button'&&text(n)==='Отмена').props.onClick();tree=render();assert.equal(calls.length,0);
 get(tree,n=>n.type==='button'&&text(n)==='Удалить выбранные').props.onClick();tree=render();
 await get(tree,n=>n.type==='button'&&text(n)==='Подтвердить удаление').props.onClick();tree=render();assert.match(text(tree),/Сначала остановите/);assert.equal(deleted.length,0);
 fail=false;const pending=get(tree,n=>n.type==='button'&&text(n)==='Подтвердить удаление').props.onClick();tree=render();
 assert(elements(tree).filter(n=>n.type==='input').every(n=>n.props.disabled));assert(get(tree,n=>n.type==='button'&&text(n)==='Удаление…').props.disabled);
 resolve();await pending;tree=render();assert.equal(JSON.stringify(deleted),JSON.stringify([reports[0].id]));assert.equal(JSON.stringify(calls[1]),JSON.stringify({scan:7,ids:[reports[0].id]}));
 assert.equal(get(tree,n=>n.type==='button'&&text(n)==='Удалить выбранные').props.disabled,true);
 get(tree,n=>n.props['aria-label']==='Выбрать все SMB-результаты').props.onChange({target:{checked:true}});tree=render();assert.match(text(tree),/Выбрано: 2/);
 console.log('PASS: SMB history explicit confirmation/cancel, selected-only deletion, busy guard, server failure and select-all');
})().catch(error=>{console.error(error);process.exitCode=1;});
