// Run: node frontend/tests/observedPaths.cjs (requires @babel/core and preset-typescript).
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const babel=require('@babel/core');
const code=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/utils/observedPaths.ts'),'utf8'),{filename:'observedPaths.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
const context={exports:{}};vm.runInNewContext(code,context);
const {buildObservationGraph:build,shortestObservedPath:find}=context.exports;
const id=(part,ip)=>JSON.stringify([part,ip]);
const column=(n,source,part=1)=>({id:n,source_host:source,network:`part-${part}`,network_part_id:part,observed_at:null,author:null});
const row=(part,ip,report_id,state='found',hostname=null,protocol='tcp')=>({device_id:id(part,ip),ip,hostname,network:`part-${part}`,port:22,protocol,cells:[{report_id,state,service:'ssh'}]});
let data={columns:[column(1,'10.0.0.1 · entry'),column(2,'10.0.0.2'),column(3,'10.0.0.3')],rows:[row(1,'10.0.0.2',1),row(1,'10.0.0.3',2),row(1,'10.0.0.2',3)]};
let graph=build(data),start=Array.from(graph.nodes.values()).find(n=>n.label.includes('entry')).id;
let route=find(graph,start,id(1,'10.0.0.3'));assert.equal(route.length,2);assert.equal(route[0].evidence[0].report.id,1);assert.equal(route[1].evidence[0].report.id,2);
assert.equal(find(graph,id(1,'10.0.0.3'),start),null,'direction and cycles');
assert.equal(find(graph,start,start).length,0);assert.equal(find(graph,start,'missing'),null);
for(const state of ['unknown','not_found','not_tested']){graph=build({...data,rows:[row(1,'10.0.0.2',1,state),row(1,'10.0.0.3',2)]});assert.equal(find(graph,start,id(1,'10.0.0.3')),null,state);}
graph=build({...data,rows:[...data.rows,row(1,'10.0.0.3',1)]});assert.equal(find(graph,start,id(1,'10.0.0.3')).length,1,'shortest path');
graph=build({columns:[column(1,'outside'),column(2,'10.0.0.2',2)],rows:[row(1,'10.0.0.2',1),row(2,'10.0.0.3',2)]});start=Array.from(graph.nodes.values()).find(n=>n.label==='outside').id;assert.equal(find(graph,start,id(2,'10.0.0.3')),null,'overlapping IPs do not join');
graph=build({columns:[column(1,'outside'),column(2,'pivot.local')],rows:[row(1,'10.0.0.2',1,'found','pivot.local'),row(1,'10.0.0.3',2)]});start=Array.from(graph.nodes.values()).find(n=>n.label==='outside').id;assert.equal(find(graph,start,id(1,'10.0.0.3')).length,2,'exact hostname');
graph=build({columns:[column(1,'outside'),column(2,'pivot.local')],rows:[row(1,'10.0.0.2',1,'found','pivot.local'),row(1,'10.0.0.4',1,'found','pivot.local'),row(1,'10.0.0.3',2)]});start=Array.from(graph.nodes.values()).find(n=>n.label==='outside').id;assert.equal(find(graph,start,id(1,'10.0.0.3')),null,'ambiguous hostname not guessed');
graph=build({columns:[column(1,'10.0.0.2')],rows:[row(1,'10.0.0.2',1)]});assert.equal(graph.outgoing.size,0,'self observations do not produce transitions');
graph=build({columns:[column(1,'outside'),column(2,'outside')],rows:[row(1,'10.0.0.2',1),row(1,'10.0.0.2',2)]});start=Array.from(graph.nodes.values()).find(n=>n.label==='outside').id;assert.equal(find(graph,start,id(1,'10.0.0.2'))[0].evidence.length,2,'all report evidence retained');
graph=build({columns:[column(1,'outside')],rows:[row(1,'10.0.0.2',1,'found',null,'host')]});start=Array.from(graph.nodes.values()).find(n=>n.label==='outside').id;assert.equal(find(graph,start,id(1,'10.0.0.2')),null,'host-only discovery is not service access');
// Explicit shared addressing enables cross-part joins.
data={merge_parts:true,columns:[column(1,'outside'),column(2,'10.0.0.2',2)],rows:[row(null,'10.0.0.2',1),row(null,'10.0.0.3',2)]};graph=build(data);start=Array.from(graph.nodes.values()).find(n=>n.label==='outside').id;assert.equal(find(graph,start,id(null,'10.0.0.3')).length,2);
console.log('PASS: multi-hop, shortest path, direction, cycles, unknown states, separate address spaces, ambiguous/exact hostnames, self edges, evidence, shared addressing, host-only reports');
// Exercise controls and evidence rendering without a browser.
let slots=[],cursor=0;
const hooks={useMemo:fn=>fn(),useState(initial){const i=cursor++;if(!(i in slots))slots[i]=initial;return [slots[i],value=>slots[i]=value];}};
const React={createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(v=>v!==null&&v!==undefined&&v!==false)};}};
const ui={exports:{},React,require(name){if(name.includes('i18n/core'))return require('./helpers/i18n.cjs');if(name==='react')return hooks;if(name==='react-router-dom')return {Link:'Link'};if(name==='lucide-react')return {Route:'Route'};if(name.includes('observedPaths'))return context.exports;throw Error(name);}};
const uiCode=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/components/ObservedPaths.tsx'),'utf8'),{filename:'ObservedPaths.tsx',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-react-jsx','@babel/plugin-transform-modules-commonjs']}).code;
vm.runInNewContext(uiCode,ui);
const sample={columns:[column(1,'outside'),column(2,'10.0.0.2')],rows:[row(1,'10.0.0.2',1),row(1,'10.0.0.3',2)]};
const render=()=>{cursor=0;return ui.exports.default({data:sample});};
const elements=n=>n&&typeof n==='object'?[n,...n.children.flatMap(elements)]:[];
const text=n=>n&&typeof n==='object'?n.children.map(text).join(''):String(n??'');
let tree=render();elements(tree).filter(n=>n.type==='select')[0].props.onChange({target:{value:JSON.stringify(['source',1,'outside'])}});tree=render();elements(tree).find(n=>n.props['aria-label']==='Целевой хост').props.onChange({target:{value:'10.0.0.3 · part-1'}});tree=render();elements(tree).find(n=>n.type==='button').props.onClick();tree=render();
assert.equal(elements(tree).filter(n=>n.type==='Link').length,2,'UI links every step to evidence');assert.match(text(tree),/требуется проверка/);assert.match(text(tree),/Время сканирования неизвестно/);
elements(tree).filter(n=>n.type==='select')[0].props.onChange({target:{value:id(1,'10.0.0.2')}});tree=render();assert.equal(elements(tree).filter(n=>n.type==='Link').length,0,'changing selection clears old result');
console.log('PASS: path controls, evidence links, time warning, stale selection clearing');

