const fs=require('fs'),path=require('path'),vm=require('vm'),babel=require('@babel/core');
const code=babel.transformSync(fs.readFileSync(path.join(__dirname,'../../src/i18n/core.ts'),'utf8'),{filename:'core.ts',presets:['@babel/preset-typescript'],plugins:['@babel/plugin-transform-modules-commonjs']}).code;
const values=new Map();const document={documentElement:{lang:'ru'}};
const box={exports:{},Intl,Date,document,localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},require:name=>name==='./api.en.json'?require('../../src/i18n/api.en.json'):require('../../src/i18n/en.json')};
vm.runInNewContext(code,box);module.exports=box.exports;
