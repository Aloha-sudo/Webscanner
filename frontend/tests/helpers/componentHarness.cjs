const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),babel=require('@babel/core');
const base=path.join(__dirname,'../../src');
const React={createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(v=>v!==null&&v!==undefined&&v!==false)};}};
const elements=n=>n&&typeof n==='object'?[n,...n.children.flatMap(elements)]:[];
const text=n=>n&&typeof n==='object'?n.children.map(text).join(''):String(n??'');
const get=(tree,predicate)=>{const found=elements(tree).find(predicate);assert(found,'element not found');return found;};
function createHarness(filename,dependencies,globals={}){
 let slots=[],cursor=0,pending=[];
 const hooks={
 useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},
 useRef(initial){const i=cursor++;if(!(i in slots))slots[i]={current:initial};return slots[i];},
 useId:()=>':test-dialog:',
 useEffect(callback,deps){const i=cursor++;const previous=slots[i];if(!previous||deps.some((d,j)=>!Object.is(d,previous.deps[j])))pending.push(()=>{previous?.cleanup?.();slots[i]={deps,cleanup:callback()};});}
 };
 const code=babel.transformSync(fs.readFileSync(path.join(base,filename),'utf8'),{filename,presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-react-jsx','@babel/plugin-transform-modules-commonjs']}).code;
 const sandbox={exports:{},React,console,...globals,require(name){if(name.includes('i18n/core'))return require('./i18n.cjs');if(name==='react')return hooks;if(name==='lucide-react')return new Proxy({},{get:(_,key)=>String(key)});return dependencies(name);}};
 vm.runInNewContext(code,sandbox);
 return {render(props={}){cursor=0;return sandbox.exports.default(props);},effects(){const jobs=pending;pending=[];jobs.forEach(fn=>fn());}};
}
module.exports={createHarness,elements,text,get,tick:()=>new Promise(resolve=>setImmediate(resolve))};
