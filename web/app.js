'use strict';
const gameView=document.body.dataset.view==='game',optionalUI=new Map();
const $=id=>{
 const element=document.getElementById(id);if(element)return element;
 if(!optionalUI.has(id)){
  const node=document.createElement(id==='progress'?'progress':id==='pack'?'input':id==='diagnostics'?'pre':'div');
  if(id==='diagnostics'){const details=document.createElement('details');details.append(node);}
  if(id==='pack')node.type='file';optionalUI.set(id,node);
 }
 return optionalUI.get(id);
},canvas=$('canvas');
let manifest,db,game,right=false,running=false,loading=false,networkBytes=0,startedAt=0;
let transferStarted=0,transferMilliseconds=0,speedSamples=[];
let importing=false,pendingReload=false,gameMemory=null;
const settings=$('game-settings');
function openSettings(){
 resetTouchInput();
 if(game)for(const vk of physicalHeld)game._ra2_web_key(0,vk,0);
 physicalHeld.clear();
 if(!settings.open)settings.showModal();
 document.body.classList.add('settings-open');
}
function closeSettings(){if(location.hash==='#settings')history.replaceState(null,'',location.pathname+location.search);if(settings.open)settings.close();}
$('settings-open').onclick=openSettings;
$('settings-close').onclick=closeSettings;
settings.addEventListener('close',()=>{document.body.classList.remove('settings-open');if(location.hash==='#settings')history.replaceState(null,'',location.pathname+location.search);if(running)canvas.focus({preventScroll:true});});
settings.addEventListener('click',e=>{if(e.target!==settings)return;const r=settings.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeSettings();});
const CHUNK=16*1024*1024;
const size=n=>n>=1048576?(n/1048576).toFixed(1)+' MiB':Math.ceil(n/1024)+' KiB';
const log=text=>{const el=$('diagnostics');el.textContent=(el.textContent+String(text)+'\n').slice(-32000);};
function sendDiagnostics(report){
 if(manifest?.diagnostics===false)return;
 fetch('diagnostics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(report),keepalive:true}).catch(()=>{});
}
const status=text=>{
 $('status').textContent=text;
 if(gameView){const notice=document.getElementById('game-error');notice.textContent=text;notice.hidden=!/^(游戏运行出错|游戏停止|启动失败|无法准备游戏|游戏程序暂不可用|请通过 HTTPS|当前浏览器缺少)/.test(text);}
};
async function showProgramVersion(){
 const file=manifest.artifacts['ra2-web.wasm'],version=manifest.programUpdate?.version;
 const installed=(await get(file.sha256+':meta'))?.size===file.size;
 $('version').textContent=(version?'程序 v'+version:'程序开发版')+' · '+(installed?'本机已缓存':'本机尚未安装当前版本');
}
function describeError(value,seen=new Set()){
 if(value==null||seen.has(value))return '';if(typeof value==='string')return value==='[object ErrorEvent]'?'':value;
 if(typeof value!=='object')return String(value);seen.add(value);
 return describeError(value.error,seen)||describeError(value.reason,seen)||value.stack||(value.message&&value.message!=='[object ErrorEvent]'?value.message:'')||(value.filename?'线程异常：'+value.filename+':'+(value.lineno||0):'');
}
function reportRuntimeError(value,kind='browser'){
 const error=describeError(value)||'浏览器线程退出，未提供具体错误信息';
 const report={kind,error:String(error).slice(0,2000),stage:stageText,logs:$('diagnostics').textContent.slice(-6000)};
 log(error);status('游戏运行出错：'+String(error).split('\n')[0]);running=false;loading=false;document.body.classList.remove('game-active','game-shell');
 $('start').textContent='重新启动游戏';$('start').disabled=false;$('import').disabled=false;$('diagnostics').closest('details').open=true;openSettings();
 try{localStorage.setItem('ra2-last-error',JSON.stringify(report));localStorage.setItem('ra2-launch-pending','1');}catch{}
 sendDiagnostics(report);
}
const request=req=>new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('无法读取本地缓存'));});
const done=tx=>new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error||new Error('浏览器本地存储写入失败'));tx.onabort=()=>reject(tx.error||new Error('缓存写入中止'));});
async function database(){const req=indexedDB.open('ra2-web-resources',1);req.onupgradeneeded=()=>req.result.createObjectStore('resources');return request(req);}
const get=key=>request(db.transaction('resources').objectStore('resources').get(key));
async function put(key,value){const tx=db.transaction('resources','readwrite'),finished=done(tx);tx.objectStore('resources').put(value,key);await finished;}
let stageText='',lastPaint=0;
function progress(stage,current=0,total=0,force=false){
 const now=performance.now();if(!force&&stage===stageText&&now-lastPaint<100)return;
 stageText=stage;lastPaint=now;$('loading').hidden=false;$('phase').textContent=stage;status(stage);
 try{localStorage.setItem('ra2-last-stage',stage);}catch{}
 if(total){$('progress').max=total;$('progress').value=current;$('percent').textContent=Math.min(100,current/total*100).toFixed(1)+'%';$('bytes').textContent=size(current)+' / '+size(total);}
 else{$('progress').removeAttribute('value');$('percent').textContent='';$('bytes').textContent='此阶段没有准确百分比，请稍候';}
}
setInterval(()=>{
 if(!loading&&!importing)return;const now=performance.now(),seconds=Math.max(1,(now-startedAt)/1000);
 speedSamples.push({time:now,bytes:networkBytes});while(speedSamples.length>1&&speedSamples[1].time<now-5000)speedSamples.shift();
 const first=speedSamples[0],recent=(networkBytes-first.bytes)/Math.max(0.5,(now-first.time)/1000);
 const activeSeconds=(transferMilliseconds+(transferStarted?now-transferStarted:0))/1000;
 $('elapsed').textContent='已用 '+Math.floor(seconds)+' 秒 · 本次下载 '+size(networkBytes)+(transferStarted?' · 当前 '+size(recent)+'/秒':' · 当前未下载')+(activeSeconds?' · 下载平均 '+size(networkBytes/activeSeconds)+'/秒':'');
},500);
async function* streamFile(file){
 let offset=0;const count=Math.ceil(file.size/CHUNK);
 for(let i=0;i<count;i++){
  const length=Math.min(CHUNK,file.size-offset),key=file.sha256+':'+i;
  let bytes=await get(key);
  if(bytes instanceof ArrayBuffer&&bytes.byteLength===length){progress('读取本地缓存：'+file.name,offset+length,file.size);}
  else{
   if(file.localOnly)throw new Error('请从设置导入已有资源包：'+file.name+' 尚未缓存');
   progress('下载：'+file.name,offset,file.size,true);
   transferStarted=performance.now();
   try{
   const chunkUrl=file.chunkUrls?.[i];
   if(file.chunkUrls&&(!chunkUrl||file.chunkUrls.length!==count||file.chunkHashes?.length!==count))throw new Error('资源分块清单不完整');
   const response=await fetch(chunkUrl||file.url,chunkUrl?{}:{headers:{Range:`bytes=${offset}-${offset+length-1}`}});
   if(!response.ok)throw new Error(file.name+' 下载失败：'+response.status);
   if(!chunkUrl&&response.status!==206&&file.size>CHUNK){await response.body?.cancel();throw new Error('服务器未提供分块下载，请刷新页面再试');}
   if(!chunkUrl&&response.status===206&&response.headers.get('Content-Range')!==`bytes ${offset}-${offset+length-1}/${file.size}`)throw new Error('下载分块位置不正确');
   const output=new Uint8Array(length);let received=0;
   if(response.body){const reader=response.body.getReader();while(true){const part=await reader.read();if(part.done)break;if(received+part.value.length>length){await reader.cancel();throw new Error('下载分块超出预期大小');}output.set(part.value,received);received+=part.value.length;networkBytes+=part.value.length;progress('下载：'+file.name,offset+received,file.size);}}
   else{const full=new Uint8Array(await response.arrayBuffer());output.set(full);received=full.length;networkBytes+=received;}
   if(received!==length)throw new Error('网络传输中断；已完成的分块会保留，刷新后可继续');
   if(file.chunkHashes){const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',output)),n=>n.toString(16).padStart(2,'0')).join('');if(digest!==file.chunkHashes[i])throw new Error('资源下载校验失败：'+file.name+'；刷新后重试');}
   bytes=output.buffer;
   }finally{transferMilliseconds+=performance.now()-transferStarted;transferStarted=0;}
   progress('保存本地缓存：'+file.name,offset+length,file.size,true);await put(key,bytes);
  }
  offset+=length;yield new Uint8Array(bytes);
 }
 await put(file.sha256+':meta',{size:file.size,chunks:count});log('资源就绪 '+file.name);
}
async function readResource(file){const output=new Uint8Array(file.size);let offset=0;for await(const chunk of streamFile(file)){output.set(chunk,offset);offset+=chunk.length;}return output;}
function instantiateStreaming(imports,success,reject){
 for(const namespace of Object.values(imports))for(const value of Object.values(namespace))if(value instanceof WebAssembly.Memory)gameMemory=value;
 const file=manifest.artifacts['ra2-web.wasm'],iterator=streamFile(file);
 const body=new ReadableStream({async pull(controller){try{const next=await iterator.next();if(next.done){controller.close();progress('下载完成，正在编译游戏程序…',0,0,true);}else controller.enqueue(next.value);}catch(e){controller.error(e);}},async cancel(){await iterator.return();}});
 WebAssembly.instantiateStreaming(new Response(body,{headers:{'Content-Type':'application/wasm'}}),imports).then(({instance,module})=>{progress('程序编译完成，正在分配内存和初始化…',0,0,true);success(instance,module);}).catch(reject);
 return {};
}
async function initialize(){
 try{
  manifest=await(await fetch('manifest.json',{cache:'no-store'})).json();db=await database();
  const offer=manifest.programUpdate;
  if(offer?.fallback&&(await get(offer.from+':meta'))?.size!==offer.sourceSize)manifest.programUpdate=offer.fallback;
  try{const previous=JSON.parse(localStorage.getItem('ra2-last-error')||'null');if(previous){log('上次运行错误：'+previous.error);sendDiagnostics({...previous,kind:'previous-session'});}}catch{}
  if(!manifest.ready){document.body.classList.remove('game-shell');status('游戏程序暂不可用。');openSettings();return;}
  await showProgramVersion();
  if(!globalThis.crossOriginIsolated||typeof SharedArrayBuffer==='undefined'){document.body.classList.remove('game-shell');status('请通过 HTTPS 游戏地址访问；当前浏览器没有提供多线程运行条件。');openSettings();return;}
  const total=manifest.files.reduce((n,f)=>n+f.size,0)+manifest.artifacts['ra2-web.wasm'].size;
  const all=[manifest.artifacts['ra2-web.wasm'],...manifest.files];
  const states=await Promise.all(all.map(async file=>{
   if((await get(file.sha256+':meta'))?.size!==file.size)return false;
   const keys=await Promise.all(Array.from({length:Math.ceil(file.size/CHUNK)},(_,i)=>request(db.transaction('resources').objectStore('resources').getKey(file.sha256+':'+i))));
   return keys.every(key=>key!==undefined);
  }));
  const missingImports=manifest.resourceMode==='local-import'&&!states.slice(1).every(Boolean);
  const complete=states.every(Boolean),cached=all.reduce((n,f,i)=>n+(states[i]?f.size:0),0);
  $('resources').textContent='已确认本地缓存 '+size(cached)+' / '+size(total)+(complete?'，无需重新导入或下载游戏资源。':'；已保存的分块会复用。');
  let interrupted=false,lastStage='';try{interrupted=localStorage.getItem('ra2-launch-pending')==='1';lastStage=localStorage.getItem('ra2-last-stage')||'';}catch{}
  status(interrupted?'上次启动中断'+(lastStage?'（'+lastStage+'）':'')+'。'+(complete?'资源缓存仍在，无需重新导入。':'正在显示实际缓存状态。'):'资源检查完成，点击启动游戏。');
  $('start').textContent=complete?'启动游戏（本地资源已就绪）':'下载缺失资源并启动';$('start').disabled=missingImports;
  if(complete)$('import').textContent='重新导入资源包（可选）';
  else if(manifest.programUpdate&&(await get(manifest.programUpdate.from+':meta'))?.size===manifest.programUpdate.sourceSize){$('resources').textContent='已导入的游戏资源仍在，仅需程序增量更新'+(manifest.programUpdate.downloadBytes?'（'+size(manifest.programUpdate.downloadBytes)+'）':'')+'，无需重新导入完整资源包。';$('start').textContent='更新程序并启动';}
  if(missingImports){$('start').textContent='先导入资源包';$('resources').textContent+='；请导入手机已有的 .ra2pack 文件，无需重新下载。';}
  $('import').disabled=false;
  if((complete||manifest.resourceMode==='github-releases')&&location.hash!=='#settings')startGame(false);
  else{if(!complete)status(missingImports?'请导入手机已有的资源包，程序更新会自动下载。':'请导入资源包或程序更新包，也可以下载缺失资源后启动。');openSettings();}
 }catch(e){document.body.classList.remove('game-shell');status('无法准备游戏：'+(e?.message||e));log(e?.stack||e);openSettings();}
}
async function startGame(manual=true){
 if(loading||running||importing)return;closeSettings();document.body.classList.add('game-shell');loading=true;startedAt=performance.now();networkBytes=0;
 transferStarted=0;transferMilliseconds=0;speedSamples=[{time:startedAt,bytes:0}];
 if(manual)try{localStorage.setItem('ra2-auto-start','1');}catch{}
 try{sessionStorage.setItem('ra2-launch-in-progress','1');}catch{}
 try{localStorage.setItem('ra2-launch-pending','1');}catch{}
 try{localStorage.removeItem('ra2-last-error');}catch{}
 $('import').disabled=true;$('start').disabled=true;$('start').textContent='正在启动…';progress('加载启动器…',0,0,true);
 try{
  await ensureRuntimeUpdate();await showProgramVersion();
  if(typeof createRA2Web!=='function'){const script=document.createElement('script');script.src=manifest.script.url;await new Promise((resolve,reject)=>{script.onload=resolve;script.onerror=()=>reject(new Error('启动器加载失败'));document.head.appendChild(script);});}
  let fail;const failed=new Promise((_,reject)=>{fail=reject;});
  progress('准备下载或读取游戏程序…',0,0,true);
  game=await Promise.race([createRA2Web({canvas,noInitialRun:true,onThreadError:reason=>reportRuntimeError(reason,'pthread'),locateFile:path=>manifest.artifacts[path]?.url||path,instantiateWasm:(imports,success)=>instantiateStreaming(imports,success,fail),print:log,printErr:log,onGameFrame:()=>{document.body.classList.add('game-active');try{localStorage.removeItem('ra2-launch-pending');sessionStorage.removeItem('ra2-launch-in-progress');}catch{}loading=false;$('loading').hidden=true;$('import').disabled=false;$('start').textContent='游戏运行中';status('游戏已开始输出画面，菜单仍需初始化片刻。');},onAbort:reason=>{document.body.classList.remove('game-active','game-shell');loading=false;running=false;status('游戏停止：'+reason);fail(new Error(String(reason)));},onExit:code=>{document.body.classList.remove('game-active','game-shell');loading=false;running=false;status('游戏已退出，代码 '+code);$('loading').hidden=true;$('start').disabled=false;$('start').textContent='重新启动游戏';$('import').disabled=false;openSettings();}}),failed]);
  game.FS.mkdirTree('/game');let loaded=0;const total=manifest.files.reduce((n,f)=>n+f.size,0);
  for(const file of manifest.files){const bytes=await readResource(file);progress('载入游戏内存：'+file.name,file.size,file.size,true);await new Promise(resolve=>setTimeout(resolve,0));game.FS.writeFile('/game/'+file.name,bytes,{canOwn:true});loaded+=file.size;$('resources').textContent='游戏资源已载入 '+size(loaded)+' / '+size(total)+'；本次下载 '+size(networkBytes);}
  game.FS.chdir('/game');progress('下载与载入完成，原游戏正在初始化…',0,0,true);running=true;game.callMain(['/game/game.exe','--with-launcher']);canvas.focus();
 }catch(e){document.body.classList.remove('game-active','game-shell');loading=false;running=false;status('启动失败：'+(e?.message||String(e)));log(e?.stack||e);$('phase').textContent='启动失败，已保存的资源分块仍然保留';$('start').textContent='刷新后重试';$('start').disabled=false;$('import').disabled=false;openSettings();}
}
$('start').onclick=()=>{if(loading||importing)return;if(game||pendingReload){closeSettings();location.reload();return;}startGame(true);};
$('import').onclick=()=>{if(loading||importing)return;$('pack').click();};
$('pack').onchange=async()=>{
 const pack=$('pack').files[0];if(!pack||loading||importing)return;
 if(!db||!manifest){status('页面尚未准备完成，请稍后再导入。');return;}
 importing=true;startedAt=performance.now();networkBytes=0;transferStarted=0;transferMilliseconds=0;speedSamples=[];$('start').disabled=true;$('import').disabled=true;
 try{
  const first=new Uint8Array(await pack.slice(0,12).arrayBuffer());
  if(new TextDecoder().decode(first.slice(0,8))==='RA2UPDT1'){await applyRuntimeUpdate(pack);$('phase').textContent='程序更新完成';status('程序更新完成，原有游戏资源已保留，可以启动。');$('start').textContent='启动游戏（程序已更新）';pendingReload=!!game;return;}
  if(first.length!==12||new TextDecoder().decode(first.slice(0,8))!=='RA2PACK1')throw new Error('不是有效的红警资源包');
  const length=new DataView(first.buffer).getUint32(8,true);if(length>1024*1024||12+length>pack.size)throw new Error('资源包头损坏');
  const header=JSON.parse(await pack.slice(12,12+length).text());
  const expected=[manifest.artifacts['ra2-web.wasm'],...manifest.files];
  if(header.version!==1||header.files?.length!==expected.length)throw new Error('资源包版本不匹配');
  let offset=12+length;
  for(let index=0;index<expected.length;index++){
   let file=expected[index];const entry=header.files[index];
   if(index===0&&((entry.sha256===manifest.programUpdate?.from&&entry.size===manifest.programUpdate.sourceSize)||manifest.programUpdate?.resourcePrograms?.some(p=>p.sha256===entry.sha256&&p.size===entry.size)))file={...file,sha256:entry.sha256,size:entry.size};
   const count=Math.ceil(file.size/CHUNK);
   if(entry.sha256!==file.sha256||entry.size!==file.size||entry.chunks?.length!==count)throw new Error('资源包与当前游戏版本不匹配：'+file.name);
   for(let i=0;i<count;i++){
    const end=offset+Math.min(CHUNK,file.size-i*CHUNK);if(end>pack.size)throw new Error('资源包不完整');
    const bytes=await pack.slice(offset,end).arrayBuffer();
    const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
    if(digest!==entry.chunks[i])throw new Error('资源包校验失败：'+file.name);
    await put(file.sha256+':'+i,bytes);offset=end;progress('从手机文件导入：'+file.name,offset,pack.size,true);
    await new Promise(resolve=>setTimeout(resolve,0));
   }
   await put(file.sha256+':meta',{size:file.size,chunks:count});
  }
  if(offset!==pack.size)throw new Error('资源包长度不正确');
  $('phase').textContent='资源包导入完成';status('导入完成，点击启动游戏即可使用本地资源。');$('start').textContent='启动游戏（资源已导入）';pendingReload=!!game;
 }catch(e){status('导入失败：'+e.message);$('phase').textContent='导入失败；已完成的分块保留';log(e.stack||e);}
 finally{importing=false;$('start').disabled=running&&!pendingReload;$('import').disabled=false;$('pack').value='';if(pendingReload){$('start').textContent='重载游戏以应用更新';status('导入完成。重载后生效，重载会结束当前对局。');}await showProgramVersion();}
};

// Read-only diagnostics for the exact published v0.1.2 USER32 layout.
// Addresses came from its linker map; the data sections were compared byte for byte.
let controlTap=null,lastControlReport='';
function controlSnapshot(){
 if(!running||!gameMemory||!['c19ab41c0dae310ce59aa8591e88c3955d6b0854583b4febd1ac2afd1da1f502','1161d114e9b077a325db9c668fcd8915f8cc06c776efce499682bc607c417e66','bffe87187bfcffda96a83838d30ded1174b49e1a0e800f07b697c90e4fe96a4e','5f7f1d11111d725549b4c26c6fa0fb631de00ee1aa4026aeae74429d61af6173'].includes(manifest.artifacts['ra2-web.wasm'].sha256))return null;
 const view=new DataView(gameMemory.buffer),bytes=new Uint8Array(gameMemory.buffer),base=0xfe2f0,stride=836;
 if(view.byteLength<0x2a8c90)return null;
 const uint=p=>view.getUint32(p,true),integer=p=>view.getInt32(p,true);
 const string=(p,max=120)=>{
  if(!p||p>=bytes.length)return '';
  let end=p;while(end<Math.min(p+max,bytes.length)&&bytes[end])end++;
  const raw=bytes.subarray(p,end),utf=new TextDecoder().decode(raw);
  try{return (utf.includes('�')?new TextDecoder('big5').decode(raw):utf).slice(0,60);}catch{return utf.slice(0,60);}
 };
 const windows=new Map();
 for(let i=0;i<2048;i++){
  const p=base+i*stride;if(uint(p)!==1)continue;
  const h=uint(p+16);if(h!==(0x10000|(i<<4)))return null;
  windows.set(h,{p,parent:uint(p+24),style:uint(p+32),x:integer(p+64),y:integer(p+68)});
 }
 const controls=[],capture=uint(0x2a8c8c),focus=uint(0x2a8c88);
 for(const [hwnd,w] of windows){
  const p=w.p,kind=integer(p+8);if(kind!==6&&kind!==7)continue;
  let x=0,y=0,disabled=false,visible=true,parent=w;
  for(let depth=0;parent&&depth<64;depth++){
   visible=visible&&!!(parent.style&0x10000000);disabled=disabled||!!(parent.style&0x08000000);
   x+=parent.x;y+=parent.y;parent=windows.get(parent.parent);
  }
  if(!visible)continue;
  const width=integer(p+72),height=integer(p+76),count=integer(p+828);
  const row={hwnd:hwnd.toString(16),id:uint(p+40),kind,rect:[x,y,width,height],disabled,selected:integer(p+784),count,dropped:integer(p+808),itemHeight:integer(p+792),dropHeight:integer(p+820)};
  if(hwnd===focus||hwnd===capture||(controlTap&&controlTap[0]>=x&&controlTap[0]<x+width&&controlTap[1]>=y&&controlTap[1]<y+height)){
   row.text=string(p+228);row.items=[];const items=uint(p+824);
   if(count>=0&&count<=1024&&items&&items+count*8<=bytes.length)for(let j=0;j<Math.min(count,12);j++)row.items.push(string(uint(items+j*8),80));
  }
  controls.push(row);if(controls.length>=32)break;
 }
 const popups=[];
 for(const [hwnd,w] of windows){
  const cls=integer(w.p+4),name=cls>=0&&cls<64?string(0x2a7680+cls*88,64):'';
  if(hwnd!==capture&&name!=='ComboDropWin')continue;
  let x=0,y=0,parent=w;for(let depth=0;parent&&depth<64;depth++){x+=parent.x;y+=parent.y;parent=windows.get(parent.parent);}
  popups.push({hwnd:hwnd.toString(16),class:name,kind:integer(w.p+8),parent:w.parent.toString(16),style:w.style.toString(16),proc:uint(w.p+20).toString(16),user:uint(w.p+44).toString(16),rect:[x,y,integer(w.p+72),integer(w.p+76)]});
 }
 const hitWindows=[];
 if(controlTap)for(const [hwnd,w] of windows){
  const p=w.p,id=uint(p+40),width=integer(p+72),height=integer(p+76);
  if(!id||width<=0||height<=0||(width>=canvas.width*0.9&&height>=canvas.height*0.8))continue;
  let x=0,y=0,visible=true,disabled=false,parent=w;
  for(let depth=0;parent&&depth<64;depth++){visible=visible&&!!(parent.style&0x10000000);disabled=disabled||!!(parent.style&0x08000000);x+=parent.x;y+=parent.y;parent=windows.get(parent.parent);}
  if(!visible||controlTap[0]<x||controlTap[0]>=x+width||controlTap[1]<y||controlTap[1]>=y+height)continue;
  const cls=integer(p+4);hitWindows.push({hwnd:hwnd.toString(16),id,kind:integer(p+8),class:cls>=0&&cls<64?string(0x2a7680+cls*88,64):'',rect:[x,y,width,height],disabled});
 }
 return controls.length||hitWindows.length?{version:manifest.programUpdate?.version,tap:controlTap,capture:capture.toString(16),focus:focus.toString(16),popups,hitWindows,controls}:null;
}
function reportControls(){
 try{
  const snapshot=controlSnapshot();if(!snapshot)return;
  const serialized=JSON.stringify(snapshot);if(serialized===lastControlReport)return;lastControlReport=serialized;
  log('[controls] '+serialized);
  sendDiagnostics({kind:'controls',stage:'menu-input',error:'',logs:serialized});
 }catch{/* Diagnostic reads must never change game input or error state. */}
}
canvas.addEventListener('pointerup',e=>{if(!running)return;controlTap=point(e,true);setTimeout(reportControls,300);});
setInterval(reportControls,2500);

const point=(event,clamp=false)=>{
 const r=canvas.getBoundingClientRect(),scale=Math.min(r.width/canvas.width,r.height/canvas.height);
 if(!scale)return null;
 const x=(event.clientX-r.left-(r.width-canvas.width*scale)/2)/scale,y=(event.clientY-r.top-(r.height-canvas.height*scale)/2)/scale;
 if(!clamp&&(x<0||y<0||x>=canvas.width||y>=canvas.height))return null;
 // Keep phone input outside the game's edge-scroll hot zones. Mouse input stays exact.
 const inset=event.pointerType==='touch'?16:0;
 return [Math.max(inset,Math.min(canvas.width-1-inset,Math.floor(x))),Math.max(inset,Math.min(canvas.height-1-inset,Math.floor(y)))];
};
let active=null,heldButton=0,physicalPosition=[0,0];
// Defer a touch press until a tap or single-finger drag is established.
// The left stick owns camera keys; canvas fingers remain ordinary game input.
const panKeys=new Set(),stick=$('view-stick');
let touchPress=null,stickPointer=null,stickTouch=null;
function scrollKeys(keys){
 for(const vk of panKeys)if(!keys.includes(vk)){
  if(game&&!physicalHeld.has(vk))game._ra2_web_key(0,vk,0);
  panKeys.delete(vk);
 }
 for(const vk of keys)if(!panKeys.has(vk)){
  if(running&&!physicalHeld.has(vk))game._ra2_web_key(1,vk,0);
  panKeys.add(vk);
 }
}
function stopPan(){
 const pointer=stickPointer;stickPointer=null;stickTouch=null;stick.classList.remove('active');
 stick.style.setProperty('--stick-x','0px');stick.style.setProperty('--stick-y','0px');
 if(pointer!==null&&stick.hasPointerCapture(pointer))stick.releasePointerCapture(pointer);
 scrollKeys([]);
}
function moveStick(e){
 const rect=stick.getBoundingClientRect(),dx=e.clientX-rect.left-rect.width/2,dy=e.clientY-rect.top-rect.height/2;
 const distance=Math.hypot(dx,dy),travel=30,scale=distance>travel?travel/distance:1;
 stick.style.setProperty('--stick-x',dx*scale+'px');stick.style.setProperty('--stick-y',dy*scale+'px');
 if(distance<8){scrollKeys([]);return;}
 const major=Math.max(Math.abs(dx),Math.abs(dy)),keys=[];
 const horizontal=dx<0?37:39,vertical=dy<0?38:40;
 // A small angle hysteresis keeps the stick steady near diagonal boundaries.
 if(Math.abs(dx)>=major*(panKeys.has(horizontal)?.30:.45))keys.push(horizontal);
 if(Math.abs(dy)>=major*(panKeys.has(vertical)?.30:.45))keys.push(vertical);
 scrollKeys(keys);
}
stick.addEventListener('pointerdown',e=>{
 if(!running||settings.open||stickPointer!==null||e.button!==0)return;
 e.preventDefault();stickPointer=e.pointerId;stick.setPointerCapture(e.pointerId);
 stick.classList.add('active');moveStick(e);
});
stick.addEventListener('pointermove',e=>{if(e.pointerId!==stickPointer)return;e.preventDefault();moveStick(e);});
// Listen before target handlers too, so lifting outside the pad still releases.
for(const type of ['pointerup','pointercancel'])window.addEventListener(type,e=>{
 if(e.pointerId!==stickPointer)return;stopPan();
},true);
stick.addEventListener('lostpointercapture',e=>{
 if(e.pointerId!==stickPointer)return;stopPan();
});
stick.addEventListener('touchstart',e=>{
 if(e.cancelable)e.preventDefault();
 if(stickTouch===null&&stickPointer!==null)stickTouch=e.changedTouches[0]?.identifier??null;
},{passive:false});
// iOS fallback: track the stick's own touch, independently of the right hand.
for(const type of ['touchend','touchcancel'])window.addEventListener(type,e=>{
 if(stickPointer===null)return;
 if(!e.touches.length||[...e.changedTouches].some(t=>t.identifier===stickTouch))stopPan();
},{capture:true,passive:true});
window.addEventListener('pointermove',e=>{
 if(e.pointerId===stickPointer&&e.pointerType==='mouse'&&e.buttons===0)stopPan();
},true);
window.addEventListener('pagehide',stopPan);
stick.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('pointerdown',e=>{
 if(!running)return;
 const p=point(e);if(!p)return;
 if(e.pointerType==='touch'){
  e.preventDefault();canvas.setPointerCapture(e.pointerId);
  if(active!==null)return;
  active=e.pointerId;heldButton=right?2:0;
  touchPress={point:p,x:e.clientX,y:e.clientY};return;
 }
 if(active!==null)return;
 e.preventDefault();active=e.pointerId;physicalPosition=p;heldButton=right||e.button===2?2:0;canvas.setPointerCapture(e.pointerId);
 game._ra2_web_mouse(0,p[0],p[1],heldButton);game._ra2_web_mouse(1,p[0],p[1],heldButton);
});
canvas.addEventListener('pointermove',e=>{
 if(!running)return;
 if(active!==null&&active!==e.pointerId)return;
 const p=point(e,active===e.pointerId);if(!p)return;
 if(touchPress){
  if(Math.hypot(e.clientX-touchPress.x,e.clientY-touchPress.y)<6)return;
  const start=touchPress.point;touchPress=null;
  game._ra2_web_mouse(0,start[0],start[1],heldButton);game._ra2_web_mouse(1,start[0],start[1],heldButton);
 }
 physicalPosition=p;game._ra2_web_mouse(0,p[0],p[1],heldButton);
});
function release(e){
 if(!running||active!==e.pointerId)return;
 const p=e.type==='lostpointercapture'?physicalPosition:point(e,true);
 if(touchPress){
  if(e.type==='pointerup'&&p){
   game._ra2_web_mouse(0,p[0],p[1],heldButton);game._ra2_web_mouse(1,p[0],p[1],heldButton);
   game._ra2_web_mouse(2,p[0],p[1],heldButton);physicalPosition=p;
  }
  touchPress=null;
 }else if(p){game._ra2_web_mouse(2,p[0],p[1],heldButton);physicalPosition=p;}
 active=null;
}
canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('lostpointercapture',release);canvas.addEventListener('contextmenu',e=>e.preventDefault());
// Keep iOS long presses inside the game; input itself uses Pointer Events.
canvas.addEventListener('touchstart',e=>{if(e.cancelable)e.preventDefault();},{passive:false});
$('game-window').addEventListener('selectstart',e=>e.preventDefault());
$('game-window').addEventListener('dragstart',e=>e.preventDefault());
function releaseMouse(){if(running&&active!==null&&!touchPress)game._ra2_web_mouse(2,physicalPosition[0],physicalPosition[1],heldButton);active=null;touchPress=null;}
function resetTouchInput(){releaseMouse();stopPan();}
window.addEventListener('blur',resetTouchInput);document.addEventListener('visibilitychange',()=>{if(document.hidden)resetTouchInput();});
$('mobile-cancel').onclick=()=>{
 if(!running)return;releaseMouse();
 game._ra2_web_mouse(1,physicalPosition[0],physicalPosition[1],2);
 game._ra2_web_mouse(2,physicalPosition[0],physicalPosition[1],2);
 canvas.focus({preventScroll:true});
};
$('mobile-home').onclick=()=>{
 if(!running)return;releaseMouse();
 game._ra2_web_key(1,72,0);game._ra2_web_key(0,72,0);
 canvas.focus({preventScroll:true});
};
$('right').onclick=()=>{right=!right;$('right').textContent=right?'右键模式':'左键模式';};
for(const button of document.querySelectorAll('.key'))button.onclick=()=>{if(running){game._ra2_web_key(1,+button.dataset.vk,0);game._ra2_web_key(0,+button.dataset.vk,0);}};
const physicalHeld=new Set();document.addEventListener('keydown',e=>{if(!running||settings.open||physicalHeld.has(e.keyCode))return;physicalHeld.add(e.keyCode);if(!panKeys.has(e.keyCode))game._ra2_web_key(1,e.keyCode,0);if([27,32,37,38,39,40].includes(e.keyCode))e.preventDefault();});document.addEventListener('keyup',e=>{if(!running||settings.open)return;physicalHeld.delete(e.keyCode);if(!panKeys.has(e.keyCode))game._ra2_web_key(0,e.keyCode,0);});window.addEventListener('blur',()=>{if(game)for(const vk of physicalHeld)game._ra2_web_key(0,vk,0);physicalHeld.clear();});
$('fullscreen').onclick=()=>canvas.requestFullscreen?.().catch(log);
// Safari versions that ignore overscroll-behavior still need a cancelable
// touchmove handler. Setup can scroll internally; game gestures never pan the page.
let touchX=0,touchY=0;
document.addEventListener('touchstart',event=>{const touch=event.touches[0];if(touch){touchX=touch.clientX;touchY=touch.clientY;}},{passive:true});
document.addEventListener('touchmove',event=>{
 if(settings.contains(event.target))return;
 if(document.body.classList.contains('game-active')){if(event.cancelable)event.preventDefault();return;}
 if(event.touches.length!==1)return;
 const touch=event.touches[0],dx=touch.clientX-touchX,dy=touch.clientY-touchY;touchX=touch.clientX;touchY=touch.clientY;
 if(Math.abs(dy)>Math.abs(dx))for(let el=event.target instanceof Element?event.target:null;el&&el!==document.body;el=el.parentElement){
  if(!/(auto|scroll)/.test(getComputedStyle(el).overflowY))continue;
  if((dy>0&&el.scrollTop>0)||(dy<0&&el.scrollTop+el.clientHeight<el.scrollHeight-1))return;
 }
 if(event.cancelable)event.preventDefault();
},{passive:false});
document.addEventListener('wheel',event=>{if(!settings.contains(event.target)&&document.body.classList.contains('game-active')&&event.cancelable)event.preventDefault();},{passive:false});
initialize();

window.addEventListener('error',event=>{if(running||loading)reportRuntimeError(event);});
window.addEventListener('unhandledrejection',event=>{if(running||loading)reportRuntimeError(event,'promise');});
