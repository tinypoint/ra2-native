/* Integration tests using the adapted upstream Win32 HLE and actual lifted
 * functions. No game bytes are embedded in this file. */
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "win32hle.h"
#include "pe_loader.h"
extern uint32_t ra2_blowfish_create(const uint8_t *,uint32_t *);

static unsigned checks,failures,implemented,stubs;
/* Original synthetic stdcall callback used only to exercise real winmm timers. */
void runtime_timer_callback(void) {
    uint32_t user=MEM32(g_esp+12);
    MEM32(user)++;
    g_eax=0;g_esp+=24;
}
void runtime_thread_callback(void) {
    uint32_t user=MEM32(g_esp+4);MEM32(user)=hle_thread_id();
    g_eax=0x1234;g_esp+=8;
}
static unsigned window_create_ok;
static uint32_t expected_class;
void runtime_window_callback(void) {
    uint32_t msg=MEM32(g_esp+8),l=MEM32(g_esp+16);
    if(msg==0x81 || msg==1) {
        if(gm_accessible(l,48,0) && !strcmp(gm_ptr(MEM32(l+36)),"ARM64 window") &&
           (MEM32(l+40)==expected_class || (MEM32(l+40)>=0x10000 && !strcmp(gm_ptr(MEM32(l+40)),"RuntimeTest"))))window_create_ok++;
    }
    g_eax=1;g_esp+=20;
}
static void check(const char *name,int condition) {
    checks++;if (!condition) {failures++;fprintf(stderr,"FAIL %s\n",name);}
}
static uint32_t api(const char *name,int argc,const uint32_t *args) {
    uint32_t va=hle_resolve(name);
    if (!va) {fprintf(stderr,"Missing API %s\n",name);exit(2);}
    return hle_call_guest(va,argc,args);
}
static uint32_t resolve(const char *name) {
    if (hle_resolve(name)) implemented++;else stubs++;
    return hle_resolve_or_stub(name);
}
static uint32_t com_api(uint32_t obj,int slot,int n,const uint32_t *args) {
    uint32_t values[10]={obj};for(int i=0;i<n;i++)values[i+1]=args[i];
    return hle_call_guest(MEM32(MEM32(obj)+slot*4),n+1,values);
}
static uint16_t *widecopy(const char *text) {
    size_t n=strlen(text);uint16_t *w=gm_calloc(n+1,2);
    for(size_t i=0;i<n;i++)w[i]=(uint8_t)text[i];return w;
}
static void storage_checks(void) {
    char name[96];snprintf(name,sizeof name,"C:\\.native-storage-%ld.cfb",(long)getpid());
    uint16_t *path=widecopy(name),*sub=widecopy("Scenario"),*small=widecopy("Header"),*big=widecopy("Data");
    uint32_t *out=gm_calloc(4,4);uint32_t create[]={gm_va(path),0x1012,0,gm_va(out)};
    check("StgCreateDocfile returns guest COM",api("StgCreateDocfile",4,create)==0 && out[0]);
    uint32_t root=out[0],nested=0,stream=0;
    if(root){
        uint8_t *clsid=gm_alloc(16);for(int i=0;i<16;i++)clsid[i]=(uint8_t)(i+1);
        uint32_t *stat=gm_calloc(18,4),class_args[]={gm_va(clsid)},stat_args[]={gm_va(stat),1};
        check("IStorage SetClass",com_api(root,15,1,class_args)==0);
        check("PE32 STATSTG CLSID layout",com_api(root,17,2,stat_args)==0 && !memcmp((uint8_t*)stat+48,clsid,16) && stat[0]==0);
        gm_free(clsid);gm_free(stat);
        uint32_t args[]={gm_va(sub),0x12,0,0,gm_va(out+1)};
        check("IStorage creates nested storage",com_api(root,5,5,args)==0 && out[1]);nested=out[1];
        args[0]=gm_va(small);args[4]=gm_va(out+2);
        check("IStorage creates small stream",com_api(nested,3,5,args)==0 && out[2]);stream=out[2];
        char *hello=gm_strdup("ARM64 CFB stream");uint32_t write[]={gm_va(hello),17,gm_va(out+3)};
        check("IStream writes guest small payload",com_api(stream,4,3,write)==0 && out[3]==17);com_api(stream,2,0,NULL);
        uint8_t *data=gm_alloc(10000),*back=gm_alloc(10000);for(int i=0;i<10000;i++)data[i]=(uint8_t)(i*7);
        args[0]=gm_va(big);check("IStorage creates regular FAT stream",com_api(nested,3,5,args)==0 && out[2]);stream=out[2];
        write[0]=gm_va(data);write[1]=10000;check("IStream writes large payload",com_api(stream,4,3,write)==0 && out[3]==10000);
        com_api(stream,2,0,NULL);com_api(nested,2,0,NULL);uint32_t commit_args[]={0};
        check("IStorage Commit writes compound file",com_api(root,9,1,commit_args)==0);com_api(root,2,0,NULL);
        uint32_t open[]={gm_va(path),0,0x10,0,0,gm_va(out)};
        check("StgOpenStorage reopens committed disk file",api("StgOpenStorage",6,open)==0 && out[0]);root=out[0];
        uint32_t open_sub[]={gm_va(sub),0,0x10,0,0,gm_va(out+1)};
        check("IStorage reopens nested storage",com_api(root,6,6,open_sub)==0 && out[1]);nested=out[1];
        uint32_t open_stream[]={gm_va(small),0,0x10,0,gm_va(out+2)};
        check("IStorage reopens mini stream",com_api(nested,4,5,open_stream)==0 && out[2]);stream=out[2];
        uint32_t read[]={gm_va(back),10000,gm_va(out+3)};
        check("small stream round trip and EOF status",com_api(stream,3,3,read)==1 && out[3]==17 && !memcmp(back,hello,17));com_api(stream,2,0,NULL);
        open_stream[0]=gm_va(big);check("IStorage reopens big stream",com_api(nested,4,5,open_stream)==0 && out[2]);stream=out[2];
        check("large stream disk round trip",com_api(stream,3,3,read)==0 && out[3]==10000 && !memcmp(back,data,10000));
        check("read-only structured storage rejects Write",com_api(stream,4,3,write)==0x80030005);
        com_api(stream,2,0,NULL);com_api(nested,2,0,NULL);com_api(root,2,0,NULL);
        gm_free(hello);gm_free(data);gm_free(back);
    }
    char *ansi=gm_strdup(name);uint32_t remove[]={gm_va(ansi)};check("compound test file removed",api("DeleteFileA",1,remove)==1);gm_free(ansi);
    uint16_t *bad=widecopy("C:\\.native-storage-missing-dir\\no-file.cfb");create[0]=gm_va(bad);out[0]=0xdeadbeef;
    check("StgCreateDocfile reports actual disk failure",api("StgCreateDocfile",4,create)==0x8003001d && out[0]==0);
    gm_free(bad);gm_free(out);gm_free(path);gm_free(sub);gm_free(small);gm_free(big);
}
typedef struct {uint32_t tib,stack;int okay;} thread_result;
static void *thread_check(void *arg) {
    thread_result *r=arg;
    mach_enter();r->tib=g_fs_base;r->stack=g_esp;
    g_xmm[0].u32[0]=r->tib;g_mxcsr=0x3f80;
    g_flag_k=FK_EFLAGS;g_flag_a=0x247;g_flag_b=0;g_flag_cf=1;
    uint32_t args[]={1};
    for (int i=0;i<12;i++) {
        api("Sleep",1,args);
        if (g_xmm[0].u32[0]!=r->tib || g_mxcsr!=0x3f80 || g_flag_a!=0x247 ||
            g_fs_base!=r->tib || g_esp!=r->stack) {r->okay=0;mach_leave();return NULL;}
    }
    r->okay=1;mach_leave();return NULL;
}

