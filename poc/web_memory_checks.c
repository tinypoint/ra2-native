/* Standalone bounded-arena contract checks; no game resources required. */
#include "guest_memory.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
ptrdiff_t g_mem_base;
static unsigned checks,failed;
#define CHECK(x) do{checks++;if(!(x)){failed++;fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);}}while(0)
int main(int argc,char **argv){
    if(argc>1){gm_ptr(!strcmp(argv[1],"low")?1u:UINT32_MAX);return 2;}
    CHECK(gm_init());CHECK(gm_page_size()==4096);
    CHECK(gm_ptr(0)==NULL);CHECK(gm_va(NULL)==0);
    CHECK(gm_reserve(0xfffff000u,0x2000)==0);
    CHECK(gm_reserve(0x20000000u,4096)==0); /* default cap */
    CHECK(gm_reserve(0x1000,4096)==0);
    uint32_t va=gm_reserve(0x400000,8192);CHECK(va==0x400000);
    CHECK(!gm_accessible(va,1,0));CHECK(gm_commit(va,8192,4));
    CHECK(gm_va(gm_ptr(va))==va);CHECK(gm_accessible(va,8192,1));
    CHECK(!gm_accessible(va+8191,2,0));CHECK(!gm_accessible(UINT32_MAX,2,0));
    unsigned char *p=gm_ptr(va);p[0]=42;p[8191]=73;
    uint32_t old=0,q[7];CHECK(gm_protect(va,4096,2,&old));CHECK(old==4);
    CHECK(gm_accessible(va,4096,0));CHECK(!gm_accessible(va,1,1));
    CHECK(gm_query(va,q)&&q[0]==va&&q[3]==4096&&q[4]==0x1000&&q[5]==2);
    CHECK(!gm_protect(va+1,4096,4,&old));CHECK(!gm_commit(va,4096,0xff));
    CHECK(gm_decommit(va,4096));CHECK(!gm_accessible(va,1,0));
    CHECK(gm_commit(va,4096,4));CHECK(p[0]==0&&p[8191]==73);
    CHECK(!gm_release(va+4096));CHECK(gm_release(va));CHECK(!gm_release(va));
    CHECK(gm_query(va,q)&&q[4]==0x10000);
    CHECK(!gm_query(UINT32_MAX,q));CHECK(!gm_release(UINT32_MAX));
    void *a=gm_calloc(8,8);CHECK(a&&gm_va(a)>=0x10000000u);
    CHECK(!memcmp(a,(unsigned char[64]){0},64));memset(a,0x5a,64);
    void *b=gm_realloc(a,8192);CHECK(b&&((unsigned char*)b)[0]==0x5a&&((unsigned char*)b)[63]==0x5a);
    gm_free(b);char *s=gm_strdup("RA2 wasm");CHECK(s&&!strcmp(s,"RA2 wasm"));gm_free(s);
    CHECK(gm_calloc(SIZE_MAX,2)==NULL);CHECK(gm_alloc(SIZE_MAX)==NULL);
    CHECK(gm_reserve(0,UINT32_MAX)==0);
    printf("{\"checks\":%u,\"failed\":%u,\"guest_page_bytes\":%zu,\"software_protection_only\":true}\n",checks,failed,gm_page_size());
    return failed?1:0;
}
