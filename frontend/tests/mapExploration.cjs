const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict'),babel=require('@babel/core');
const directory=path.join(__dirname,'../src');
function load(file,extra=()=>{throw Error('Unexpected dependency');},globals={}){const code=babel.transformSync(fs.readFileSync(path.join(directory,file),'utf8'),{filename:file,presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-react-jsx','@babel/plugin-transform-modules-commonjs']}).code;const box={exports:{},require:name=>name.includes('i18n/core')?require('./helpers/i18n.cjs'):extra(name),...globals};vm.runInNewContext(code,box);return box.exports;}
const core=load('utils/observedPaths.ts'),layouts=load('utils/networkMapLayout.ts'),tools=load('utils/mapExploration.ts',()=>layouts);
const id=ip=>JSON.stringify([1,ip]);
const report=(n,source)=>({id:n,source_host:source,network:'HQ',network_part_id:1,observed_at:null,author:null});
const row=(ip,from,port,service)=>({device_id:id(ip),ip,hostname:null,network:'HQ',protocol:'tcp',port,cells:[{report_id:from,state:'found',service}]});
const data={columns:[report(1,'10.0.0.1'),report(2,'10.0.0.2'),report(3,'10.0.0.3'),report(4,'outside')],rows:[row('10.0.0.2',1,22,'ssh'),row('10.0.0.3',2,3389,'ms-wbt-server'),row('10.0.0.5',1,80,'http'),row('10.0.0.1',2,135,'msrpc'),row('10.0.0.2',4,445,'microsoft-ds'),row('10.0.0.4',3,80,'http')]};
const graph=core.buildObservationGraph(data,true),root=graph.reportSources.get(1),target=id('10.0.0.2');
const whole=layouts.layoutNetworkMap(graph,root,new Set());
const focused=tools.layoutHostNeighborhood(graph,target);
assert(focused.positions.has(graph.reportSources.get(4)),'include incoming source outside the original rooted branch');
assert(focused.positions.has(id('10.0.0.1')));assert(focused.positions.has(id('10.0.0.3')));assert(!focused.positions.has(id('10.0.0.4')),'one hop excludes more distant device');assert(!focused.positions.has(id('10.0.0.5')),'exclude unrelated branch');
assert.equal([...focused.positions.keys()].filter(v=>v===id('10.0.0.1')).length,1,'bidirectional neighbor shown once');
assert(focused.edges.every(e=>e.from===target||e.to===target));
const originalEdges=whole.edges.length,filtered=tools.filterMapServices(whole,root,'tcp/3389');
assert.equal(filtered.edges.length,2);assert(filtered.positions.has(target));assert(filtered.positions.has(id('10.0.0.3')));assert(!filtered.positions.has(id('10.0.0.5')));assert.equal(filtered.edges.filter(e=>tools.edgeHasService(e,'tcp/3389')).length,1,'connector stays context, never a false service match');assert.equal(whole.edges.length,originalEdges);
assert.equal(tools.filterMapServices(whole,root,'tcp/9999').edges.length,0);assert.equal(tools.filterMapServices(whole,root,'tcp/9999').positions.size,1);assert.equal(tools.filterMapServices(whole,root,''),whole);
assert.equal(tools.filterMapServices(focused,target,'tcp/445').positions.size,2);
const options=tools.mapServiceOptions(graph);assert(options.some(v=>v.key==='tcp/3389'&&v.label.includes('ms-wbt-server')));assert(!options.some(v=>v.key==='host/0'));

let slots=[],cursor=0,effects=[];
const hooks={useMemo:fn=>fn(),useId:()=>':explore:',useEffect(){},useState(initial){let i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],value=>slots[i]=typeof value==='function'?value(slots[i]):value];},useRef(initial){let i=cursor++;if(!(i in slots))slots[i]={current:initial};return slots[i];},useLayoutEffect(fn,deps){let i=cursor++;if(!slots[i]||deps.some((v,j)=>!Object.is(v,slots[i].deps[j])))effects.push(()=>{slots[i]?.cleanup?.();slots[i]={deps,cleanup:fn()};});}};
const React={createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(v=>v!==false&&v!==null&&v!==undefined)};}};
const component=load('components/VisibilityMap.tsx',name=>{if(name==='react')return hooks;if(name==='react-router-dom')return {Link:'Link'};if(name==='lucide-react')return {};if(name.includes('observedPaths'))return core;if(name.includes('networkMapLayout'))return layouts;if(name.includes('svgExport'))return {};if(name.includes('mapExploration'))return tools;throw Error(name);},{React});
const elements=n=>n&&typeof n==='object'?[n,...n.children.flatMap(elements)]:[];
const text=n=>n&&typeof n==='object'?n.children.map(text).join(''):String(n??'');
const get=(tree,test)=>{const el=elements(tree).find(test);assert(el,'Expected element');return el;};
const viewport={clientWidth:900,clientHeight:600,scrollLeft:0,scrollTop:0,scrollTo(x,y){this.scrollLeft=x;this.scrollTop=y;}};
let source='1';
function render(){cursor=0;const tree=component.default({data,rows:data.rows,source,setSource:v=>source=v,onShowPath(){}});get(tree,n=>n.props['aria-label']==='Многоуровневая карта доступности').props.ref.current=viewport;const pending=effects;effects=[];pending.forEach(fn=>fn());return tree;}
const width=tree=>get(tree,n=>n.type==='svg').props.style.width;
let tree=render();tree=render();get(tree,n=>n.props['aria-label']==='Открыть устройство 10.0.0.2, HQ').props.onClick();tree=render();get(tree,n=>n.props['aria-label']==='Увеличить масштаб').props.onClick();tree=render();
const oldWidth=width(tree);viewport.scrollLeft=110;viewport.scrollTop=190;
get(tree,n=>n.type==='button'&&text(n)==='Показать окружение').props.onClick();tree=render();tree=render();assert.match(text(tree),/Окружение 10.0.0.2/);assert(!elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.4, HQ'));assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство outside, HQ'));
get(tree,n=>n.type==='button'&&text(n)==='Вся карта').props.onClick();tree=render();tree=render();assert.equal(width(tree),oldWidth);assert.equal(viewport.scrollLeft,110);assert.equal(viewport.scrollTop,190);
get(tree,n=>n.props['aria-label']==='Сервис 3389/TCP').props.onChange({target:{checked:true}});tree=render();assert.match(text(tree),/Контекст/);assert(!elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.5, HQ'));assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.3, HQ'));
get(tree,n=>n.type==='button'&&text(n)==='Все сервисы').props.onClick();tree=render();assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.5, HQ'));
console.log('PASS: one-hop neighborhood, shared and reverse neighbors, remote sources, service/context distinction, filter reset and exact viewport restoration');