int main(int argc,char **argv) {
    if (argc!=2 || !gm_init()) return 2;
    win32hle_register(win32hle_kernel32);
    win32hle_register(win32hle_kernel32_crt);
    win32hle_register(win32hle_kernel32_ext);
    win32hle_register(win32hle_module);
    win32hle_register(win32hle_winmm);
    win32hle_register(win32hle_wsock32);
    win32hle_register(win32hle_ole32);
    win32hle_register(win32hle_storage);
    win32hle_register(win32hle_advapi32);
    win32hle_register(win32hle_user32);win32hle_register(win32hle_ddraw);
    win32hle_register(win32hle_gdi32);win32hle_register(win32hle_gdidc);
    win32hle_register(win32hle_dsound);win32hle_register(win32hle_bink);
    char game_dir[2048];snprintf(game_dir,sizeof game_dir,"%s",argv[1]);
    char *slash=strrchr(game_dir,'/');if (!slash) return 2;*slash=0;
    hle_set_drive('C',game_dir);
    check("64-bit host",sizeof(void*)==8);
    check("guest base above 4 GiB",(uintptr_t)g_mem_base>UINT32_MAX);
    check("null translation",gm_ptr(0)==NULL && gm_va(NULL)==0);
    check("null page inaccessible",!gm_accessible(0,4,0));
    pe_image image={0};
    check("actual PE loads",recomp_pe_map(argv[1],&image)==0);
    check("actual entry preserved",image.base==0x00400000 && image.entry==0x00785aa0);
    check("PE signature",MEM16(image.base)==0x5a4d);
    hle_module_add("game.exe",image.base,image.resource_rva,image.resource_size,1);
    pe_image collision={0};
    check("overlapping image rejected",recomp_pe_map(argv[1],&collision)!=0);
    check("imports bound",recomp_pe_bind(&image,resolve)==0);

    mach_enter();
    uint32_t stack=g_esp,tib=g_fs_base;
    check("TIB self is guest VA",MEM32(tib+0x18)==tib);
    check("stack is mapped guest memory",gm_accessible(stack-64,64,1));
    uint32_t alloc_args[]={1,8,64};
    uint32_t p=api("HeapAlloc",3,alloc_args);
    check("HeapAlloc returns guest VA",p && gm_va(gm_ptr(p))==p);
    check("HeapAlloc host pointer remains above 4 GiB",(uintptr_t)gm_ptr(p)>UINT32_MAX);
    int zero=1;for (int i=0;i<64;i++) if (MEM8(p+i)) zero=0;
    check("HEAP_ZERO_MEMORY",zero);
    memcpy(gm_ptr(p),"native ARM64",13);
    uint32_t string_args[]={p};
    check("real lstrlenA reads guest string",api("lstrlenA",1,string_args)==12);
    uint32_t resize[]={1,8,p,256};uint32_t q=api("HeapReAlloc",4,resize);
    check("HeapReAlloc preserves content",q && !strcmp(gm_ptr(q),"native ARM64"));
    zero=1;for (int i=64;i<256;i++) if (MEM8(q+i)) zero=0;
    check("HeapReAlloc zero extension",zero);
    uint32_t size_args[]={1,0,q};check("HeapSize",api("HeapSize",3,size_args)==256);
    check("HeapFree",api("HeapFree",3,size_args)==1);
    check("freed guest block inaccessible",!gm_accessible(q,1,0));
    hle_set_command_line("game.exe -native-test");
    uint32_t cmd=api("GetCommandLineA",0,NULL);
    check("command line copied into guest memory",cmd && !strcmp(gm_ptr(cmd),"game.exe -native-test"));
    uint32_t env=api("GetEnvironmentStrings",0,NULL);
    check("environment block is guest memory",env && !strncmp(gm_ptr(env),"PATH=",5));
    uint32_t env_args[]={env};check("environment block freed",api("FreeEnvironmentStringsA",1,env_args)==1 && !gm_accessible(env,1,0));
    uint32_t *system=hle_alloc(40);uint32_t system_args[]={gm_va(system)};
    api("GetSystemInfo",1,system_args);
    check("SYSTEM_INFO advertises actual guest page granule",system[1]==gm_page_size());
    hle_free(system);
    uint32_t main_args[]={0};check("GetModuleHandleA main",api("GetModuleHandleA",1,main_args)==image.base);
    char *kernel=gm_strdup("kernel32.dll"),*version=gm_strdup("GetVersion");
    uint32_t module_args[]={gm_va(kernel)};uint32_t module=api("GetModuleHandleA",1,module_args);
    uint32_t proc_args[]={module,gm_va(version)};uint32_t proc=api("GetProcAddress",2,proc_args);
    check("dynamic import returns shim VA",module && proc && proc==hle_resolve("GetVersion"));
    check("dynamic import can be called",hle_call_guest(proc,0,NULL)==(5u|(1u<<8)|(2600u<<16)));
    gm_free(kernel);gm_free(version);
    char guest_file[2048];hle_guest_path(argv[1],guest_file,sizeof guest_file);
    char *path=gm_strdup(guest_file);char *bytes=hle_alloc(32);uint32_t *written=hle_alloc(4);
    uint32_t open_args[]={gm_va(path),0x80000000,1,0,3,0x80,0};
    uint32_t file=api("CreateFileA",7,open_args);
    check("CreateFileA resolves Windows game path",file!=0xffffffff && file!=0);
    uint32_t read_args[]={file,gm_va(bytes),2,gm_va(written),0};
    check("ReadFile writes guest buffer and count",api("ReadFile",5,read_args)==1 && *written==2 && bytes[0]=='M' && bytes[1]=='Z');
    uint32_t *times=hle_alloc(24);uint32_t time_args[]={file,gm_va(times),gm_va(times+2),gm_va(times+4)};
    check("Darwin file timestamps translate",api("GetFileTime",4,time_args)==1 && times[5]!=0);
    uint32_t close_args[]={file};check("CloseHandle",api("CloseHandle",1,close_args)==1);
    hle_free(times);hle_free(bytes);hle_free(written);gm_free(path);
    char *persist_path=gm_strdup("C:\\.native-hle-write-check.tmp");
    uint32_t persist_open[]={gm_va(persist_path),0xc0000000,0,0,1,0x80,0};
    uint32_t persisted=api("CreateFileA",7,persist_open);
    check("write fixture created without overwriting",persisted!=0xffffffff && persisted!=0);
    if(persisted!=0xffffffff && persisted) {
        char *payload=gm_strdup("ARM64 write/read");uint32_t *count=gm_calloc(1,4);
        uint32_t write_args[]={persisted,gm_va(payload),17,gm_va(count),0};
        check("WriteFile writes full guest payload",api("WriteFile",5,write_args)==1 && *count==17);
        uint32_t sync_args[]={persisted};check("FlushFileBuffers syncs native file",api("FlushFileBuffers",1,sync_args)==1);
        api("CloseHandle",1,sync_args);persist_open[1]=0x80000000;persist_open[4]=3;
        persisted=api("CreateFileA",7,persist_open);memset(payload,0,17);write_args[0]=persisted;
        check("disk payload survives close and reopen",api("ReadFile",5,write_args)==1 && *count==17 && !memcmp(payload,"ARM64 write/read",17));
        sync_args[0]=persisted;api("CloseHandle",1,sync_args);uint32_t delete_args[]={gm_va(persist_path)};
        check("temporary disk fixture removed",api("DeleteFileA",1,delete_args)==1);gm_free(payload);gm_free(count);
    }
    uint32_t bad_sync[]={0xffffffff};
    check("FlushFileBuffers rejects invalid handle",api("FlushFileBuffers",1,bad_sync)==0 && api("GetLastError",0,NULL)==6);
    gm_free(persist_path);
    storage_checks();
    uint8_t *wsa=hle_alloc(400);uint32_t wsa_args[]={0x101,gm_va(wsa)};
    check("ordinal WSAStartup resolves",hle_resolve("wsock32.dll#115")==hle_resolve("WSAStartup") ||
          hle_resolve("wsock32.dll#115")!=0);
    check("WSAStartup writes PE32 WSADATA",api("WSAStartup",2,wsa_args)==0 && wsa[0]==1 && wsa[1]==1);
    uint32_t addr_args[]={0x0100007f};uint32_t address=api("inet_ntoa",1,addr_args);
    check("inet_ntoa returns guest string",address && !strcmp(gm_ptr(address),"127.0.0.1"));
    char *localhost=gm_strdup("localhost");uint32_t host_args[]={gm_va(localhost)};
    uint32_t host=api("gethostbyname",1,host_args);
    check("hostent and nested pointers are guest addresses",host && MEM16(host+8)==2 &&
          gm_accessible(MEM32(host),1,0) && gm_accessible(MEM32(MEM32(host+12)),4,0));
    gm_free(localhost);
    check("WSACleanup",api("WSACleanup",0,NULL)==0);hle_free(wsa);
    uint32_t ole_args[]={0};check("OleInitialize",api("OleInitialize",1,ole_args)==0);
    static const win32hle_shim unknown[]={
        {"test.IUnknown.QueryInterface",hle_com_QueryInterface},
        {"test.IUnknown.AddRef",hle_com_AddRef},
        {"test.IUnknown.Release",hle_com_Release},{0,0}};
    uint32_t vt=hle_com_vtable(unknown),com=hle_com_new(vt,16),self[]={com};
    check("COM object and vtable use guest addresses",com && MEM32(com)==vt && MEM32(com+4)==1);
    check("COM AddRef through shim dispatch",hle_call_guest(MEM32(vt+4),1,self)==2);
    check("COM Release keeps referenced object",hle_call_guest(MEM32(vt+8),1,self)==1 && gm_accessible(com,8,0));
    check("COM final Release frees guest object",hle_call_guest(MEM32(vt+8),1,self)==0 && !gm_accessible(com,1,0));
    uint16_t *wide=hle_alloc(8);wide[0]='R';wide[1]='A';wide[2]='2';wide[3]=0;
    uint32_t wide_args[]={gm_va(wide)};uint32_t bstr=api("SysAllocString",1,wide_args);
    check("BSTR retains PE32 length prefix",bstr && MEM32(bstr-4)==6 && MEM16(bstr+4)=='2');
    uint32_t bstr_args[]={bstr};api("SysFreeString",1,bstr_args);
    check("BSTR frees correct guest allocation",!gm_accessible(bstr,1,0));hle_free(wide);
    uint32_t cipher=0;
    check("Blowfish creates from uploaded DLL tables",ra2_blowfish_create(NULL,&cipher)==0 && cipher);
    uint32_t *key=hle_alloc(16),*plaintext=hle_alloc(8),*ciphertext=hle_alloc(8),*decoded=hle_alloc(8);
    uint32_t cipher_vt=MEM32(cipher),key_args[]={cipher,8,gm_va(key)};
    check("Blowfish SetKey through COM",hle_call_guest(MEM32(cipher_vt+12),3,key_args)==0);
    uint32_t encrypt_args[]={cipher,8,gm_va(plaintext),gm_va(ciphertext)};
    hle_call_guest(MEM32(cipher_vt+24),4,encrypt_args);
    static const uint8_t expected[]={0x4e,0xf9,0x97,0x45,0x61,0x98,0xdd,0x78};
    check("Blowfish matches independent zero-key vector",!memcmp(ciphertext,expected,8));
    uint32_t decrypt_args[]={cipher,8,gm_va(ciphertext),gm_va(decoded)};
    hle_call_guest(MEM32(cipher_vt+28),4,decrypt_args);
    check("Blowfish decrypts reference ciphertext",!memcmp(decoded,plaintext,8));
    uint32_t cipher_self[]={cipher};hle_call_guest(MEM32(cipher_vt+8),1,cipher_self);
    check("Blowfish object and state release",!gm_accessible(cipher,1,0));
    hle_free(key);hle_free(plaintext);hle_free(ciphertext);hle_free(decoded);
    hle_reg_set_dword(0x80000002u,"Software\\RA2NativeTest","Version",0x10006);
    char *regpath=gm_strdup("Software\\RA2NativeTest"),*regname=gm_strdup("Version");
    uint32_t *regout=hle_alloc(20);
    uint32_t regopen[]={0x80000002u,gm_va(regpath),0,0x20019,gm_va(regout)};
    check("RegOpenKeyExA returns typed native-backed handle",api("RegOpenKeyExA",5,regopen)==0 && regout[0]);
    regout[3]=1;uint32_t queryreg[]={regout[0],gm_va(regname),0,gm_va(regout+1),gm_va(regout+2),gm_va(regout+3)};
    check("registry reports required data size",api("RegQueryValueExA",6,queryreg)==234 && regout[3]==4);
    check("registry value writes guest type/data",api("RegQueryValueExA",6,queryreg)==0 && regout[1]==4 && regout[2]==0x10006);
    uint32_t regclose[]={regout[0]};check("RegCloseKey",api("RegCloseKey",1,regclose)==0);
    hle_free(regout);gm_free(regname);gm_free(regpath);
    uint32_t *timer_count=hle_alloc(4);
    uint32_t timer_args[]={5,1,0x00ef0000,gm_va(timer_count),1};
    uint32_t timer=api("timeSetEvent",5,timer_args);uint32_t sleep_args[]={10};
    for (int i=0;i<20 && !*timer_count;i++) api("Sleep",1,sleep_args);
    check("multimedia timer runs explicit guest callback",timer && *timer_count>0);
    uint32_t kill_args[]={timer};check("timeKillEvent",api("timeKillEvent",1,kill_args)==0);
    uint32_t stopped=*timer_count;api("Sleep",1,sleep_args);
    check("killed timer does not call freed state",*timer_count==stopped);
    hle_free(timer_count);
    uint32_t *thread_data=hle_alloc(16);
    uint32_t create_thread[]={0,0,0x00ef0010,gm_va(thread_data),4,gm_va(thread_data+1)};
    uint32_t th=api("CreateThread",6,create_thread),wait_thread[]={th,0};
    check("suspended thread has stable guest ID",th && thread_data[1] && thread_data[0]==0);
    check("suspended thread is not signaled",api("WaitForSingleObject",2,wait_thread)==258);
    uint32_t resume_thread[]={th};check("ResumeThread",api("ResumeThread",1,resume_thread)==1);
    wait_thread[1]=5000;
    check("WaitForSingleObject observes thread completion",api("WaitForSingleObject",2,wait_thread)==0);
    check("thread callback sees the returned guest ID",thread_data[0]==thread_data[1]);
    uint32_t exit_thread[]={th,gm_va(thread_data+2)};
    check("GetExitCodeThread",api("GetExitCodeThread",2,exit_thread)==1 && thread_data[2]==0x1234);
    check("CloseHandle releases completed thread",api("CloseHandle",1,resume_thread)==1);
    hle_free(thread_data);
    uint32_t reserve_args[]={0,32768,0x2000,4};
    uint32_t va=api("VirtualAlloc",4,reserve_args);
    uint32_t query[7];gm_query(va,query);
    check("reserve is not committed",va && query[4]==0x2000 && !gm_accessible(va,1,0));
    uint32_t commit_args[]={va,16384,0x1000,4};
    check("commit first page",api("VirtualAlloc",4,commit_args)==va && gm_accessible(va,16384,1));
    check("neighbor remains reserved",!gm_accessible(va+16384,1,0));
    MEM32(va)=0x12345678;
    uint32_t decommit_args[]={va,16384,0x4000};
    check("decommit",api("VirtualFree",3,decommit_args)==1 && !gm_accessible(va,1,0));
    check("recommit zeroes memory",api("VirtualAlloc",4,commit_args)==va && MEM32(va)==0);
    uint32_t *old=hle_alloc(4);uint32_t protect_args[]={va,16384,2,gm_va(old)};
    check("read-only protection",api("VirtualProtect",4,protect_args)==1 && *old==4 && gm_accessible(va,1,0) && !gm_accessible(va,1,1));
    uint32_t badwrite[]={va,1};check("IsBadWritePtr sees protection",api("IsBadWritePtr",2,badwrite)==1);
    protect_args[0]=va+4096;protect_args[1]=4096;
    check("unsupported sub-host-page protection fails",api("VirtualProtect",4,protect_args)==0);
    uint32_t release_args[]={va,0,0x8000};check("release",api("VirtualFree",3,release_args)==1);
    check("double release fails",api("VirtualFree",3,release_args)==0);
    hle_free(old);

    uint32_t *object=hle_alloc(4096),*out=hle_alloc(16);
    uint32_t object_va=gm_va(object),out_va=gm_va(out);
    MEM32(object_va+0x88)=0xffffff00;MEM32(object_va+0x8c)=256;MEM32(object_va+0x90)=37;
    g_ecx=object_va;uint32_t args[]={out_va};
    check("real game function through HLE callback",hle_call_guest(0x005d4e40,1,args)==out_va && out[0]==0xffffff00 && out[1]==256 && out[2]==37);
    hle_call_guest(0x0041b320,1,args);
    check("real coordinate conversion through HLE",out[0]==0x0001ffff);
    g_flag_k=FK_EFLAGS;g_flag_a=0x247;g_flag_b=0;g_flag_cf=1;
    g_xmm[0].u32[0]=0x12345678;
    hle_call_guest(0x005d4e40,1,args);
    check("callback restores flags and SIMD state",g_flag_k==FK_EFLAGS && g_flag_a==0x247 && g_xmm[0].u32[0]==0x12345678);
    check("callback restores caller stack and TIB",g_esp==stack && g_fs_base==tib);
    hle_free(object);hle_free(out);
    char *mutex_name=gm_strdup("runtime.named.mutex");uint32_t mutex_args[]={0,0,gm_va(mutex_name)};
    uint32_t m1=api("CreateMutexA",3,mutex_args),m2=api("CreateMutexA",3,mutex_args);
    check("named mutex gets independent handles",m1 && m2 && m1!=m2 && api("GetLastError",0,NULL)==183);
    uint32_t close_mutex[]={m1};api("CloseHandle",1,close_mutex);
    uint32_t open_mutex[]={0,0,gm_va(mutex_name)};uint32_t m3=api("OpenMutexA",3,open_mutex);
    check("closing original handle preserves shared mutex",m3 && m3!=m2);
    close_mutex[0]=m2;api("CloseHandle",1,close_mutex);close_mutex[0]=m3;api("CloseHandle",1,close_mutex);
    check("last close removes named mutex",api("OpenMutexA",3,open_mutex)==0);
    gm_free(mutex_name);
    uint32_t eventargs[]={0,0,1,0};uint32_t event_a=api("CreateEventA",4,eventargs);
    eventargs[2]=0;uint32_t event_b=api("CreateEventA",4,eventargs);
    uint32_t *events=gm_calloc(2,4);events[0]=event_a;events[1]=event_b;
    uint32_t waitallargs[]={2,gm_va(events),1,0};
    check("WaitAll timeout leaves signaled auto-event intact",api("WaitForMultipleObjects",4,waitallargs)==258);
    uint32_t one_event[]={event_a,0};check("WaitAll never partially consumes",api("WaitForSingleObject",2,one_event)==0);
    uint32_t seteventargs[]={event_a};api("SetEvent",1,seteventargs);seteventargs[0]=event_b;api("SetEvent",1,seteventargs);
    check("WaitAll consumes only when all objects ready",api("WaitForMultipleObjects",4,waitallargs)==0 && api("WaitForSingleObject",2,one_event)==258);
    uint32_t close_event[]={event_a};api("CloseHandle",1,close_event);close_event[0]=event_b;api("CloseHandle",1,close_event);gm_free(events);
    char *class_name=gm_strdup("RuntimeTest"),*title=gm_strdup("ARM64 window");
    uint32_t *wc=gm_calloc(10,4);wc[1]=0x00ef0020;wc[9]=gm_va(class_name);
    uint32_t reg_args[]={gm_va(wc)};uint32_t atom=api("RegisterClassA",1,reg_args);
    check("register native guest window class",atom!=0);expected_class=atom;
    uint32_t create_args[]={0,atom,gm_va(title),0,0,0,640,480,0,0,0,0};
    uint32_t hwnd=api("CreateWindowExA",12,create_args);
    check("window callbacks receive nested guest CREATESTRUCT",hwnd && window_create_ok==2);
    uint32_t destroy_args[]={hwnd};api("DestroyWindow",1,destroy_args);
    gm_free(wc);gm_free(class_name);gm_free(title);
    char *fmt=gm_strdup("%08X %s %d %%"),*word=gm_strdup("guest"),*formatted=gm_alloc(1024);
    uint32_t *fa=gm_calloc(3,4);fa[0]=0xabcdef;fa[1]=gm_va(word);fa[2]=(uint32_t)-7;
    uint32_t format_args[]={gm_va(formatted),gm_va(fmt),gm_va(fa)};
    check("formatter reads guest varargs on ARM64",api("wvsprintfA",3,format_args)==19 && !strcmp(formatted,"00ABCDEF guest -7 %"));
    gm_free(fa);gm_free(formatted);gm_free(fmt);gm_free(word);
    uint32_t *ddout=gm_calloc(1,4);uint32_t ddargs[]={0,gm_va(ddout),0};
    check("DirectDraw COM object",api("DirectDrawCreate",3,ddargs)==0 && *ddout);
    uint32_t dd=*ddout,ddvt=MEM32(dd);uint32_t modeargs[]={dd,640,480,16};
    check("DirectDraw native display mode",hle_call_guest(MEM32(ddvt+21*4),4,modeargs)==0);
    uint32_t *desc=gm_calloc(27,4);desc[0]=108;desc[1]=1|2|4;desc[2]=8;desc[3]=16;desc[26]=0x40;
    uint32_t surface_args[]={dd,gm_va(desc),gm_va(ddout),0};
    check("DirectDraw software surface",hle_call_guest(MEM32(ddvt+6*4),4,surface_args)==0 && *ddout);
    uint32_t sf=*ddout,sddvt=MEM32(sf);uint32_t lockargs[]={sf,0,gm_va(desc),0,0};
    check("DirectDraw Lock returns guest pixels",hle_call_guest(MEM32(sddvt+25*4),5,lockargs)==0 && gm_accessible(desc[9],16*8*2,1));
    uint32_t pixels=desc[9];MEM16(pixels)=0xf800;uint32_t sfargs[]={sf};
    check("DirectDraw Release frees guest pixels",hle_call_guest(MEM32(sddvt+2*4),1,sfargs)==0 && !gm_accessible(pixels,1,0));
    uint8_t *external=gm_calloc(256,1);memset(desc,0,108);desc[0]=108;desc[1]=1|2|4|0x800;desc[2]=8;desc[3]=16;desc[9]=gm_va(external);desc[26]=0x40;
    hle_call_guest(MEM32(ddvt+6*4),4,surface_args);sfargs[0]=*ddout;sddvt=MEM32(*ddout);
    hle_call_guest(MEM32(sddvt+2*4),1,sfargs);
    check("DirectDraw preserves externally owned pixels",gm_accessible(gm_va(external),256,1));
    gm_free(external);gm_free(desc);gm_free(ddout);
    setenv("SDL_AUDIODRIVER","dummy",1);
    uint32_t *dsout=gm_calloc(1,4);uint32_t dsargs[]={0,gm_va(dsout),0};
    check("DirectSound creates native mixer device",api("DirectSoundCreate",3,dsargs)==0 && *dsout);
    uint32_t ds=*dsout,dsvt=MEM32(ds);uint32_t *dsdesc=gm_calloc(5,4);
    dsdesc[0]=20;dsdesc[2]=4096;uint32_t dsbufferargs[]={ds,gm_va(dsdesc),gm_va(dsout),0};
    check("DirectSound creates PCM buffer",hle_call_guest(MEM32(dsvt+3*4),4,dsbufferargs)==0 && *dsout);
    uint32_t dsbuffer=*dsout,bvt=MEM32(dsbuffer);uint32_t *dslock=gm_calloc(4,4);
    uint32_t dslockargs[]={dsbuffer,0,64,gm_va(dslock),gm_va(dslock+1),gm_va(dslock+2),gm_va(dslock+3),0};
    check("DirectSound Lock returns guest PCM memory",hle_call_guest(MEM32(bvt+11*4),8,dslockargs)==0 && dslock[1]==64 && gm_accessible(dslock[0],64,1));
    uint32_t dsrelease[]={dsbuffer};hle_call_guest(MEM32(bvt+2*4),1,dsrelease);
    dsrelease[0]=ds;hle_call_guest(MEM32(dsvt+2*4),1,dsrelease);
    gm_free(dsdesc);gm_free(dslock);gm_free(dsout);
    char *absent_movie=gm_strdup("C:\\nonexistent-movie.bik");uint32_t movieargs[]={gm_va(absent_movie),0};
    check("Bink missing movie returns failure",api("_BinkOpen@8",2,movieargs)==0);
    uint32_t movieerror=api("_BinkGetError@0",0,NULL);
    check("Bink error is guest string",movieerror && !strcmp(gm_ptr(movieerror),"cannot open the movie"));gm_free(absent_movie);
    void *native=malloc(32);uint32_t handle=hle_handle_alloc(31,native);
    check("native handle preserves 64-bit pointer",handle && hle_handle_obj(handle,31)==native);
    check("typed handle rejects wrong type",hle_handle_obj(handle,HLE_H_MUTEX)==NULL);
    hle_handle_close(handle);free(native);
    mach_leave();
    thread_result workers[2]={{0}};pthread_t threads[2];
    int c0=pthread_create(&threads[0],NULL,thread_check,&workers[0]);
    int c1=pthread_create(&threads[1],NULL,thread_check,&workers[1]);
    if (!c0) pthread_join(threads[0],NULL);if (!c1) pthread_join(threads[1],NULL);
    check("two threads preserve register state over Sleep",!c0 && !c1 && workers[0].okay && workers[1].okay);
    check("thread TIBs and stacks are distinct",workers[0].tib!=workers[1].tib && workers[0].stack!=workers[1].stack);
    printf("{\"checks\":%u,\"failed\":%u,\"implemented_imports\":%u,\"explicit_unimplemented_imports\":%u,\"host_page_size\":%zu}\n",
           checks,failures,implemented,stubs,gm_page_size());
    return failures!=0;
}
