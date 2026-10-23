const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),vm=require('vm'),babel=require('@babel/core'),traverse=require('@babel/traverse').default;
const i18n=require('./helpers/i18n.cjs');
const {createHarness,elements,get,text,tick}=require('./helpers/componentHarness.cjs');
const catalog=require('../src/i18n/en.json');
for(const [source,english] of Object.entries(catalog)){
 assert(!/[А-Яа-яЁё]/.test(english),`English contains Russian: ${source}`);
 assert.deepEqual((source.match(/\{v\d+\}/g)||[]).sort(),(english.match(/\{v\d+\}/g)||[]).sort(),`Parameters differ: ${source}`);
}
function audit(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,entry.name);if(entry.isDirectory()){if(entry.name!=='i18n')audit(file);continue;}if(!/\.tsx?$/.test(file))continue;const ast=babel.parseSync(fs.readFileSync(file,'utf8'),{filename:file,presets:['@babel/preset-typescript']});traverse(ast,{CallExpression(p){if(p.node.callee.name==='t'&&p.node.arguments[0]?.type==='StringLiteral'){const key=p.node.arguments[0].value;assert(key in catalog,`Missing translation in ${file}: ${key}`);}const callee=p.node.callee;if(callee.type==='MemberExpression')assert(!['toLocaleString','toLocaleDateString'].includes(callee.property.name),`Date formatting bypasses the 24-hour formatter: ${file}`);}});}}
audit(path.join(__dirname,'../src'));
const originalEnv=process.env.TZ;process.env.TZ='UTC';
for(const language of ['ru','en']){
 i18n.setLanguage(language);
 for(const [iso,time] of [['2026-10-23T00:05:00Z','00:05'],['2026-10-23T09:30:00Z','09:30'],['2026-10-23T18:45:00Z','18:45'],['2026-10-23T23:59:00Z','23:59']]){
  const output=i18n.formatDateTime(iso);assert(output.includes(time),output);assert(!/\b(?:am|pm)\b/i.test(output),output);
 }
 assert.equal(i18n.formatDateTime('invalid'),'—');
}
if(originalEnv===undefined)delete process.env.TZ;else process.env.TZ=originalEnv;
assert.equal(i18n.hostCount(1),'1 host');assert.equal(i18n.hostCount(2),'2 hosts');
i18n.setLanguage('ru');assert.equal(i18n.hostCount(21),'21 хост');assert.equal(i18n.hostCount(12),'12 хостов');assert.equal(i18n.hostCount(22),'22 хоста');
let changes=0;const unsub=i18n.subscribeLanguage(()=>changes++);i18n.setLanguage('en');assert.equal(changes,1);unsub();
assert.equal(i18n.t('Сохранить'),'Save');
assert.equal(i18n.t('Отчёт #{v0}',{v0:'Русское название {v1}'}),'Report #Русское название {v1}','parameters stay unchanged and are not recursively interpolated');
const apiCode=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/i18n/api.ts'),'utf8'),{filename:'api.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
const apiBox={exports:{},require:name=>name==='./core'?i18n:name==='./api.en.json'?require('../src/i18n/api.en.json'):{}};vm.runInNewContext(apiCode,apiBox);
assert.equal(apiBox.exports.apiText('Некорректное имя хоста: Сервер'),'Invalid hostname: Сервер');
const data={comment:'Сохранить',project:'Проект',hosts:[{hostname:'Не указан'}],error_message:'Проект не найден',warnings:['Одинаковые IP между частями объединены по вашему выбору.']};apiBox.exports.localizeDiagnostics(data);assert.equal(data.comment,'Сохранить');assert.equal(data.project,'Проект');assert.equal(data.hosts[0].hostname,'Не указан');assert.equal(data.error_message,'Project not found');assert(!/[А-Яа-яЁё]/.test(data.warnings[0]));
// Static module label maps must react to language changes too.
const scan={id:1,status:'completed',dns_status:'not_requested',hosts:[{ip:'192.0.2.1',ports:[]}],dns_options:null};
const dns=createHarness('components/DnsResults.tsx',name=>name==='axios'?{__esModule:true,default:{isAxiosError:()=>false}}:{});
let tree=dns.render({scan,onQueued(){}});assert(text(tree).includes('Hostnames'));assert(text(tree).includes('Resolve names'));
get(tree,n=>n.props['aria-label']==='DNS server for hostname lookup').props.onChange({target:{value:'192.0.2.53'}});
i18n.setLanguage('ru');tree=dns.render({scan,onQueued(){}});assert(text(tree).includes('Имена хостов'));assert.equal(get(tree,n=>n.props['aria-label']==='DNS-сервер для имён').props.value,'192.0.2.53','switching preserves form values');
i18n.setLanguage('en');tree=dns.render({scan:{...scan,dns_status:'completed',dns_summary:{counts:{no_record:1}}},onQueued(){}});assert(text(tree).includes('No PTR record'),'module-level labels follow language changes');
i18n.setLanguage('ru');console.log('PASS: translation coverage and placeholders, 24-hour time at midnight/noon/evening, persistence notifications, plural forms, diagnostics and user-data isolation, live language switch without form reset');

