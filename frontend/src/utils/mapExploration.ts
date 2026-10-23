import type { ObservationGraph, PathEdge } from './observedPaths';
import type { MapLayout } from './networkMapLayout';
import { MAP_LEVEL_GAP } from './networkMapLayout';

export const edgeHasService=(edge:PathEdge,key:string)=>edge.evidence.some(item=>`${item.protocol}/${item.port}`===key);
export const edgeHasAnyService=(edge:PathEdge,keys:ReadonlySet<string>)=>edge.evidence.some(item=>keys.has(`${item.protocol}/${item.port}`));

export function mapServiceOptions(graph:ObservationGraph):{key:string;label:string}[]{
  const services=new Map<string,Set<string>>();
  for(const edges of graph.outgoing.values())for(const edge of edges)for(const item of edge.evidence){
    if(item.protocol==='host')continue;
    const key=`${item.protocol}/${item.port}`;
    const names=services.get(key)||new Set<string>();
    if(item.service)names.add(item.service);
    services.set(key,names);
  }
  return Array.from(services,([key,names])=>({key,label:`${key.split('/')[1]}/${key.split('/')[0].toUpperCase()}${names.size?' · '+Array.from(names).join(', '):''}`}))
    .sort((a,b)=>Number(a.key.split('/')[1])-Number(b.key.split('/')[1])||a.key.localeCompare(b.key));
}

/** One-hop observations only: shared incoming/outgoing neighbors remain a single node. */
export function layoutHostNeighborhood(graph:ObservationGraph,target:string):MapLayout{
  if(!graph.nodes.has(target))return {positions:new Map(),edges:[],width:360,height:240,levels:1};
  const edges=Array.from(graph.outgoing.values()).flat().filter(edge=>edge.from===target||edge.to===target);
  const incoming=Array.from(new Set(edges.filter(edge=>edge.to===target).map(edge=>edge.from)));
  const left=new Set(incoming);
  const outgoing=Array.from(new Set(edges.filter(edge=>edge.from===target&&!left.has(edge.to)).map(edge=>edge.to)));
  const height=Math.max(240,Math.max(incoming.length,outgoing.length)*96+100);
  const positions:MapLayout['positions']=new Map();
  incoming.forEach((id,i)=>positions.set(id,{id,level:0,x:32,y:52+i*96}));
  positions.set(target,{id:target,level:1,x:32+MAP_LEVEL_GAP,y:height/2-38});
  outgoing.forEach((id,i)=>positions.set(id,{id,level:2,x:32+MAP_LEVEL_GAP*2,y:52+i*96}));
  return {positions,edges,width:MAP_LEVEL_GAP*2+304,height,levels:3};
}

/** Retain actual connecting observations for orientation; never label them as matches. */
export function filterMapServices(layout:MapLayout,anchor:string,keys:string|readonly string[]):MapLayout{
  const selected=new Set(typeof keys==='string'?(keys?[keys]:[]):keys);
  if(!selected.size)return layout;
  const matches=layout.edges.filter(edge=>edgeHasAnyService(edge,selected));
  const nodes=new Set<string>(layout.positions.has(anchor)?[anchor]:[]);
  const keep=new Set<PathEdge>(matches);
  const previous=new Map<string,PathEdge>();
  const outgoing=new Map<string,PathEdge[]>();
  for(const edge of layout.edges){const items=outgoing.get(edge.from)||[];items.push(edge);outgoing.set(edge.from,items);}
  const visited=new Set([anchor]),queue=[anchor];
  for(let i=0;i<queue.length;i++)for(const edge of outgoing.get(queue[i])||[]){
    if(visited.has(edge.to))continue;
    visited.add(edge.to);previous.set(edge.to,edge);queue.push(edge.to);
  }
  const traced=new Set<string>();
  const addPath=(node:string)=>{
    nodes.add(node);
    while(previous.has(node)&&!traced.has(node)){
      traced.add(node);
      const edge=previous.get(node)!;keep.add(edge);nodes.add(edge.from);node=edge.from;
    }
  };
  for(const edge of matches){addPath(edge.from);addPath(edge.to);}
  return {...layout,positions:new Map(Array.from(layout.positions).filter(([id])=>nodes.has(id))),edges:layout.edges.filter(edge=>keep.has(edge))};
}
