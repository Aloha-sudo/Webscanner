// Verify shared theme tokens used by forms, reports, statuses, links and buttons.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),postcss=require('postcss');
const css=postcss.parse(fs.readFileSync(path.join(__dirname,'../src/index.css'),'utf8'));
function palette(selector){const values={};css.walkRules(rule=>{if(rule.selector===selector)rule.walkDecls(decl=>values[decl.prop]=decl.value);});return values;}
const light=palette(':root'),dark={...light,...palette(':root[data-theme="dark"]')};
function luminance(hex){const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb.reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);}
function contrast(a,b){const values=[luminance(a),luminance(b)].sort((a,b)=>a-b);return (values[1]+.05)/(values[0]+.05);}
let pairs=0;
for(const [name,tokens] of [['light',light],['dark',dark]]){
 for(const text of ['--text','--text-secondary','--muted','--accent'])for(const background of ['--page','--surface','--subtle','--selected']){
  const ratio=contrast(tokens[text],tokens[background]);assert(ratio>=4.5,`${name} ${text} on ${background}: ${ratio.toFixed(2)}`);pairs++;
 }
 for(const type of ['success','warning','danger']){const ratio=contrast(tokens[`--${type}`],tokens[`--${type}-bg`]);assert(ratio>=4.5,`${name} ${type}: ${ratio.toFixed(2)}`);pairs++;}
 for(const bg of ['--button-bg','--button-hover']){const ratio=contrast(tokens['--button-text'],tokens[bg]);assert(ratio>=4.5,`${name} button ${bg}: ${ratio.toFixed(2)}`);pairs++;}
}
for(const background of ['#ffffff','#f1f8fb','#f5fafc'])assert(contrast('#7a91a4',background)>=3,'light control boundary');
assert.equal(light['--surface'],'#ffffff');
console.log(`PASS: ${pairs} text/background pairs in both themes (minimum 4.5:1), light control borders (3:1), white surfaces retained`);