// The editing control also stays 24-hour on systems whose native time widget uses AM/PM.
const timeCode=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/utils/localDateTime.ts'),'utf8'),{filename:'localDateTime.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
const timeBox={exports:{}};vm.runInNewContext(timeCode,timeBox);
for(const value of ['','2026-10-23T00:00','2026-10-23T18:45','2026-10-23T23:59'])assert(timeBox.exports.validLocalDateTime(value),value);
for(const value of ['2026-10-23T24:00','2026-10-23T12:60','2026-10-23T06:00 PM','2026-10-23T9:3'])assert(!timeBox.exports.validLocalDateTime(value),value);
let entered='2026-10-23T18:45';const timeInput=createHarness('components/LocalDateTimeInput.tsx',name=>name.includes('localDateTime')?timeBox.exports:{});
let control=timeInput.render({value:entered,label:'Report time',onChange:v=>entered=v});
assert(!elements(control).some(n=>n.props.type==='time'||n.props.type==='datetime-local'));
get(control,n=>n.props.type==='text').props.onChange({target:{value:'23:59'}});assert.equal(entered,'2026-10-23T23:59');
const originalLabel='Мой проект';
i18n.setLanguage('en');assert.equal(i18n.uiText('Проект «Мой проект» импортирован. Выберите часть сети или просмотр всего проекта.'),'Project “Мой проект” imported. Select a network segment or the whole-project view.');
i18n.setLanguage('ru');assert.equal(i18n.uiText('Project “Мой проект” imported. Select a network segment or the whole-project view.'),'Проект «Мой проект» импортирован. Выберите часть сети или просмотр всего проекта.');
console.log('PASS: explicit 24-hour editing, invalid time rejection and existing messages switch language without translating project names');

let requestInterceptor,responseInterceptor;
apiBox.exports.installLocaleInterceptors({interceptors:{request:{use:fn=>requestInterceptor=fn},response:{use:fn=>responseInterceptor=fn}}});
let header;
i18n.setLanguage('en');requestInterceptor({headers:{set:(name,value)=>header=[name,value]}});assert.deepEqual(header,['Accept-Language','en']);
i18n.setLanguage('ru');requestInterceptor({headers:{set:(name,value)=>header=[name,value]}});assert.deepEqual(header,['Accept-Language','ru']);
const settingsCode=babel.transformSync(fs.readFileSync(path.join(__dirname,'../src/i18n/core.ts'),'utf8'),{filename:'core.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
let savedLanguage='en';const langDoc={documentElement:{lang:''}};
const settingsBox={exports:{},Intl,Date,document:langDoc,localStorage:{getItem:()=>savedLanguage,setItem:(key,value)=>savedLanguage=value},require:name=>name.includes('api.en')?require('../src/i18n/api.en.json'):catalog};vm.runInNewContext(settingsCode,settingsBox);
assert.equal(settingsBox.exports.getLanguage(),'en');assert.equal(langDoc.documentElement.lang,'en-GB');settingsBox.exports.setLanguage('ru');assert.equal(savedLanguage,'ru');assert.equal(langDoc.documentElement.lang,'ru');
assert.deepEqual(require('../src/i18n/api.en.json'),JSON.parse(fs.readFileSync(path.join(__dirname,'../../backend/app/core/api.en.json'),'utf8')),'frontend and backend diagnostics catalogs agree');
console.log('PASS: stored language initializes correctly, changes persist, API headers follow the current language and diagnostic catalogs agree');
