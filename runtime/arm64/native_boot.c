/* ARM64 game host with optional startup, input and performance probes. */
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "win32hle.h"
#include "pe_loader.h"

static uint32_t host_started_ms;
static void fault(int sig,siginfo_t *si,void *context) {
    (void)context;
    fprintf(stderr,"[native-boot] signal=%d address=%p guest=%08x last_import=%s esp=%08x\n",
            sig,si?si->si_addr:NULL,g_cur_func,g_cur_import?g_cur_import:"none",g_esp);
    _exit(128+sig);
}
static void timeout_handler(int sig) {
    (void)sig;
    fprintf(stderr,"[native-boot] watchdog guest=%08x last_import=%s\n",
            g_cur_func,g_cur_import?g_cur_import:"none");_exit(124);
}
void recomp_not_lifted(uint32_t va) {hle_fatal("function not lifted: %08x",va);}
static void headless_messagebox(void) {
    fprintf(stderr,"[native-boot] game dialog title=%s text=%s buttons=%08x\n",
            ASTR(2)?ASTR(2):"",ASTR(1)?ASTR(1):"",A32(3));
    hle_fatal("game requested a dialog; headless probe stops for diagnosis");
}
/* Capture only the guest framebuffer, never the user's desktop. */
static void capture_frame(const uint8_t *px,int w,int h,int pitch,int bpp) {
    static unsigned frames;frames++;
    static uint32_t first_ms;static unsigned clicked;
    if(!first_ms)first_ms=hle_ticks_ms();
    const char *click=getenv("RA2_PROBE_CLICK");unsigned delay;int cx,cy;
    for(unsigned i=0;click&&i<clicked;i++){click=strchr(click,';');if(click)click++;}
    if(click&&sscanf(click,"%u,%d,%d",&delay,&cx,&cy)==3&&hle_ticks_ms()-first_ms>=delay) {
        clicked++;hle_input_mouse(0x0200,cx,cy);hle_input_mouse(0x0201,cx,cy);hle_input_mouse(0x0202,cx,cy);
        fprintf(stderr,"[native-boot] probe clicked guest coordinates %d,%d\n",cx,cy);
    }
    static int key_sent;const char *key=getenv("RA2_PROBE_KEY");unsigned key_ms,key_vk;
    if(key&&!key_sent&&sscanf(key,"%u,%u",&key_ms,&key_vk)==2&&hle_ticks_ms()-first_ms>=key_ms) {
        key_sent=1;hle_input_key(1,key_vk,0);hle_input_key(0,key_vk,0);
        fprintf(stderr,"[native-boot] probe key vk=%u\n",key_vk);
    }
    /* Optional local test mailbox. It never listens on a network interface. */
    const char *control=getenv("RA2_PROBE_CONTROL_FILE");static unsigned last_command;
    if(control){FILE *in=fopen(control,"r");if(in){unsigned id;char action[16];int a,b;
        if(fscanf(in,"%u %15s %d %d",&id,action,&a,&b)==4&&id>last_command){
            last_command=id;
            if(!strcmp(action,"click")){hle_input_mouse(0x0200,a,b);hle_input_mouse(0x0201,a,b);hle_input_mouse(0x0202,a,b);}
            else if(!strcmp(action,"key")){hle_input_key(1,(uint32_t)a,(uint32_t)b);hle_input_key(0,(uint32_t)a,(uint32_t)b);}
            else hle_fatal("invalid local probe command");
            fprintf(stderr,"[native-boot] control id=%u %s %d %d\n",id,action,a,b);
        }fclose(in);}}
    const char *metrics=getenv("RA2_METRICS_PATH");
    static uint32_t metric_ms;static unsigned metric_frames;
    uint32_t now=hle_ticks_ms();
    if(metrics && (!metric_ms || now-metric_ms>=1000)) {
        FILE *mf=fopen(metrics,"a");if(mf){
            const char *frame_va_text=getenv("RA2_GAME_FRAME_VA");
            uint32_t frame_va=frame_va_text?(uint32_t)strtoul(frame_va_text,NULL,0):0;
            uint32_t game_frame=frame_va&&gm_accessible(frame_va,4,0)?MEM32(frame_va):0;
            fprintf(mf,"{\"monotonic_ms\":%u,\"present_callbacks\":%u,\"interval_ms\":%u,\"interval_frames\":%u,\"host_elapsed_ms\":%u,\"game_frame\":%u}\n",
                    now,frames,metric_ms?now-metric_ms:0,frames-metric_frames,now-host_started_ms,game_frame);fclose(mf);}
        metric_ms=now;metric_frames=frames;
    }
    const char *path=getenv("RA2_FRAME_PATH");
    static uint32_t captured_ms;
    unsigned interval=getenv("RA2_CAPTURE_MS")?(unsigned)strtoul(getenv("RA2_CAPTURE_MS"),NULL,10):1000;
    if(!path || (captured_ms && now-captured_ms<interval))return;
    captured_ms=now;
    size_t size=(size_t)w*h*3;uint8_t *rgb=malloc(size);if(!rgb)return;
    const uint8_t *unused;const uint32_t *palette=NULL;int aw,ah,ap,ab;unsigned seq;
    if(bpp==8)hle_dd_frame(&unused,&aw,&ah,&ap,&ab,&palette,&seq);
    for(int y=0;y<h;y++)for(int x=0;x<w;x++) {
        const uint8_t *p=px+y*pitch+x*(bpp/8);uint8_t *out=rgb+((size_t)y*w+x)*3;
        if(bpp==16){unsigned v=p[0]|p[1]<<8;out[0]=((v>>11)&31)*255/31;out[1]=((v>>5)&63)*255/63;out[2]=(v&31)*255/31;}
        else if(bpp==24||bpp==32){out[0]=p[2];out[1]=p[1];out[2]=p[0];}
        else {unsigned v=palette?palette[*p]:0;out[0]=v&255;out[1]=(v>>8)&255;out[2]=(v>>16)&255;}
    }
    char temporary[4096];
    if(snprintf(temporary,sizeof temporary,"%s.tmp",path)>=(int)sizeof temporary){free(rgb);return;}
    FILE *f=fopen(temporary,"wb");if(!f){free(rgb);return;}
    fprintf(f,"P6\n%d %d\n255\n",w,h);size_t written=fwrite(rgb,1,size,f);int closed=fclose(f);free(rgb);
    if(written==size&&!closed)rename(temporary,path);
    fprintf(stderr,"[native-boot] captured guest frame=%u %dx%d %dbpp\n",frames,w,h,bpp);

}
extern uint32_t ra2_blowfish_create(const uint8_t *,uint32_t *);
int main(int argc,char **argv) {
    host_started_ms=hle_ticks_ms();
    if ((argc!=2 && argc!=3) || !gm_init()) return 2;
    struct sigaction sa={0};sa.sa_sigaction=fault;sa.sa_flags=SA_SIGINFO;
    sigaction(SIGSEGV,&sa,NULL);sigaction(SIGBUS,&sa,NULL);sigaction(SIGABRT,&sa,NULL);
    signal(SIGALRM,timeout_handler);
    const char *seconds=getenv("RA2_PROBE_SECONDS");
    unsigned limit=seconds?(unsigned)strtoul(seconds,NULL,10):20;
    if(limit>3600)return 2;alarm(limit);
    win32hle_register(win32hle_kernel32);
    win32hle_register(win32hle_kernel32_crt);
    win32hle_register(win32hle_kernel32_ext);
    win32hle_register(win32hle_module);
    win32hle_register(win32hle_winmm);
    win32hle_register(win32hle_wsock32);
    win32hle_register(win32hle_ole32);
    win32hle_register(win32hle_storage);
    win32hle_register(win32hle_advapi32);
    static const win32hle_shim diagnostics[]={{"MessageBoxA",headless_messagebox},{0,0}};
    win32hle_register(diagnostics);
    win32hle_register(win32hle_user32);
    win32hle_register(win32hle_ddraw);
    win32hle_register(win32hle_dsound);
    win32hle_register(win32hle_bink);
    win32hle_register(win32hle_gdi32);
    win32hle_register(win32hle_gdidc);
    extern void (*hle_ws_post_message)(uint32_t,uint32_t,uint32_t,uint32_t);
    hle_ws_post_message=hle_post_message;
    hle_screen_frame_hook=capture_frame;
#ifndef __EMSCRIPTEN__
    extern int hle_native_cursor_visible(void);
    hle_screen_cursor_hook=hle_native_cursor_visible;
#endif
    if(hle_screen_open("Red Alert 2 — ARM64 migration",0,0))return 4;
    char game_dir[2048];
    if (!getcwd(game_dir,sizeof game_dir)) return 2;
    hle_set_drive('C',game_dir);
    static const uint8_t blowfish_clsid[]={0x10,0xad,0x40,0x14,0xa8,0x6a,0xd1,0x11,0xb6,0xf9,0,0xa0,0x24,0xdd,0xaf,0xd1};
    hle_com_register_class(blowfish_clsid,ra2_blowfish_create);
    hle_set_command_line("game.exe");
    pe_image image={0};
    if (recomp_pe_map(argv[1],&image)) return 3;
    char guest_path[2048];hle_guest_path(argv[1],guest_path,sizeof guest_path);
    hle_module_add(guest_path,image.base,image.resource_rva,image.resource_size,1);
    if (recomp_pe_bind(&image,hle_resolve_or_stub)) return 3;
    if (argc==3 && !strcmp(argv[2],"--with-launcher")) {
        /* Act as the platform launcher: supply the same named kernel objects,
           not a patched game return value or a forged GetLastError result. */
        char *mutex_name=gm_strdup("48BC11BD-C4D7-466b-8A31-C6ABBAD47B3E");
        char *event_name=gm_strdup("D6E7FC97-64F9-4d28-B52C-754EDF721C6F");
        uint32_t mutex_args[]={0,0,gm_va(mutex_name)};
        uint32_t event_args[]={0,0,0,gm_va(event_name)};
        uint32_t mutex=hle_call_guest(hle_resolve("CreateMutexA"),3,mutex_args);
        uint32_t event=hle_call_guest(hle_resolve("CreateEventA"),4,event_args);
        if (!mutex || !event) hle_fatal("cannot establish launcher kernel objects");
        gm_free(mutex_name);gm_free(event_name);
        fprintf(stderr,"[native-boot] platform launcher objects established; game checks unmodified\n");
    }
    fprintf(stderr,"[native-boot] entering actual game CRT entry %08x as ARM64\n",image.entry);
    win32hle_trace=getenv("RA2_TRACE")?atoi(getenv("RA2_TRACE")):1;
    uint32_t result=hle_call_guest(image.entry,0,NULL);
    fprintf(stderr,"[native-boot] entry returned %08x\n",result);
    return 0;
}
