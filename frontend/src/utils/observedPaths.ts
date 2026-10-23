/** Directed service observations, never a claim of usable transit or physical routing. */
export type ObservationCell = {report_id:number;state:string;service:string|null;version?:string|null};
export type ObservationRow = {device_id:string;network:string;ip:string;hostname:string|null;protocol:string;port:number;cells:ObservationCell[]};
export type ObservationColumn = {id:number;network:string;network_part_id?:number|null;source_host:string;author:string|null;observed_at:string|null};
export type ObservationData = {columns:ObservationColumn[];rows:ObservationRow[];merge_parts?:boolean};
export type PathNode = {id:string;label:string;network:string;ip?:string;isSource:boolean;matched:boolean};
export type PathEvidence = {report:ObservationColumn;port:number;protocol:string;service:string|null};
export type PathEdge = {from:string;to:string;evidence:PathEvidence[]};
export type ObservationGraph = {nodes:Map<string,PathNode>;outgoing:Map<string,PathEdge[]>;unmatchedSources:string[];reportSources:Map<number,string>};

function sourceAddress(label:string):string|null {
  // Accept an IP by itself or followed by a human label; never guess from arbitrary text.
  const match=label.trim().match(/^(\d{1,3}(?:\.\d{1,3}){3})(?=$|\s|[·(])/);
  return match&&match[1].split('.').every(p=>Number(p)<=255)?match[1]:null;
}
function partOfDevice(id:string):unknown {try{return JSON.parse(id)[0];}catch{return undefined;}}

export function buildObservationGraph(data:ObservationData, includeHostObservations=false):ObservationGraph {
  const nodes=new Map<string,PathNode>();
  const hosts=new Map<string,Set<string>>();
  for(const row of data.rows){
    if(!nodes.has(row.device_id))nodes.set(row.device_id,{id:row.device_id,label:row.ip,ip:row.ip,network:row.network,isSource:false,matched:true});
    if(row.hostname){const values=hosts.get(row.device_id)||new Set<string>();values.add(row.hostname.toLowerCase());hosts.set(row.device_id,values);}
  }
  const reportSources=new Map<number,string>();const unmatchedSources:string[]=[];
  for(const column of data.columns){
    const label=column.source_host.trim();const address=sourceAddress(label);
    const part=data.merge_parts?null:(column.network_part_id||column.network);
    const matches=Array.from(nodes.values()).filter(node=>node.ip&&partOfDevice(node.id)===part&&
      (address?node.ip===address:hosts.get(node.id)?.has(label.toLowerCase())));
    let id:string;
    if(matches.length===1){id=matches[0].id;nodes.get(id)!.isSource=true;}
    else {
      id=JSON.stringify(['source',part,address||label.toLowerCase()]);
      if(!nodes.has(id)){
        nodes.set(id,{id,label,network:column.network,isSource:true,matched:false});
        unmatchedSources.push(label);
      }
    }
    reportSources.set(column.id,id);
  }
  const edges=new Map<string,PathEdge>();
  for(const row of data.rows){
    if(row.protocol==='host'&&!includeHostObservations)continue;
    for(const cell of row.cells){
      if(cell.state!=='found')continue;
      const from=reportSources.get(cell.report_id);if(!from||from===row.device_id)continue;
      const report=data.columns.find(c=>c.id===cell.report_id);if(!report)continue;
      const key=JSON.stringify([from,row.device_id]);
      let edge=edges.get(key);if(!edge){edge={from,to:row.device_id,evidence:[]};edges.set(key,edge);}
      edge.evidence.push({report,port:row.port,protocol:row.protocol,service:cell.service});
    }
  }
  const outgoing=new Map<string,PathEdge[]>();
  for(const edge of edges.values()){const list=outgoing.get(edge.from)||[];list.push(edge);outgoing.set(edge.from,list);}
  return {nodes,outgoing,unmatchedSources,reportSources};
}

/** BFS finds one shortest chain by number of observations; cycles are safe. */
export function shortestObservedPath(graph:ObservationGraph,from:string,to:string):PathEdge[]|null {
  if(!graph.nodes.has(from)||!graph.nodes.has(to))return null;
  if(from===to)return [];
  const previous=new Map<string,PathEdge>();const visited=new Set([from]);const queue=[from];
  for(let i=0;i<queue.length;i++){
    for(const edge of graph.outgoing.get(queue[i])||[]){
      if(visited.has(edge.to))continue;
      visited.add(edge.to);previous.set(edge.to,edge);
      if(edge.to===to){const path:PathEdge[]=[];let current=to;while(current!==from){const step=previous.get(current)!;path.push(step);current=step.from;}return path.reverse();}
      queue.push(edge.to);
    }
  }
  return null;
}

/** Prefer the source covering most of the selected evidence, rather than the newest report. */
export function initialSourceReport(data:ObservationData):number|undefined {
  const graph=buildObservationGraph(data,true);
  const sources=Array.from(new Set(graph.reportSources.values()));
  let best=sources[0];let bestSources=-1;let bestNodes=-1;
  for(const source of sources){
    const seen=new Set([source]);const queue=[source];
    for(let i=0;i<queue.length;i++)for(const edge of graph.outgoing.get(queue[i])||[]){
      if(!seen.has(edge.to)){seen.add(edge.to);queue.push(edge.to);}
    }
    const covered=sources.filter(id=>seen.has(id)).length;
    if(covered>bestSources||(covered===bestSources&&seen.size>bestNodes)){
      best=source;bestSources=covered;bestNodes=seen.size;
    }
  }
  return data.columns.find(report=>graph.reportSources.get(report.id)===best)?.id;
}
