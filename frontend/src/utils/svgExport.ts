import { t, formatDateTime } from '../i18n/core';
import { buildObservationGraph, type ObservationData } from './observedPaths';
import { layoutNetworkMap } from './networkMapLayout';

export function downloadFile(content: BlobPart, filename: string, type: string) {
  const url=URL.createObjectURL(new Blob([content],{type}));
  const link=document.createElement('a');link.href=url;link.download=filename;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const escape=(value:unknown)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]!));

/** All components, including isolated devices, without collapse or UI filters. */
export function fullMapSvg(data:ObservationData,title:string):string {
  const graph=buildObservationGraph(data,true);const seen=new Set<string>();let offset=100,width=800;const shapes:string[]=[];
  const starts=[...Array.from(graph.nodes.values()).filter(n=>n.isSource).map(n=>n.id),...graph.nodes.keys()];
  const positions=new Map<string,{x:number;y:number}>();
  for(const root of starts){
    if(seen.has(root))continue;
    const remaining={...graph,nodes:new Map([...graph.nodes].filter(([id])=>!seen.has(id))),outgoing:new Map([...graph.outgoing].map(([id,edges])=>[id,edges.filter(e=>!seen.has(e.to))]))};
    const layout=layoutNetworkMap(remaining,root,new Set());
    for(const [id,p] of layout.positions){seen.add(id);positions.set(id,{x:p.x,y:p.y+offset});}
    offset+=layout.height+40;width=Math.max(width,layout.width+40);
  }
  for(const edges of graph.outgoing.values())for(const edge of edges){
    const a=positions.get(edge.from)!,b=positions.get(edge.to)!;
    const ports=[...new Set(edge.evidence.filter(e=>e.protocol!=='host').map(e=>`${e.port}/${e.protocol}`))];
    const evidence=[...new Set(edge.evidence.map(e=>`#${e.report.id}`))].join(', ');
    const forward=b.x>a.x;
    const d=forward?`M${a.x+240},${a.y+30} C${a.x+280},${a.y+30} ${b.x-40},${b.y+30} ${b.x},${b.y+30}`:`M${a.x+120},${a.y} C${a.x+120},${a.y-35} ${b.x+120},${b.y-35} ${b.x+120},${b.y}`;
    shapes.push(`<path d="${d}" fill="none" stroke="#64748b" stroke-dasharray="5 4" marker-end="url(#arrow)"><title>${escape(t("{v0} · отчёты {v1}", {
  v0: ports.join(', ') || t("Хост"),
  v1: evidence
}))}</title></path>`);
    if(forward)shapes.push(`<text x="${(a.x+240+b.x)/2}" y="${(a.y+b.y)/2+20}" text-anchor="middle" font-size="11">${escape(ports.length<=2?ports.join(' · '):t("{v0} портов", {
  v0: ports.length
}))}</text>`);
  }
  for(const [id,p] of positions){const node=graph.nodes.get(id)!;
    shapes.push(`<g><title>${escape(node.label+' · '+node.network)}</title><rect x="${p.x}" y="${p.y}" width="240" height="64" rx="8" fill="${node.isSource?'#dbeafe':'#f1f5f9'}" stroke="#64748b"/><text x="${p.x+10}" y="${p.y+24}" font-size="14">${escape(node.label.slice(0,29))}</text><text x="${p.x+10}" y="${p.y+46}" font-size="11">${escape(node.network.slice(0,28))}${node.isSource?t(" · источник"):''}</text></g>`);
  }
  const height=offset+data.columns.length*22+70;
  const reports=data.columns.map((c,i)=>`<text x="32" y="${offset+45+i*22}" font-size="12">${escape(`#${c.id} · ${c.source_host} · ${c.network} · ${c.observed_at?formatDateTime(c.observed_at):t("время неизвестно")} · ${c.author||''}`)}</text>`).join('');
  const summary=escape(t('Все выбранные отчёты · {v0} узлов · {v1}',{v0:graph.nodes.size,v1:data.merge_parts?t('Общая адресация'):t('Раздельная адресация')}));
  const legend=escape(t('Стрелки — наблюдения доступности, а не физические маршруты. Голубой узел — источник.'));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="Arial, sans-serif" fill="#0f172a"><rect width="100%" height="100%" fill="white"/><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#64748b"/></marker></defs><text x="32" y="30" font-size="20">${escape(title)}</text><text x="32" y="55" font-size="12">${summary}</text><text x="32" y="78" font-size="12">${legend}</text>${shapes.join('')}${reports}</svg>`;
}

/** Freeze SVG paint styles while the original is still attached to the page. */
export function currentMapSvg(svg:SVGSVGElement,title:string,metadata:string=''):string {
  const clone=svg.cloneNode(true) as SVGSVGElement;
  const originals=[svg,...Array.from(svg.querySelectorAll('*'))];
  const copies=[clone,...Array.from(clone.querySelectorAll('*'))];
  const properties=['fill','fill-opacity','stroke','stroke-opacity','stroke-width','stroke-dasharray','stroke-linecap','stroke-linejoin','paint-order','color','font-family','font-size','font-weight','text-anchor','dominant-baseline','opacity'];
  originals.forEach((node,i)=>{
    const style=getComputedStyle(node);
    for(const key of properties){
      const value=style.getPropertyValue(key);
      if(value)copies[i].setAttribute(key,value);
    }
    // Text halos in the map use paint-order: stroke fill. Losing that CSS rule
    // paints the thick background-coloured stroke over the small glyphs.
    if(node.localName==='text'){
      copies[i].setAttribute('stroke','none');
      copies[i].setAttribute('stroke-width','0');
      copies[i].setAttribute('paint-order','normal');
    }
    copies[i].removeAttribute('style');
    copies[i].removeAttribute('tabindex');
    copies[i].removeAttribute('role');
  });
  const box=svg.viewBox.baseVal;
  if(!Number.isFinite(box.width)||!Number.isFinite(box.height)||box.width<=0||box.height<=0)throw new Error(t("Не удалось определить размер карты"));
  const header=75;
  // XMLSerializer supplies the SVG namespace itself. A plain xmlns attribute
  // can duplicate that declaration in some serializers.
  clone.removeAttribute('xmlns');
  clone.setAttribute('width',String(box.width));
  clone.setAttribute('height',String(box.height+header));
  clone.setAttribute('viewBox',`${box.x} ${box.y-header} ${box.width} ${box.height+header}`);
  let ancestor:Element|null=svg;let backgroundColor='#ffffff';
  while(ancestor){
    const color=getComputedStyle(ancestor).backgroundColor;
    if(color&&color!=='transparent'&&color!=='rgba(0, 0, 0, 0)'){backgroundColor=color;break;}
    ancestor=ancestor.parentElement;
  }
  const description=document.createElementNS('http://www.w3.org/2000/svg','desc');description.textContent=metadata;clone.appendChild(description);
  const background=document.createElementNS('http://www.w3.org/2000/svg','rect');
  background.setAttribute('x',String(box.x));background.setAttribute('y',String(box.y-header));
  background.setAttribute('width',String(box.width));background.setAttribute('height',String(box.height+header));
  background.setAttribute('fill',backgroundColor);background.setAttribute('stroke','none');
  clone.insertBefore(background,clone.firstChild);
  const heading=document.createElementNS('http://www.w3.org/2000/svg','text');
  heading.setAttribute('x',String(box.x+16));heading.setAttribute('y',String(box.y-40));
  heading.setAttribute('fill',getComputedStyle(svg).color||'#0f172a');heading.setAttribute('stroke','none');
  heading.setAttribute('font-family','Arial, sans-serif');heading.setAttribute('font-size','16');
  heading.textContent=title;clone.appendChild(heading);
  const note=heading.cloneNode() as SVGTextElement;
  note.setAttribute('y',String(box.y-16));note.setAttribute('font-size','11');
  note.textContent=t("Текущий вид с фильтрами и свёрнутыми ветками. Связи — наблюдения доступности.");clone.appendChild(note);
  const output=new XMLSerializer().serializeToString(clone);
  const parsed=new DOMParser().parseFromString(output,'image/svg+xml');
  if(parsed.querySelector('parsererror'))throw new Error(t("Не удалось создать корректный SVG карты"));
  return output;
}
