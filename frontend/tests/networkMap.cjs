// Run from any directory: node frontend/tests/networkMap.cjs
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),babel=require('@babel/core');
const directory=path.join(__dirname,'../src');
function load(name,requireExtra=()=>{throw Error('Unexpected dependency');},globals={}){
 const code=babel.transformSync(fs.readFileSync(path.join(directory,name),'utf8'),{filename:name,presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-react-jsx','@babel/plugin-transform-modules-commonjs']}).code;
 const sandbox={exports:{},require:name=>name.includes('i18n/core')?require('./helpers/i18n.cjs'):requireExtra(name),...globals};vm.runInNewContext(code,sandbox);return sandbox.exports;
}
const core=load('utils/observedPaths.ts');const layoutTools=load('utils/networkMapLayout.ts');const {layoutNetworkMap:layout,fitMapZoom}=layoutTools;
const exploration=load('utils/mapExploration.ts',name=>{if(name.includes('networkMapLayout'))return layoutTools;throw Error(name);});
const id=ip=>JSON.stringify([1,ip]);
const report=(n,source)=>({id:n,source_host:source,network:'HQ',network_part_id:1,observed_at:null,author:null});
const row=(ip,report_id,port=22,protocol='tcp')=>({device_id:id(ip),network:'HQ',ip,hostname:null,port,protocol,cells:[{report_id,state:'found',service:'ssh'}]});
const data={columns:[report(1,'10.0.0.1'),report(2,'10.0.0.2'),report(3,'10.0.0.3')],rows:[row('10.0.0.2',1),row('10.0.0.3',2),row('10.0.0.4',3),row('10.0.0.2',3)]};
const graph=core.buildObservationGraph(data,true);const root=graph.reportSources.get(1);
let drawing=layout(graph,root,new Set());assert.equal(drawing.positions.size,4);assert.equal(drawing.levels,4);assert.equal(drawing.edges.length,4,'includes back edge without infinite recursion');
assert.equal(new Set([...drawing.positions.keys()]).size,4,'one node per identity');
drawing=layout(graph,root,new Set([id('10.0.0.2')]));assert.equal(drawing.positions.size,2);assert.equal(drawing.edges.length,1);
drawing=layout(graph,root,new Set([root]));assert.equal(drawing.positions.size,1);
// A shared descendant remains reachable through a second open branch.
const diamond={columns:[...data.columns,report(4,'10.0.0.4')],rows:[row('10.0.0.2',1),row('10.0.0.3',1),row('10.0.0.4',2),row('10.0.0.4',3)]};
let diamondGraph=core.buildObservationGraph(diamond,true);drawing=layout(diamondGraph,diamondGraph.reportSources.get(1),new Set([id('10.0.0.2')]));assert(drawing.positions.has(id('10.0.0.4')));assert.equal(drawing.positions.size,4);
const hostData={columns:[report(1,'outside')],rows:[row('10.0.0.2',1,0,'host')]};assert.equal(core.buildObservationGraph(hostData).outgoing.size,0);assert.equal(core.buildObservationGraph(hostData,true).outgoing.size,1,'map preserves host-only sightings without changing service paths');
let slots=[],cursor=0,source='1',requested=null;
const hooks={useMemo:fn=>fn(),useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},useRef:()=>({current:null}),useEffect(){},useLayoutEffect(){},useId:()=>':test:'};
const React={createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(v=>v!==null&&v!==undefined&&v!==false)};}};
const component=load('components/VisibilityMap.tsx',name=>{
 if(name==='react')return hooks;if(name==='react-router-dom')return {Link:'Link'};if(name==='lucide-react')return {};
 if(name.includes('svgExport'))return {};if(name.includes('mapExploration'))return exploration;if(name.includes('observedPaths'))return core;if(name.includes('networkMapLayout'))return layoutTools;throw Error(name);
},{React});
const elements=n=>n&&typeof n==='object'?[n,...n.children.flatMap(elements)]:[];
const text=n=>n&&typeof n==='object'?n.children.map(text).join(''):String(n??'');
const get=(tree,predicate)=>{const el=elements(tree).find(predicate);assert(el,'expected element');return el;};
const render=()=>{cursor=0;return component.default({data,rows:data.rows,source,setSource:value=>source=value,onShowPath:(from,to)=>requested={from,to}});};
let tree=render();get(tree,n=>n.props['aria-label']==='Свернуть ветку 10.0.0.2').props.onClick();tree=render();assert(!elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.4, HQ'));
get(tree,n=>n.props['aria-label']==='Раскрыть ветку 10.0.0.2').props.onKeyDown({key:'Enter',preventDefault(){}});tree=render();assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.4, HQ'));
get(tree,n=>n.props['aria-label']==='Открыть устройство 10.0.0.3, HQ').props.onClick();tree=render();assert.match(text(tree),/Отчёты из этого хоста/);assert(elements(tree).some(n=>n.type==='Link'&&n.props.to==='/scan/3'));
get(tree,n=>n.type==='button'&&text(n)==='Показать путь до хоста').props.onClick();assert.equal(requested.from,root);assert.equal(requested.to,id('10.0.0.3'));
get(tree,n=>n.type==='button'&&text(n)==='22/TCP').props.onClick();tree=render();assert.match(text(tree),/Кто видит этот сервис/);assert(elements(tree).some(n=>n.type==='Link'&&n.props.to==='/scan/2'));
get(tree,n=>n.type==='button'&&text(n)==='Вернуться к веткам').props.onClick();tree=render();assert(elements(tree).some(n=>n.props['aria-label']==='Открыть устройство 10.0.0.4, HQ'));
get(tree,n=>n.type==='select').props.onChange({target:{value:id('10.0.0.3')}});tree=render();assert.equal(source,'3');assert(!elements(tree).some(n=>n.type==='aside'),'changing root clears card');
console.log('PASS: multilevel layout, shared descendants, cycles, collapse/expand with keyboard, host-only sightings, source reports, path navigation, reverse visibility, changing root');

const newestFirst={...data,columns:[data.columns[2],data.columns[1],data.columns[0]]};
assert.equal(core.initialSourceReport(newestFirst),1,'default root is the upstream source even when newest imported report is first');
assert.equal(core.initialSourceReport({columns:[],rows:[]}),undefined);
console.log('PASS: automatic initial source follows chain coverage, not report order');
// Compact layout bounds and fitting a large branch into a viewport.
assert.equal(fitMapZoom(1000,700,500,240),1,'small graphs keep natural text size');
const fitScale=fitMapZoom(900,600,1400,1600);assert(fitScale*1400<=870);assert(fitScale*1600<=570);
assert.equal(fitMapZoom(0,0,1400,1600),1,'hidden viewport avoids invalid zoom');
const compact=layout(graph,root,new Set());
for(const edge of compact.edges){const a=compact.positions.get(edge.from),b=compact.positions.get(edge.to);if(b.level===a.level+1)assert(b.x-a.x-240>=130,'leave room for arrows and service labels');}
for(const pos of compact.positions.values()){assert(pos.x>=0&&pos.y>=0);assert(pos.x+240<=compact.width);assert(pos.y+76<=compact.height);}
const broad=core.buildObservationGraph({columns:[report(1,'outside')],rows:Array.from({length:25},(_,i)=>row(`10.1.0.${i+1}`,1))},true);
const broadLayout=layout(broad,broad.reportSources.get(1),new Set());const byLevel=new Map();
for(const pos of broadLayout.positions.values()){const values=byLevel.get(pos.level)||[];values.push(pos.y);byLevel.set(pos.level,values);}
for(const values of byLevel.values()){values.sort((a,b)=>a-b);for(let i=1;i<values.length;i++)assert(values[i]-values[i-1]>=76,'cards never overlap');}
console.log('PASS: compact bounds, broad branch spacing, viewport fit and natural-scale cap');

// Run layout effects after refs are attached, with controllable ResizeObserver callbacks.
let viewSlots=[],effectSlots=[],pendingEffects=[],viewCursor=0;const observers=[];
const scrolls=[];const viewport={clientWidth:900,clientHeight:620,scrollTo(...args){scrolls.push(args);}};
const resizeHooks={
 useMemo:fn=>fn(),
 useState(initial){const i=viewCursor++;if(!(i in viewSlots))viewSlots[i]=typeof initial==='function'?initial():initial;return [viewSlots[i],v=>viewSlots[i]=typeof v==='function'?v(viewSlots[i]):v];},
 useRef(initial){const i=viewCursor++;if(!(i in viewSlots))viewSlots[i]={current:initial};return viewSlots[i];},
 useId:()=>':resize-test:',useEffect(){},
 useLayoutEffect(fn,deps){const i=viewCursor++;const prev=effectSlots[i];if(!prev||deps.some((value,j)=>!Object.is(value,prev.deps[j]))){pendingEffects.push(()=>{prev?.cleanup?.();effectSlots[i]={deps,cleanup:fn()};});}}
};
class FakeObserver {constructor(callback){this.callback=callback;this.active=true;observers.push(this);}observe(){}disconnect(){this.active=false;}}
const resizedComponent=load('components/VisibilityMap.tsx',name=>{
 if(name==='react')return resizeHooks;if(name==='react-router-dom')return {Link:'Link'};if(name==='lucide-react')return {};
 if(name.includes('svgExport'))return {};if(name.includes('mapExploration'))return exploration;if(name.includes('observedPaths'))return core;if(name.includes('networkMapLayout'))return layoutTools;throw Error(name);
},{React,ResizeObserver:FakeObserver});
source='1';let viewData=data;
function renderViewport(){viewCursor=0;const tree=resizedComponent.default({data:viewData,rows:viewData.rows,source,setSource:v=>source=v,onShowPath(){}});get(tree,n=>n.props['aria-label']==='Многоуровневая карта доступности').props.ref.current=viewport;const jobs=pendingEffects;pendingEffects=[];jobs.forEach(job=>job());return tree;}
const svgWidth=tree=>get(tree,n=>n.type==='svg').props.style.width;
let fitted=renderViewport();fitted=renderViewport();assert.equal(svgWidth(fitted),compact.width,'first opening uses readable 100%, not tiny auto-fit');
const initialScroll=scrolls[scrolls.length-1];assert.equal(initialScroll[1],Math.max(0,compact.positions.get(root).y-60),'root stays visible');
viewport.clientWidth=620;observers.filter(o=>o.active).forEach(o=>o.callback());fitted=renderViewport();assert.equal(svgWidth(fitted),compact.width,'resize does not shrink initial readable text');
get(fitted,n=>n.props['aria-label']==='Увеличить масштаб').props.onClick();fitted=renderViewport();const manualWidth=svgWidth(fitted);
viewport.clientWidth=480;observers.filter(o=>o.active).forEach(o=>o.callback());fitted=renderViewport();assert.equal(svgWidth(fitted),manualWidth,'manual zoom survives viewport changes');
get(fitted,n=>n.type==='button'&&text(n)==='Вместить в окно').props.onClick();fitted=renderViewport();fitted=renderViewport();assert(svgWidth(fitted)<=450,'overview still fits entire graph');
viewport.clientWidth=600;observers.filter(o=>o.active).forEach(o=>o.callback());fitted=renderViewport();assert(svgWidth(fitted)<=570,'explicit overview follows viewport resize');
const beforeCard=svgWidth(fitted),beforeScroll=scrolls.length;
get(fitted,n=>n.props['aria-label']==='Открыть устройство 10.0.0.3, HQ').props.onClick();fitted=renderViewport();
viewport.clientWidth=380;observers.filter(o=>o.active).forEach(o=>o.callback());fitted=renderViewport();assert.equal(svgWidth(fitted),beforeCard,'opening inspector preserves scale even after overview');assert.equal(scrolls.length,beforeScroll,'opening inspector does not move map');
get(fitted,n=>n.type==='select').props.onChange({target:{value:id('10.0.0.3')}});fitted=renderViewport();fitted=renderViewport();assert.equal(svgWidth(fitted),layout(graph,id('10.0.0.3'),new Set()).width,'new source returns to 100%');
viewData={columns:[report(1,'outside')],rows:Array.from({length:25},(_,i)=>row(`10.1.0.${i+1}`,1))};source='1';fitted=renderViewport();fitted=renderViewport();
const broadRoot=broad.reportSources.get(1);assert.equal(svgWidth(fitted),broadLayout.width,'broad graph keeps full text size');assert.equal(scrolls[scrolls.length-1][1],Math.max(0,broadLayout.positions.get(broadRoot).y-60),'tall graph starts around its root');
console.log('PASS: readable initial scale, visible root, explicit overview, manual zoom, stable inspector view and source reset');
