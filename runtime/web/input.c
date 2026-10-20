/* Browser events are queued on the UI thread and consumed under the guest machine lock. */
#include <stdatomic.h>
#include <stdint.h>
#include <emscripten.h>
#include "win32hle.h"
typedef struct {int kind,a,b,c;} input_event;
/* Larger burst capacity; adjacent motion is consumed without crossing buttons. */
static input_event queue[1024];
static _Atomic unsigned head,tail;
extern unsigned hle_web_mouse_completed;
static unsigned wait_completed;
static uint32_t wait_started;
static int waiting_button;
extern void hle_web_resolution_reply(uint32_t,int);
extern void ra2_mobile_report(void),ra2_mobile_cancel(int);

static int enqueue(input_event e){unsigned h=atomic_load(&head),n=(h+1)%1024;if(n==atomic_load_explicit(&tail,memory_order_acquire))return 0;queue[h]=e;atomic_store_explicit(&head,n,memory_order_release);return 1;}
EMSCRIPTEN_KEEPALIVE int ra2_web_mouse(int kind,int x,int y,int button){
 if(kind<0||kind>2||button<0||button>2||x<0||x>8191||y<0||y>8191)return 0;
 return enqueue((input_event){kind,x,y,button});
}
EMSCRIPTEN_KEEPALIVE int ra2_web_key(int down,int vk,int scan){if(vk<0||vk>255)return 0;return enqueue((input_event){3,down,vk,scan});}
EMSCRIPTEN_KEEPALIVE int ra2_web_cancel(int mode){return enqueue((input_event){4,mode,0,0});}
EMSCRIPTEN_KEEPALIVE int ra2_web_resolution_reply(int hwnd,int accept){return enqueue((input_event){5,hwnd,accept!=0,0});}
void ra2_web_frame(const uint8_t *px,int w,int h,int pitch,int bpp){
 (void)px;(void)w;(void)h;(void)pitch;(void)bpp;
 static int first_frame;
 if(!first_frame){first_frame=1;MAIN_THREAD_ASYNC_EM_ASM({if(typeof Module['onGameFrame']==='function')Module['onGameFrame']();});}
}
void ra2_web_pump_input(void){
 ra2_mobile_report();
 /* Wait only for the button we sent, never for unrelated queued motion.
  * A filtered or destroyed-window message must not freeze menu input. */
 if(waiting_button){
  if(hle_web_mouse_completed==wait_completed && hle_ticks_ms()-wait_started<128)return;
  waiting_button=0;
 }
 unsigned t=atomic_load(&tail),hnow=atomic_load_explicit(&head,memory_order_acquire);
 while(t!=hnow){input_event e=queue[t];t=(t+1)%1024;
  if(e.kind==5){hle_web_resolution_reply((uint32_t)e.a,e.b);break;}
  if(e.kind==4){ra2_mobile_cancel(e.a);break;}
  if(e.kind==3)hle_input_key(e.a!=0,(uint32_t)e.b,(uint32_t)e.c);
  else{uint32_t message=e.kind==0?0x200:(e.c==2?(e.kind==1?0x204:0x205):(e.kind==1?0x201:0x202));hle_input_mouse(message,e.a,e.b);
   if(e.kind!=0){waiting_button=1;wait_completed=hle_web_mouse_completed;wait_started=hle_ticks_ms();}
  }
  /* Apply a diagonal's adjacent arrow transitions together. Splitting them
   * across presentations makes a two-finger diagonal drag visibly staircase.
   * Opposite transitions still wait, preserving a short pulse for a full tick. */
  if(e.kind==3&&e.b>=37&&e.b<=40&&t!=hnow){
   input_event next=queue[t];
   if(next.kind==3&&next.a==e.a&&next.b>=37&&next.b<=40)continue;
  }
  /* Let the guest consume each button/key transition before applying its
   * release. Touch taps can enqueue both in the same browser task. This also
   * lets WM_*BUTTONDOWN establish capture before hit-testing the release. */
  /* A teleport to a new touch position must be visible while released,
   * BEFORE DOWN. Previously MOVE and DOWN shared one presentation: the
   * game could observe the new position only with the button already held.
   * Coalesce adjacent moves, but never cross a button boundary. */
  if(e.kind==0 && t!=hnow && queue[t].kind==0)continue;
  break;
 }
 atomic_store_explicit(&tail,t,memory_order_release);
}
