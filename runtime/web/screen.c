/* DirectDraw software pixels presented to the browser's 2D canvas. No desktop capture. */
#include <emscripten.h>
#include <stdint.h>
#include <stdio.h>
#include "win32hle.h"
void (*hle_screen_frame_hook)(const uint8_t *,int,int,int,int);
int (*hle_screen_compose_hook)(const uint8_t *,int,int,int,uint32_t *);
int (*hle_screen_key_hook)(int,int);
int (*hle_screen_cursor_hook)(void);
void (*hle_screen_settings_hook)(const char *,int,int);
static uint32_t shown_ms;
void hle_screen_pump(void){
 uint32_t now=hle_ticks_ms();if(shown_ms&&now-shown_ms<32)return;
 const uint8_t *px;const uint32_t *pal;int w,h,pitch,bpp;unsigned seq;
 if(!hle_dd_frame(&px,&w,&h,&pitch,&bpp,&pal,&seq))return;
 shown_ms=now;if(hle_screen_frame_hook)hle_screen_frame_hook(px,w,h,pitch,bpp);
 MAIN_THREAD_EM_ASM({
  const px=$0;const w=$1;const h=$2;const pitch=$3;const bpp=$4;const pal=$5;
  const canvas=Module['canvas'];if(!canvas)return;
  if(canvas.width!==w)canvas.width=w;if(canvas.height!==h)canvas.height=h;
  const ctx=canvas.getContext('2d',{alpha:false});if(!ctx)return;
  if(!Module.ra2Image||Module.ra2Image.width!==w||Module.ra2Image.height!==h)Module.ra2Image=ctx.createImageData(w,h);
  const rgba=Module.ra2Image.data;
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
   let p=px+y*pitch+x*(bpp>>3);let o=(y*w+x)*4;let r=0;let g=0;let b=0;
   if(bpp===16){let v=HEAPU16[p>>1];r=((v>>11)&31)*255/31;g=((v>>5)&63)*255/63;b=(v&31)*255/31;}
   else if(bpp===24||bpp===32){b=HEAPU8[p];g=HEAPU8[p+1];r=HEAPU8[p+2];}
   else if(pal){let v=HEAPU32[(pal>>2)+HEAPU8[p]];r=v&255;g=(v>>8)&255;b=(v>>16)&255;}
   rgba[o]=r;rgba[o+1]=g;rgba[o+2]=b;rgba[o+3]=255;
  }
  ctx.putImageData(Module.ra2Image,0,0);
 },px,w,h,pitch,bpp,pal);
}
int hle_screen_open(const char *title,int fullscreen,int headless){(void)title;(void)fullscreen;(void)headless;hle_set_pump_hook(hle_screen_pump);fprintf(stderr,"[web-screen] browser canvas software presenter\n");return 0;}
void hle_screen_title(const char *title){(void)title;}
int hle_screen_scale(const char *name){(void)name;return 1;}
void hle_screen_bars(int enabled){(void)enabled;}
