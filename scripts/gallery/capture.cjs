/* Real browser screenshots of WebScanner. Every API request is intercepted;
 * only synthetic fixtures are supplied and no backend mutation is permitted. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('playwright');
const fixture=require('./fixtures.json');
const baseURL=process.env.GALLERY_URL||'http://127.0.0.1:3000';
const output=path.resolve(process.env.GALLERY_OUTPUT||path.join(__dirname,'../../docs/images/gallery'));
const captureId=Date.now();
const stage=path.join(path.dirname(output),`.gallery-staging-${captureId}`);
const shots=[];const unexpected=[];const jsErrors=[];
const plans=[
 ['01-overview-dark','Scan overview','Обзор сканирования'],
 ['02-scan-results-dark','Scan details and host filters','Результаты скана и фильтры'],
 ['03-host-card-dark','Host card, DNS evidence and web metadata','Карточка хоста, DNS и веб-метаданные'],
 ['04-dns-settings-dark','Compact DNS lookup controls','Компактные настройки DNS'],
 ['05-screenshot-gallery-dark','Web-service screenshot gallery','Галерея скриншотов сервисов'],
 ['06-screenshot-viewer-dark','Full screenshot viewer','Просмотр скриншота'],
 ['07-comparison-dark','Before and after report comparison','Сравнение двух отчётов'],
 ['08-network-map-dark','Multilevel service reachability map','Многоуровневая карта'],
 ['09-neighborhood-dark','Incoming and outgoing host observations','Окружение хоста'],
 ['10-service-visibility-dark','Who observed this service?','Кто видит сервис?'],
 ['11-observation-path-dark','Directed observation path and evidence','Путь по наблюдениям и отчёты'],
 ['12-evidence-table-dark','Source-by-service evidence matrix','Матрица доступности'],
 ['13-project-description-dark','Project description and saved map','Описание проекта и сохранённая карта'],
 ['14-project-import-dark','Project archive import preview','Предпросмотр импорта проекта'],
];
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function serviceHtml(title,index){return `<!doctype html><meta charset="UTF-8"><style>*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#dce5f2;font:16px Arial}header{padding:28px 42px;background:#101c30;border-bottom:1px solid #27364b;display:flex;justify-content:space-between}main{padding:36px 42px}small{color:#91a5bf}h1{font-size:30px;margin:14px 0 8px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:30px 0}.card,section{padding:24px;background:#122137;border:1px solid #273e59;border-radius:12px}.metric{font-size:34px;margin:12px 0;color:#7dd3fc}.bar{height:12px;margin:18px 0;background:#263b55;border-radius:6px}.bar span{display:block;height:12px;background:#38bdf8;border-radius:6px}td{padding:16px;border-bottom:1px solid #253b53}table{border-collapse:collapse;width:100%;margin-top:18px}footer{padding:20px 42px;font-size:12px;color:#91a5bf}</style><header><strong>${esc(title)}</strong><small>DOCUMENTATION DEMO / 24-HOUR CLOCK</small></header><main><small>Demo workspace / Service ${index+1}</small><h1>${esc(title)}</h1><small>Constructed service content for WebScanner screenshots</small><div class="grid"><div class="card">Service status<div class="metric">Healthy</div><small>Synthetic fixture</small></div><div class="card">Last observation<div class="metric">09:30</div><small>UTC · demonstration only</small></div><div class="card">Environment<div class="metric">Demo</div><small>No production data</small></div></div><section><strong>Service overview</strong><div class="bar"><span style="width:${62+index*9}%"></span></div><table><tr><td>Endpoint</td><td>Available in this fixture</td><td>200 OK</td></tr><tr><td>DNS name</td><td>${['portal','monitoring','gateway'][index]}.example</td><td>Demo</td></tr></table></section></main><footer>Fictional page captured in a browser. Not a live organization or production service.</footer>`;}
async function serviceImages(browser){
 const context=await browser.newContext({viewport:{width:1200,height:720},colorScheme:'dark',locale:'en-GB',timezoneId:'UTC'});
 const page=await context.newPage();const result=new Map();
 for(const [index,title] of ['Documentation portal','Service monitoring','Access gateway'].entries()){
  await page.setContent(serviceHtml(title,index));await page.evaluate(()=>document.fonts.ready);
  result.set(1001+index,await page.screenshot({animations:'disabled',caret:'hide'}));
 }
 await context.close();return result;
}
function portProfiles(){return fixture.port_profiles;}
function speeds(){return fixture.speed_profiles;}
function createApi(images){return async route=>{
 const request=route.request(),url=new URL(request.url()),method=request.method(),endpoint=url.pathname.replace(/\/$/,'');
 if(url.origin!==new URL(baseURL).origin){unexpected.push(`${method} ${url.origin}${url.pathname}`);return route.abort();}
 if(endpoint!=='/api'&&!endpoint.startsWith('/api/'))return route.continue();
 const json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
 if(method==='GET'){
  if(endpoint==='/api/catalog')return json(fixture.catalog);
  if(endpoint==='/api/scans/speed-profiles')return json(speeds());
  if(endpoint==='/api/scans/port-profiles')return json(portProfiles());
  if(endpoint==='/api/scans'){
   const all=[...fixture.scans].sort((a,b)=>b.id-a.id),skip=Number(url.searchParams.get('skip')||0),limit=Number(url.searchParams.get('limit')||50);
   return json({scans:all.slice(skip,skip+limit),total:all.length});
  }
  if(endpoint==='/api/scans/visibility'){
   const ids=(url.searchParams.get('report_ids')||'').split(',').map(Number);
   if(ids.length===3&&ids.every(id=>[101,102,103].includes(id))){
    const data=structuredClone(fixture.visibility);data.columns=ids.map(id=>data.columns.find(c=>c.id===id));data.rows.forEach(row=>row.cells=ids.map(id=>row.cells.find(c=>c.report_id===id)));return json(data);
   }
  }
  if(endpoint==='/api/scans/compare'&&url.searchParams.get('before')==='201'&&url.searchParams.get('after')==='202')return json(fixture.comparison);
  if(endpoint===`/api/project-transfer/${fixture.project_id}/notes`)return json(fixture.notes);
  const scan=endpoint.match(/^\/api\/scans\/(\d+)$/);
  if(scan){const data=fixture.scans.find(item=>item.id===Number(scan[1]));if(data)return json(data);}
  const image=endpoint.match(/^\/api\/scans\/screenshots\/(\d+)\/image$/);
  if(image&&images.has(Number(image[1])))return route.fulfill({status:200,contentType:'image/png',body:images.get(Number(image[1]))});
 }
 if(method==='POST'&&endpoint==='/api/project-transfer/import'){
  const body=(request.postDataBuffer()||Buffer.alloc(0)).toString('latin1');
  if(/name="preview"\r?\n\r?\ntrue(?:\r?\n)/.test(body))return json(fixture.import_preview);
 }
 unexpected.push(`${method} ${endpoint}`);
 return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Gallery capture blocked an unrecognized request. No request reached the backend.'})});
};}
async function capture(){
 fs.mkdirSync(stage,{recursive:true});
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const images=await serviceImages(browser);
  const context=await browser.newContext({viewport:{width:1600,height:1050},deviceScaleFactor:1,colorScheme:'dark',locale:'en-GB',timezoneId:'UTC',reducedMotion:'reduce',serviceWorkers:'block'});
  await context.addInitScript(({projectId,partId})=>{try{localStorage.setItem('webscanner-theme','dark');localStorage.setItem('webscanner-language','en');localStorage.setItem('scanner-context',JSON.stringify({projectId,partId}));}catch{}},{projectId:fixture.project_id,partId:fixture.part_id});
  await context.route('**/*',createApi(images));
  const page=await context.newPage();page.on('pageerror',error=>jsErrors.push(error.message));page.setDefaultTimeout(20000);
  async function go(url){await page.goto(new URL(url,baseURL).href,{waitUntil:'domcontentloaded'});await page.locator('.reference-brand').waitFor();await page.getByLabel('Current project',{exact:true}).selectOption(String(fixture.project_id));await page.getByLabel('Current network segment',{exact:true}).selectOption(String(fixture.part_id));await page.evaluate(()=>document.fonts.ready);}
  async function shot(id,{locator,fullPage=false}={}){
   const plan=plans.find(item=>item[0]===id);if(!plan)throw Error('Unknown gallery scene');
   const theme=await page.locator('html').getAttribute('data-theme');if(theme!=='dark')throw Error('A gallery scene is not in dark mode');
   await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const file=id+'.png';await (locator||page).screenshot({path:path.join(stage,file),animations:'disabled',caret:'hide',...(locator?{}:{fullPage})});
   const bytes=fs.readFileSync(path.join(stage,file));if(bytes.length<1000)throw Error('Empty screenshot: '+id);
   shots.push({file,en:plan[1],ru:plan[2],bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')});console.log('Captured '+shots.length+'/'+plans.length+': '+plan[1]);
  }
  async function map({expanded=true}={}){
   await go('/team');
   for(const id of [201,202])await page.getByRole('checkbox',{name:`Select report ${id}`,exact:true}).uncheck();
   await page.getByRole('button',{name:'Build map',exact:true}).click();await page.locator('.network-map-workspace').waitFor();
   await page.locator('.network-map-workspace').scrollIntoViewIfNeeded();
   if(expanded){await page.locator('.network-map-actions').getByRole('button',{name:'Expand',exact:true}).click();await page.getByRole('button',{name:'Fit to window',exact:true}).click();}
  }
  await go('/');await page.getByLabel('Scan target',{exact:true}).fill('192.0.2.0/24');
  await page.locator('#new-scan-source').fill('192.0.2.10');
  await page.locator('.scan-history tbody tr').first().waitFor();await shot('01-overview-dark',{fullPage:true});
  await go('/scan/201?host_q=192.0.2.40');await page.locator('.scan-host-filters').waitFor();await shot('02-scan-results-dark',{fullPage:true});
  const card=page.locator('.ui-surface.rounded-xl').filter({hasText:'portal.example'});
  await card.locator('.host-dns-evidence > summary').click();await shot('03-host-card-dark',{locator:card});
  await page.locator('.scan-dns-control > summary').click();await page.getByLabel('DNS server for hostname lookup',{exact:true}).fill('192.0.2.53');await page.getByLabel('DNS transport for hostname lookup',{exact:true}).selectOption('tcp');await page.locator('.scan-dns-popover').scrollIntoViewIfNeeded();await shot('04-dns-settings-dark');
  await go('/scan/201');await page.getByRole('tab',{name:/^Screenshots/}).click();
  await page.locator('#scan-screenshots-panel img').first().waitFor();
  await page.locator('#scan-screenshots-panel img').evaluateAll(images=>Promise.all(images.map(image=>image.complete?Promise.resolve():new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;}))));
  await shot('05-screenshot-gallery-dark',{fullPage:true});
  await page.getByAltText('https://portal.example:443',{exact:true}).click();await page.locator('.screenshot-dialog').waitFor();await shot('06-screenshot-viewer-dark');
  await go('/reports');await page.getByLabel('First report',{exact:true}).selectOption('201');await page.getByLabel('Second report',{exact:true}).selectOption('202');await page.getByRole('button',{name:'Show differences',exact:true}).click();await page.getByRole('heading',{name:'Comparison results',exact:true}).waitFor();await shot('07-comparison-dark',{fullPage:true});
  await map();await shot('08-network-map-dark');
  await page.getByRole('button',{name:'Open device 192.0.2.30, Server segment',exact:true}).click();await page.getByRole('button',{name:'Show neighborhood',exact:true}).click();await shot('09-neighborhood-dark');
  await map();await page.getByRole('button',{name:'Open device 192.0.2.40, Server segment',exact:true}).click();await page.locator('.service-visibility-panel').getByRole('button',{name:'443/TCP',exact:true}).click();await page.getByLabel('Who can see this service?',{exact:true}).waitFor();await shot('10-service-visibility-dark');
  await map({expanded:false});await page.getByRole('button',{name:'Find path',exact:true}).click();const paths=page.locator('.observed-paths');
  const from=fixture.visibility.rows.find(row=>row.ip==='192.0.2.10').device_id;
  await paths.getByLabel('Scan source for path search',{exact:true}).selectOption(from);await paths.getByLabel('Target host',{exact:true}).fill('192.0.2.60');await paths.getByRole('button',{name:'Find path',exact:true}).click();await page.locator('.observed-path-evidence').waitFor();await shot('11-observation-path-dark',{fullPage:true});
  await map({expanded:false});await page.getByRole('button',{name:'Table',exact:true}).click();await page.locator('.visibility-table').waitFor();await shot('12-evidence-table-dark');
  await go('/team');await page.locator('.project-management > summary').click();await page.getByRole('button',{name:'Project description',exact:true}).click();await page.getByRole('dialog',{name:'Project description',exact:true}).waitFor();await shot('13-project-description-dark');
  await page.getByRole('button',{name:'Close: Project description',exact:true}).click();await page.getByRole('button',{name:'Import project',exact:true}).click();await page.getByLabel('Project archive',{exact:true}).setInputFiles(path.join(__dirname,'../../examples/demo-project.zip'));await page.getByRole('dialog',{name:'Import project',exact:true}).getByRole('button',{name:'Create project',exact:true}).waitFor({state:'visible'});await shot('14-project-import-dark');
  if(shots.length!==plans.length)throw Error('Incomplete gallery');
  if(unexpected.length)throw Error('Unexpected requests: '+unexpected.join(', '));if(jsErrors.length)throw Error('Browser errors: '+jsErrors.join('; '));
  const contact=await context.newPage();await contact.setContent(`<html><style>body{margin:0;background:#0b1220;color:#dce5f2;font:18px Arial;padding:30px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}figure{margin:0;background:#111e31;padding:12px;border:1px solid #283e57;border-radius:10px}img{width:100%;height:300px;object-fit:contain;background:#0b1220}figcaption{padding:12px 4px;font-size:17px}h1{font-size:28px}p{color:#94a8c3}</style><h1>WebScanner / Dark interface gallery</h1><p>Actual UI · synthetic API fixtures · all 14 scenes in dark mode</p><div class="grid">${shots.map((shot,index)=>`<figure><img src="data:image/png;base64,${fs.readFileSync(path.join(stage,shot.file)).toString('base64')}"><figcaption>${index+1}. ${esc(shot.en)}</figcaption></figure>`).join('')}</div></html>`);
  await contact.evaluate(()=>Promise.all([...document.images].map(image=>image.decode())));await contact.screenshot({path:path.join(stage,'contact-sheet-dark.png'),fullPage:true,animations:'disabled'});
  const manifest={captured_at:new Date().toISOString(),theme:'dark',language:'en',timezone:'UTC',viewport:{width:1600,height:1050},source:'Actual WebScanner frontend with synthetic intercepted API responses',backend_writes:0,unexpected_requests:unexpected,browser_errors:jsErrors,shots};
  fs.writeFileSync(path.join(stage,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  const backup=path.join(path.dirname(output),`.gallery-previous-${captureId}`);
  const existing=fs.existsSync(output);if(existing)fs.renameSync(output,backup);
  try{fs.renameSync(stage,output);}catch(error){if(existing)fs.renameSync(backup,output);throw error;}
  console.log('COMPLETE: 14 dark-mode screenshots and contact sheet. No backend data was changed.');await context.close();
 }finally{await browser.close();}
}
if(require.main===module)capture().catch(error=>{console.error('GALLERY FAILED: '+error.message);console.error('Existing published screenshots were kept; partial captures are in '+stage);process.exitCode=1;});
module.exports={plans,createApi,portProfiles,speeds};
