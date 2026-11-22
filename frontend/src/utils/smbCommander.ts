export type SmbCommand={action:'list'|'preview'|'download'|'permissions'|'pwd'|'help';path?:string};
export function resolveSmbPath(current:string,argument:string):string {
  const value=argument.replace(/\\/g,'/');
  if(value.startsWith('//'))throw Error('path');
  const parts=value.startsWith('/')?[]:current.split('/').filter(Boolean);
  for(const part of value.split('/')){
    if(!part||part==='.')continue;
    if(part==='..'){if(!parts.length)throw Error('path');parts.pop();continue;}
    if(/[:*?\u0000-\u001f]/.test(part))throw Error('path');
    parts.push(part);
  }
  if(parts.length>64||parts.join('/').length>2048)throw Error('path');
  return parts.join('/');
}
export function parseSmbCommand(line:string,current:string,selected?:string):SmbCommand {
  const match=/^\s*(\S+)(?:\s+([\s\S]*))?$/.exec(line);
  if(!match)return {action:'help'};
  const command=match[1].toLowerCase();let argument=(match[2]||'').trim();
  if(argument.startsWith('"')||argument.startsWith("'")){
    if(argument.length<2||argument[argument.length-1]!==argument[0])throw Error('quote');
    argument=argument.slice(1,-1);
  }
  if(command==='help')return {action:'help'};
  if(command==='pwd')return {action:'pwd'};
  if(command==='ls')return {action:'list',path:argument?resolveSmbPath(current,argument):current};
  if(command==='cd')return {action:'list',path:argument?resolveSmbPath(current,argument):''};
  const actions={cat:'preview',get:'download',rights:'permissions'} as const;
  if(!Object.prototype.hasOwnProperty.call(actions,command))throw Error('command');
  const path=argument?resolveSmbPath(current,argument):selected;
  if(!path)throw Error('selection');
  return {action:actions[command as keyof typeof actions],path};
}
