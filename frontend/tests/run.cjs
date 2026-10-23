const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const directory=__dirname;
for(const name of fs.readdirSync(directory).filter(name=>name.endsWith('.cjs')&&name!=='run.cjs').sort()){
 const result=spawnSync(process.execPath,[path.join(directory,name)],{stdio:'inherit',cwd:path.resolve(directory,'../..')});
 if(result.error){console.error(result.error.message);process.exit(1);}
 if(result.status!==0)process.exit(result.status||1);
}
