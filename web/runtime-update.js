'use strict';
async function applyRuntimeUpdate(pack){
 const header=new Uint8Array(await pack.slice(0,12).arrayBuffer());
 if(header.length!==12||new TextDecoder().decode(header.slice(0,8))!=='RA2UPDT1')throw new Error('程序更新包格式不正确');
 const length=new DataView(header.buffer).getUint32(8,true);
 if(length>65536||12+length>=pack.size)throw new Error('程序更新包头损坏');
 const update=JSON.parse(await pack.slice(12,12+length).text()),expected=[manifest.programUpdate,manifest.programUpdate?.fallback].find(p=>p&&p.mode===update.mode&&p.from===update.from&&p.to===update.to);
 if(!expected||update.mode!==expected.mode||update.from!==expected.from||update.to!==expected.to||update.size!==expected.size||update.sourceSize!==expected.sourceSize||JSON.stringify(update.chunks)!==JSON.stringify(expected.chunks))throw new Error('程序更新包与当前版本不匹配');
 if(update.mode==='wasm'){
  const reader=pack.slice(12+length).stream().pipeThrough(new DecompressionStream('deflate')).getReader();
  let total=0,index=0,used=0,output=new Uint8Array(Math.min(CHUNK,update.size));
  try{
   while(true){const part=await reader.read();if(part.done)break;let offset=0;
    while(offset<part.value.length){const count=Math.min(part.value.length-offset,output.length-used);if(!count)throw new Error('程序更新超出预期长度');output.set(part.value.subarray(offset,offset+count),used);offset+=count;used+=count;total+=count;
     if(used===output.length){const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',output)),n=>n.toString(16).padStart(2,'0')).join('');if(digest!==update.chunks[index])throw new Error('程序更新校验失败');await put(update.to+':'+index,output.buffer);index++;progress('安装栈优化程序，保留游戏资源',total,update.size,true);output=new Uint8Array(Math.min(CHUNK,update.size-total));used=0;await new Promise(resolve=>setTimeout(resolve,0));}
    }
   }
   if(total!==update.size||used)throw new Error('程序更新不完整');
  }finally{await reader.cancel().catch(()=>{});}
  await put(update.to+':meta',{size:update.size,chunks:update.chunks.length});await showProgramVersion();log('栈优化程序安装完成，原有游戏资源保留');return;
 }
 if((await get(update.from+':meta'))?.size!==update.sourceSize)throw new Error('请先导入之前下载的完整资源包，再导入程序更新');
 const reader=pack.slice(12+length).stream().pipeThrough(new DecompressionStream('deflate')).getReader();
 const parts=[];let expanded=0;
 const limit=Math.min(expected.deltaBytes||32*1024*1024,128*1024*1024);
 while(true){const part=await reader.read();if(part.done)break;expanded+=part.value.length;if(expanded>limit){await reader.cancel();throw new Error('程序更新包超出大小限制');}parts.push(part.value);}
 if(expected.deltaBytes&&expanded!==expected.deltaBytes)throw new Error('程序更新包解压长度不正确');
 const delta=new Uint8Array(expanded);let cursor=0;for(const part of parts){delta.set(part,cursor);cursor+=part.length;}
 let position=0,total=0,index=0,used=0,output=new Uint8Array(Math.min(CHUNK,update.size));
 const sourceCache=new Map();
 function integer(){let value=0,factor=1;for(let i=0;i<5;i++){if(position>=delta.length)break;const byte=delta[position++];value+=(byte&127)*factor;if(!(byte&128))return value;factor*=128;}throw new Error('程序更新指令损坏');}
 if(integer()!==update.sourceSize||integer()!==update.size)throw new Error('程序更新大小不匹配');
 async function append(bytes){
  let offset=0;
  while(offset<bytes.length){const length=Math.min(bytes.length-offset,output.length-used);if(!length)throw new Error('程序更新超出预期长度');output.set(bytes.subarray(offset,offset+length),used);offset+=length;used+=length;total+=length;
   if(used===output.length){
    const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',output)),n=>n.toString(16).padStart(2,'0')).join('');
    if(digest!==update.chunks[index])throw new Error('程序更新校验失败');
    await put(update.to+':'+index,output.buffer);index++;progress('升级程序，保留已导入资源',total,update.size,true);
    output=new Uint8Array(Math.min(CHUNK,update.size-total));used=0;await new Promise(resolve=>setTimeout(resolve,0));
   }
  }
 }
 while(position<delta.length){
  const command=delta[position++];
  if(command&128){let offset=0,length=0;for(let bit=0;bit<7;bit++)if(command&(1<<bit)){if(position>=delta.length)throw new Error('程序更新指令不完整');const value=delta[position++];if(bit<4)offset+=value*2**(8*bit);else length+=value*2**(8*(bit-4));}length=length||65536;
   if(offset+length>update.sourceSize||total+length>update.size)throw new Error('程序更新读取范围不正确');
   while(length){const chunkIndex=Math.floor(offset/CHUNK);let source=sourceCache.get(chunkIndex);
    if(!source){const buffer=await get(update.from+':'+chunkIndex);if(!(buffer instanceof ArrayBuffer))throw new Error('旧程序缓存不完整，请重新导入已有资源包');source=new Uint8Array(buffer);sourceCache.clear();sourceCache.set(chunkIndex,source);}
    const within=offset%CHUNK,count=Math.min(length,source.length-within);if(count<=0)throw new Error('旧程序缓存大小不正确');await append(source.subarray(within,within+count));offset+=count;length-=count;
   }
  }else{if(!command||position+command>delta.length||total+command>update.size)throw new Error('程序更新数据不完整');await append(delta.subarray(position,position+command));position+=command;}
 }
 if(total!==update.size||used)throw new Error('程序更新未完成');
 await put(update.to+':meta',{size:update.size,chunks:update.chunks.length});await showProgramVersion();log('程序增量更新完成，原有游戏资源保留');
}
async function ensureRuntimeUpdate(){
 const update=manifest.programUpdate;if(!update||(await get(update.to+':meta'))?.size===update.size||(update.mode!=='wasm'&&(await get(update.from+':meta'))?.size!==update.sourceSize))return;
 progress('下载小型程序更新，保留已导入资源…',0,0,true);
 transferStarted=performance.now();let pack;
 try{
  const response=await fetch(update.url);if(!response.ok)throw new Error('程序更新下载失败');
  const reader=response.body.getReader(),parts=[];let received=0;const total=Number(response.headers.get('Content-Length'))||update.downloadBytes||0;
  while(true){const part=await reader.read();if(part.done)break;received+=part.value.length;networkBytes+=part.value.length;parts.push(part.value);progress('下载程序增量更新（保留已有资源）',received,total);}
  pack=new Blob(parts);
 }finally{transferMilliseconds+=performance.now()-transferStarted;transferStarted=0;}
 await applyRuntimeUpdate(pack);
}
