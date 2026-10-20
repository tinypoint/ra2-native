'use strict';
// Mutable game files live separately from immutable download caches.
window.RA2UserFiles={async attach(FS,report=()=>{}){
 const database=await new Promise((resolve,reject)=>{
  const r=indexedDB.open('ra2-web-user-files',1);
  r.onupgradeneeded=()=>r.result.createObjectStore('files',{keyPath:'path'});
  r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
 });
 const rows=await new Promise((resolve,reject)=>{
  const r=database.transaction('files').objectStore('files').getAll();
  r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
 });
 const normalize=p=>{if(typeof p!=='string')return null;const parts=(p.startsWith('/')?p:FS.cwd()+'/'+p).split('/'),out=[];for(const x of parts){if(x==='..')out.pop();else if(x&&x!=='.')out.push(x);}const path='/'+out.join('/');return path.startsWith('/game/')?path:null;};
 for(const row of rows){
  const path=normalize(row.path);if(!path)continue;
  if(row.deleted){try{FS.unlink(path);}catch(e){if(e.errno!==44)throw e;}}
  else{FS.mkdirTree(path.slice(0,path.lastIndexOf('/')));FS.writeFile(path,new Uint8Array(row.bytes));}
 }
 report('已恢复 '+rows.filter(r=>!r.deleted).length+' 个设置／存档文件');
 const dirty=new Set();let timer=0,saving=false,disposed=false;
 const pathOf=value=>typeof value==='string'?normalize(value):value?.node?normalize(FS.getPath(value.node)):value?normalize(FS.getPath(value)):null;
 function schedule(){if(!disposed){clearTimeout(timer);timer=setTimeout(flush,100);}}
 function mark(value){const path=pathOf(value);if(path){dirty.add(path);schedule();}}
 function isWriting(path){return FS.streams.some(s=>s&&s.fd!==null&&(s.flags&3)!==0&&pathOf(s)===path);}
 async function flush(){
  if(saving||disposed)return;
  const batch=[];
  try{
   for(const path of dirty){
    if(isWriting(path))continue; // Never persist a partially written save.
    try{const st=FS.stat(path);if(FS.isDir(st.mode)){dirty.delete(path);continue;}batch.push({path,bytes:FS.readFile(path),deleted:false});}
    catch(e){if(e.errno!==44)throw e;batch.push({path,deleted:true});}
   }
   if(!batch.length)return;
   saving=true;for(const row of batch)dirty.delete(row.path);
   await new Promise((resolve,reject)=>{
    const tx=database.transaction('files','readwrite');tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('本地保存中断'));
    for(const row of batch)tx.objectStore('files').put(row);
   });
   report('设置／存档已保存在此浏览器 · '+new Date().toLocaleTimeString());
  }catch(e){for(const row of batch)dirty.add(row.path);report('本地保存失败：'+(e?.message||String(e))+'。请暂时不要刷新。',true);}
  finally{saving=false;if(dirty.size&&!disposed){clearTimeout(timer);timer=setTimeout(flush,2000);}}
 }
 function wrap(name,after){const original=FS[name];FS[name]=function(...args){const result=original.apply(this,args);after(args,result);return result;};}
 const open=FS.open;
 FS.open=function(path,...args){let existed=true;try{if(typeof path==='string')FS.stat(path);}catch(e){if(e.errno===44)existed=false;else throw e;}const stream=open.call(this,path,...args);if(!existed&&(stream.flags&3)!==0)mark(stream);return stream;};
 wrap('write',([stream])=>mark(stream));
 wrap('truncate',([path])=>mark(path));
 const close=FS.close;
 FS.close=function(stream){const path=pathOf(stream);const result=close(stream);if(dirty.has(path))schedule();return result;};
 wrap('rename',([oldpath,newpath])=>{mark(oldpath);mark(newpath);});
 wrap('unlink',([path])=>mark(path));
 document.addEventListener('visibilitychange',()=>{if(document.hidden)void flush();});
 window.addEventListener('pagehide',()=>{void flush();});
 database.onversionchange=()=>{disposed=true;database.close();report('本地存储已变更，请刷新页面。',true);};
 return {flush};
}};