const both=tools.filterMapServices(whole,root,['tcp/3389','tcp/80']);assert(both.positions.has(id('10.0.0.5')));assert(both.positions.has(id('10.0.0.3')));assert(both.positions.has(id('10.0.0.4')));assert.equal(tools.filterMapServices(whole,root,[]),whole);assert(!tools.edgeHasAnyService(filtered.edges[0],new Set(['udp/3389'])),'protocol must match');
get(tree,n=>n.props['aria-label']==='Сервис 3389/TCP').props.onChange({target:{checked:true}});tree=render();get(tree,n=>n.props['aria-label']==='Сервис 80/TCP').props.onChange({target:{checked:true}});tree=render();assert(get(tree,n=>n.props['aria-label']==='Сервис 3389/TCP').props.checked);assert(get(tree,n=>n.props['aria-label']==='Сервис 80/TCP').props.checked);assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.5, HQ'));assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.3, HQ'));
get(tree,n=>n.props['aria-label']==='Убрать сервис 80/TCP').props.onClick();tree=render();assert(!get(tree,n=>n.props['aria-label']==='Сервис 80/TCP').props.checked);assert(get(tree,n=>n.props['aria-label']==='Сервис 3389/TCP').props.checked);assert(!elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.5, HQ'));
get(tree,n=>n.props['aria-label']==='Поиск сервисов').props.onChange({target:{value:'ms-wbt'}});tree=render();assert(get(tree,n=>n.props['aria-label']==='Сервис 3389/TCP'));assert(!elements(tree).some(n=>n.props['aria-label']==='Сервис 80/TCP'));
get(tree,n=>n.type==='button'&&text(n)==='Все сервисы').props.onClick();tree=render();assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.5, HQ'));
console.log('PASS: multiple services use OR, per-service removal, protocol isolation, option search and full reset');
