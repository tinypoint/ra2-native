/* DirectDraw software pixels presented to the browser's 2D canvas. No desktop capture. */
#include <emscripten.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "win32hle.h"
void (*hle_screen_frame_hook)(const uint8_t *,int,int,int,int);
int (*hle_screen_compose_hook)(const uint8_t *,int,int,int,uint32_t *);
int (*hle_screen_key_hook)(int,int);
int (*hle_screen_cursor_hook)(void);
void (*hle_screen_settings_hook)(const char *,int,int);
extern void ra2_web_pump_input(void);
extern void ra2_web_viewport_origin(int,int);
extern int hle_web_dialog_open(void);
/* Original game controls paint directly into the menu render surface. Keep
 * upper-window pixels intact across synchronous lower-window paints, as the
 * desktop window system would. Also protect an already-presented primary. */
typedef struct {
 uint8_t *px,*copy;int pitch,w,h,bpp,x,y,rows,rowbytes;
} web_pixels;
typedef struct {web_pixels target[2];} web_saved_pixels;
static int web_target(int which,uint8_t **px,int *w,int *h,int *pitch,int *bpp){
 if(!which){const uint8_t *p;const uint32_t *pal;unsigned seq;
  if(!hle_dd_frame(&p,w,h,pitch,bpp,&pal,&seq))return 0;
  *px=(uint8_t *)p;return 1;
 }
 if(!gm_accessible(0x839958,4,0))return 0;
 uint32_t surface=MEM32(0x839958);
 if(!surface||!gm_accessible(surface,32,0))return 0;
 return hle_dd_surface_pixels(MEM32(surface+28),px,w,h,pitch,bpp);
}
void *ra2_web_save_pixels(int l,int t,int r,int b){
 web_saved_pixels *saved=calloc(1,sizeof *saved);if(!saved)return NULL;
 int any=0;
 for(int i=0;i<2;i++){
  web_pixels *p=&saved->target[i];
  if(!web_target(i,&p->px,&p->w,&p->h,&p->pitch,&p->bpp))continue;
  int x=l<0?0:l,y=t<0?0:t,right=r>p->w?p->w:r,bottom=b>p->h?p->h:b;
  if(right<=x||bottom<=y||p->bpp%8)continue;
  p->x=x;p->y=y;p->rows=bottom-y;p->rowbytes=(right-x)*(p->bpp/8);
  p->copy=malloc((size_t)p->rows*p->rowbytes);if(!p->copy)continue;
  for(int row=0;row<p->rows;row++)memcpy(p->copy+row*p->rowbytes,p->px+(y+row)*p->pitch+x*(p->bpp/8),p->rowbytes);
  any=1;
 }
 if(!any){free(saved);return NULL;}return saved;
}
void ra2_web_restore_pixels(void *opaque){
 web_saved_pixels *saved=opaque;if(!saved)return;
 for(int i=0;i<2;i++){
  web_pixels *p=&saved->target[i];if(!p->copy)continue;
  uint8_t *px;int w,h,pitch,bpp;
  /* A callback may change display mode. Never restore into a released surface. */
  if(web_target(i,&px,&w,&h,&pitch,&bpp)&&px==p->px&&w==p->w&&h==p->h&&pitch==p->pitch&&bpp==p->bpp)
   for(int row=0;row<p->rows;row++)memcpy(px+(p->y+row)*pitch+p->x*(bpp/8),p->copy+row*p->rowbytes,p->rowbytes);
  free(p->copy);
 }
 free(saved);
}
static uint32_t shown_ms;
void hle_screen_pump(void){
 uint32_t now=hle_ticks_ms();if(shown_ms&&now-shown_ms<32)return;
 shown_ms=now;
 /* Input must progress even while resolution changes release the primary.
  * Fetch pixels AFTER input: a click can recreate/free the old surface. */
 ra2_web_pump_input();
 const uint8_t *px;const uint32_t *pal;int w,h,pitch,bpp;unsigned seq;
 if(!hle_dd_frame(&px,&w,&h,&pitch,&bpp,&pal,&seq))return;
 if(hle_screen_frame_hook)hle_screen_frame_hook(px,w,h,pitch,bpp);
 /* The original front-end centers its 800x600 artwork in larger modes
  * (006F3930). Present that content rectangle, not its internal black padding.
  * Battle, including its pause/settings dialogs, keeps the full display.
  * This is geometry from the game's menu layout, never a black-pixel heuristic. */
 int ox=0,oy=0;
 if(gm_accessible(0xA40D0B,1,0)&&!MEM8(0xA40D0B)&&!MEM8(0xA40380)&&hle_web_dialog_open()){
  if(w>800){ox=(w-800)/2;w=800;}
  if(h>600){oy=(h-600)/2;h=600;}
 }
 ra2_web_viewport_origin(ox,oy);
 px+=oy*pitch+ox*(bpp>>3);
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
