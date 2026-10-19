/* Browser events are queued on the UI thread and consumed under the guest machine lock. */
#include <stdatomic.h>
#include <stdint.h>
#include <emscripten.h>
#include "win32hle.h"
typedef struct {int kind,a,b,c;} input_event;
extern int hle_web_mouse_pending(void),hle_web_dialog_open(void);
extern void hle_web_reset_input(void);
static int scene,reported=-1,release_gap;
static _Atomic int reset_requested;
static input_event queue[128];
static _Atomic unsigned head,tail;
static int enqueue(input_event e){unsigned h=atomic_load(&head),n=(h+1)%128;if(n==atomic_load_explicit(&tail,memory_order_acquire))return 0;queue[h]=e;atomic_store_explicit(&head,n,memory_order_release);return 1;}
static void reset_input(void) {
 atomic_store_explicit(&tail,atomic_load_explicit(&head,memory_order_acquire),memory_order_release);
 hle_web_reset_input();release_gap=0;
}
EMSCRIPTEN_KEEPALIVE void ra2_web_reset(void){atomic_store(&reset_requested,1);}
void ra2_web_scene(int next){if(scene!=next){scene=next;reset_input();}}
EMSCRIPTEN_KEEPALIVE int ra2_web_mouse(int kind,int x,int y,int button){
 if(kind<0||kind>2||button<0||button>2||x<0||x>8191||y<0||y>8191)return 0;
 return enqueue((input_event){kind,x,y,button});
}
EMSCRIPTEN_KEEPALIVE int ra2_web_key(int down,int vk,int scan){if(vk<0||vk>255)return 0;return enqueue((input_event){3,down,vk,scan});}
void ra2_web_frame(const uint8_t *px,int w,int h,int pitch,int bpp){
 (void)px;(void)w;(void)h;(void)pitch;(void)bpp;
 static int first_frame;
 if(!first_frame){first_frame=1;MAIN_THREAD_ASYNC_EM_ASM({if(typeof Module['onGameFrame']==='function')Module['onGameFrame']();});}
 int phase=scene==2&&hle_web_dialog_open()?3:scene;
 if(phase!=reported){
  reset_input();reported=phase;
  MAIN_THREAD_ASYNC_EM_ASM({if(typeof Module['onInteractionState']==='function')Module['onInteractionState']($0);},phase);
 }
 if(atomic_exchange(&reset_requested,0))reset_input();
 /* A presentation can run inside PeekMessage before the previous mouse-up
  * has been removed from USER32. Do not move the global cursor to tap B while
  * tap A is still waiting in that queue. Keep one neutral presentation after
  * release as well, for the game's polled button state. */
 if(hle_web_mouse_pending())return;
 if(release_gap){release_gap=0;return;}
 unsigned t=atomic_load(&tail),hnow=atomic_load_explicit(&head,memory_order_acquire);
 while(t!=hnow){input_event e=queue[t];t=(t+1)%128;
  if(e.kind==3)hle_input_key(e.a!=0,(uint32_t)e.b,(uint32_t)e.c);
  else{uint32_t message=e.kind==0?0x200:(e.c==2?(e.kind==1?0x204:0x205):(e.kind==1?0x201:0x202));hle_input_mouse(message,e.a,e.b);}
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
  if(e.kind==2)release_gap=1;
  if(e.kind!=0)break;
 }
 atomic_store_explicit(&tail,t,memory_order_release);
}
