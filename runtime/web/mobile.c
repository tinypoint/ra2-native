/* Base RA2 addresses verified against the lifted game, never Wasm offsets.
 * Runs under the guest-machine lock, on the game thread only. */
#include <stdio.h>
#include <emscripten.h>
#include "win32hle.h"
extern int hle_web_dialog_open(void);
#define DISPLAY 0x8324E0u
static int busy;
int ra2_mobile_active(void){
 if(!gm_accessible(0xA40EEC,4,0)||!gm_accessible(DISPLAY,0x11B8,0))return 0;
 /* Same readiness checks as original MouseClass input path 0066A400. */
 return MEM8(0xA40380)&&(MEM8(0xA40D04)||MEM8(0xA40D13))&&MEM8(0xA40958)&&MEM32(0x83996C)&&MEM32(0x839C68)&&!MEM8(0xA40D44)&&!hle_web_dialog_open();
}
static int cancel_mode(void){
 uint32_t p=MEM32(DISPLAY+0x11A0);
 if(p&&gm_accessible(p,0x15,0)&&(MEM8(p+0x14)&1))return 2;
 /* Preserve the priority of DisplayClass::RightMouseButtonUp. */
 if(MEM8(DISPLAY+0x11AC)||MEM8(DISPLAY+0x11AD)||MEM8(DISPLAY+0x11AE))return 4;
 if(MEM32(DISPLAY+0x11B4)!=0xFFFFFFFFu)return 3;
 if(MEM8(DISPLAY+0x11AF)||MEM8(DISPLAY+0x11B0))return 4;
 return MEM32(0xA40C70)>0&&MEM32(0xA40C70)<4096?1:0;
}
void ra2_mobile_cancel(int expected){
 if(busy||!ra2_mobile_active()||cancel_mode()!=expected||!expected)return;
 busy=1;
 uint32_t saved=g_ecx,arg=0;g_ecx=DISPLAY;
 /* Original mode cleanup and Deselect callbacks, no screen-coordinate click. */
 hle_call_guest(0x49AF90,1,&arg);g_ecx=saved;
 busy=0;
}
void ra2_mobile_report(void){
 static uint32_t last;uint32_t now=hle_ticks_ms();
 if(busy||now-last<100)return;last=now;
 int active=ra2_mobile_active(),mode=active?cancel_mode():0;
 char json[8192];int n=snprintf(json,sizeof json,"{\"active\":%d,\"mode\":%d,\"cameos\":[",active,mode),count=0;
 if(active){
  /* Active gadget chain, not every preallocated/hidden cameo. Link +4 is next. */
  uint32_t p=MEM32(0xA40EEC);
  for(int i=0;p&&i<1024&&gm_accessible(p,0x38,0);i++){
   if(MEM32(p)==0x7AB37C&&MEM32(p+0x2C)&&!MEM8(p+0x1E)){
    int x=(int)MEM32(p+0xC),y=(int)MEM32(p+0x10),w=(int)MEM32(p+0x14),h=(int)MEM32(p+0x18);
    if(x>=0&&y>=0&&w>0&&h>0&&w<512&&h<512&&n<7900){n+=snprintf(json+n,sizeof json-n,"%s[%d,%d,%d,%d]",count++?",":"",x,y,w,h);}
   }
   uint32_t next=MEM32(p+4);if(next==p)break;p=next;
  }
 }
 snprintf(json+n,sizeof json-n,"]}");
 MAIN_THREAD_EM_ASM({if(Module.onMobileState)Module.onMobileState(JSON.parse(UTF8ToString($0)));},json);
}
