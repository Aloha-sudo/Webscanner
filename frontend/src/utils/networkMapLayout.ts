import type { ObservationGraph, PathEdge } from './observedPaths';
export type MapPosition = {id:string;level:number;x:number;y:number};
export type MapLayout = {positions:Map<string,MapPosition>;edges:PathEdge[];width:number;height:number;levels:number};

export const MAP_LEVEL_GAP=370;

/** One node per device. Collapse stops traversal, but shared descendants remain reachable elsewhere. */
export function layoutNetworkMap(graph:ObservationGraph,root:string,collapsed:Set<string>):MapLayout {
  const levels=new Map<string,number>();const queue:string[]=[];
  if(graph.nodes.has(root)){levels.set(root,0);queue.push(root);}
  for(let i=0;i<queue.length;i++){
    const id=queue[i];if(collapsed.has(id))continue;
    for(const edge of graph.outgoing.get(id)||[]){
      if(levels.has(edge.to))continue;
      levels.set(edge.to,levels.get(id)!+1);queue.push(edge.to);
    }
  }
  const layers:string[][]=[];
  for(const [id,level] of levels){if(!layers[level])layers[level]=[];layers[level].push(id);}
  const height=Math.max(240,...layers.map(items=>items.length*96+80));
  const positions=new Map<string,MapPosition>();
  layers.forEach((items,level)=>items.forEach((id,i)=>positions.set(id,{id,level,x:32+level*MAP_LEVEL_GAP,y:52+(i+.5)*(height-80)/items.length-38})));
  const edges:Array<PathEdge>=[];
  for(const id of levels.keys()){
    if(collapsed.has(id))continue;
    for(const edge of graph.outgoing.get(id)||[])if(levels.has(edge.to))edges.push(edge);
  }
  return {positions,edges,width:Math.max(360,(layers.length-1)*MAP_LEVEL_GAP+304),height,levels:layers.length};
}

/** Leave a small gutter, keep a natural scale for small graphs, ignore hidden viewports. */
export function fitMapZoom(viewWidth:number,viewHeight:number,mapWidth:number,mapHeight:number):number {
  if(viewWidth<=30||viewHeight<=30||mapWidth<=0||mapHeight<=0)return 1;
  return Math.max(.001,Math.min((viewWidth-30)/mapWidth,(viewHeight-30)/mapHeight,1));
}
