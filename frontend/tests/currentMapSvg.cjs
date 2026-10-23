// Attached SVG fixture with the same CSS text halo used by the network map.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),babel=require('@babel/core');
class Element {
 constructor(name,attrs={},style={}){this.localName=name;this.attrs={...attrs};this.computed=style;this.children=[];this.textContent='';this.parentElement=null;}
 setAttribute(k,v){this.attrs[k]=v;} removeAttribute(k){delete this.attrs[k];}
 appendChild(child){child.parentElement=this;this.children.push(child);return child;}
 insertBefore(child,before){child.parentElement=this;this.children.splice(this.children.indexOf(before),0,child);}
 get firstChild(){return this.children[0]||null;}
 querySelectorAll(){return this.children.flatMap(c=>[c,...c.querySelectorAll()]);}
 cloneNode(deep=false){const copy=new Element(this.localName,this.attrs);copy.textContent=this.textContent;if(deep)this.children.forEach(c=>copy.appendChild(c.cloneNode(true)));return copy;}
}
const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
function serialize(node,root=true){const attrs={...(root?{xmlns:'http://www.w3.org/2000/svg'}:{}),...node.attrs};return `<${node.localName}${Object.entries(attrs).map(([k,v])=>` ${k}="${escape(v)}"`).join('')}>${escape(node.textContent)}${node.children.map(c=>serialize(c,false)).join('')}</${node.localName}>`;}
const code=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/utils/svgExport.ts'),'utf8'),{filename:'svgExport.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
const box={exports:{},require:name=>name.includes('i18n/core')?require('./helpers/i18n.cjs'):{},Number,document:{createElementNS:(_,name)=>new Element(name)},getComputedStyle:node=>({color:node.computed.color||'#111827',backgroundColor:node.computed.backgroundColor||'rgba(0, 0, 0, 0)',getPropertyValue:key=>node.computed[key]||''}),XMLSerializer:class{serializeToString(node){return serialize(node);}},DOMParser:class{parseFromString(output){return {querySelector:()=>null};}}};
vm.runInNewContext(code,box);
for(const theme of ['light','dark']){
 const bg=theme==='light'?'#ffffff':'#101b30',fg=theme==='light'?'#111827':'#f1f5f9';
 const page=new Element('div',{}, {backgroundColor:bg});
 const svg=new Element('svg',{style:'width:400px;height:150px',xmlns:'http://www.w3.org/2000/svg'},{fill:'#000000',color:fg,'font-size':'14px'});
 svg.viewBox={baseVal:{x:10,y:20,width:800,height:300}};page.appendChild(svg);
 svg.appendChild(new Element('rect',{x:'40',y:'70',width:'240',height:'65',style:'cursor:pointer'},{fill:theme==='light'?'#f1f5f9':'#182c48',stroke:'#64748b','stroke-width':'1px',opacity:'1'}));
 const text=new Element('text',{x:'55',y:'100','font-size':'14',style:'cursor:pointer'}, {fill:fg,stroke:bg,'stroke-width':'3px','paint-order':'stroke fill','stroke-linejoin':'round','font-size':'14px','font-family':'Arial',opacity:'1'});text.textContent='192.0.2.1 & Host';svg.appendChild(text);
 svg.appendChild(new Element('path',{d:'M280 100 L400 100','marker-end':'url(#arrow)'},{fill:'none',stroke:'#64748b','stroke-width':'1.8px',opacity:'0.3'}));
 const output=box.exports.currentMapSvg(svg,'Project & LAN','Selected reports');
 assert.equal((output.match(/xmlns=/g)||[]).length,1);assert(output.includes('width="800"'));assert(output.includes('height="375"'));assert(output.includes('viewBox="10 -55 800 375"'));
 assert(!output.includes('style='));assert(!output.includes('var('));assert(output.includes('192.0.2.1 &amp; Host'));
 const label=output.match(/<text[^>]*>192\.0\.2\.1[^<]*<\/text>/)[0];
 assert(label.includes('stroke="none"'));assert(label.includes('stroke-width="0"'));assert(label.includes(`fill="${fg}"`));assert(label.includes('font-size="14px"'));
 assert(output.includes(`fill="${bg}" stroke="none"`),'opaque background matches the theme');assert(output.includes('marker-end="url(#arrow)"'));assert.equal(text.computed.stroke,bg,'live map is untouched');
 fs.writeFileSync(`/tmp/webscanner-current-${theme}.svg`,output);
}
console.log('PASS: current SVG text remains readable in both themes, one namespace, opaque background, unscaled canvas and preserved geometry');