// A partially entered target must not silently keep the previous destination.
elements(tree).find(n=>n.props['aria-label']==='Целевой хост').props.onChange({target:{value:'10.0.0.'}});tree=render();assert.equal(elements(tree).find(n=>n.type==='button').props.disabled,true);assert.equal(elements(tree).filter(n=>n.type==='Link').length,0);
// An exact unique IP also works without choosing a suggestion.
elements(tree).find(n=>n.props['aria-label']==='Целевой хост').props.onChange({target:{value:'10.0.0.3'}});tree=render();assert.equal(elements(tree).find(n=>n.type==='button').props.disabled,false);
// Same IP in two address spaces requires an explicit suggestion, never guess.
slots=[];sample.rows.push(row(2,'10.0.0.3',1));tree=render();elements(tree).find(n=>n.props['aria-label']==='Целевой хост').props.onChange({target:{value:'10.0.0.3'}});tree=render();assert.equal(elements(tree).find(n=>n.type==='button').props.disabled,true);assert.match(text(tree),/нескольких частях сети/);
elements(tree).find(n=>n.props['aria-label']==='Целевой хост').props.onChange({target:{value:'10.0.0.3 · part-2'}});tree=render();assert.equal(elements(tree).find(n=>n.type==='button').props.disabled,false);
assert.equal(elements(tree).filter(n=>n.type==='select').length,1,'only source remains a separate dropdown');
console.log('PASS: single target input, exact IP, partial input clears stale selection, duplicate IP requires network choice');
// Navigation from the map preselects both ends and shows the chain immediately.
slots=[];cursor=0;tree=ui.exports.default({data:sample,initialFrom:JSON.stringify(['source',1,'outside']),initialTo:id(1,'10.0.0.3')});
assert(elements(tree).some(n=>n.type==='Link'&&n.props.to==='/scan/2'));assert.match(text(tree),/Найдена цепочка/);
console.log('PASS: map-to-path navigation preselects endpoints and computes the chain');
