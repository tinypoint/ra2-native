'use strict';
// Count actual game-canvas presentations, not browser animation callbacks.
(()=>{
 const canvas=document.getElementById('canvas'),host=document.getElementById('game-window');
 if(!canvas||!host)return;
 const label=document.createElement('span');label.id='game-fps';label.textContent='FPS —';host.append(label);
 function place(){
  const controls=document.getElementById('game-controls'),box=host.getBoundingClientRect();
  if(!box.width||!box.height||!canvas.width||!canvas.height)return;
  const centerX=box.left+box.width/2,centerY=box.top+box.height/2;
  let scale=Math.min(box.width/canvas.width,box.height/canvas.height);
  // Keep the centered picture clear of each visible floating control, using
  // either horizontal or vertical letterboxing as space permits.
  for(const element of [...controls.querySelectorAll('button,#view-stick'),label]){
   const rect=element.getBoundingClientRect();if(!rect.width||!rect.height)continue;
   const gapX=Math.max(0,rect.left-centerX-10,centerX-rect.right-10);
   const gapY=Math.max(0,rect.top-centerY-10,centerY-rect.bottom-10);
   scale=Math.min(scale,Math.max(gapX*2/canvas.width,gapY*2/canvas.height));
  }
  const w=canvas.width*scale,h=canvas.height*scale;
  canvas.style.width=w+'px';canvas.style.height=h+'px';
  host.style.setProperty('--game-left',(box.width-w)/2+'px');
  host.style.setProperty('--game-top',(box.height-h)/2+'px');
  host.style.setProperty('--game-right',(box.width+w)/2+'px');
  host.style.setProperty('--game-bottom',(box.height+h)/2+'px');
 }
 const context=canvas.getContext('2d',{alpha:false}),present=context.putImageData;
 let frames=0,started=performance.now(),last=0,width=canvas.width,height=canvas.height;
 context.putImageData=function(...args){
  const result=present.apply(this,args),now=performance.now();
  if(!last){started=now;frames=0;}last=now;frames++;
  if(canvas.width!==width||canvas.height!==height){width=canvas.width;height=canvas.height;place();}
  return result;
 };
 setInterval(()=>{const now=performance.now(),elapsed=now-started;if(!last||elapsed<1000)return;label.textContent='FPS '+Math.round(frames*1000/elapsed);frames=0;started=now;},250);
 const observer=new ResizeObserver(place);observer.observe(host);observer.observe(canvas);
 window.addEventListener('resize',place);window.visualViewport?.addEventListener('resize',place);place();
})();
