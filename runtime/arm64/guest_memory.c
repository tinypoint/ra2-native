/* PE32 virtual memory in an owned 4 GiB host reservation. No x86 execution.
 * This initial backend manages whole host pages (16 KiB on the test Mac).
 * Guest protection changes at finer granularity are explicitly rejected.
 */
#include "guest_memory.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

extern ptrdiff_t g_mem_base;
static unsigned char *arena;
static size_t page, npages;
static uint32_t *owner, *spans;
static unsigned char *protection;
static pthread_once_t once=PTHREAD_ONCE_INIT;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;

static void setup(void) {
    page=(size_t)sysconf(_SC_PAGESIZE);
    if (!page || (page & (page-1))) return;
    npages=((size_t)UINT32_MAX+1)/page;
    arena=mmap(NULL,(size_t)UINT32_MAX+1,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);
    if (arena==MAP_FAILED) { arena=NULL;return; }
    owner=calloc(npages,sizeof *owner); spans=calloc(npages,sizeof *spans);
    protection=calloc(npages,sizeof *protection);
    if (!owner || !spans || !protection) {
        munmap(arena,(size_t)UINT32_MAX+1);free(owner);free(spans);free(protection);
        arena=NULL;return;
    }
    g_mem_base=(ptrdiff_t)(uintptr_t)arena;
}
int gm_init(void) { pthread_once(&once,setup);return arena!=NULL; }
size_t gm_page_size(void) { return gm_init()?page:0; }
static void fail(const char *what) { fprintf(stderr,"[guest-memory] %s\n",what);abort(); }
void *gm_ptr(uint32_t va) {
    if (!va) return NULL;
    if (!gm_init() || va<0x10000) fail("invalid guest pointer");
    return arena+va;
}
uint32_t gm_va(const void *pointer) {
    if (!pointer) return 0;
    if (!gm_init()) fail("arena unavailable");
    uintptr_t p=(uintptr_t)pointer,b=(uintptr_t)arena;
    if (p<b+0x10000 || p-b>UINT32_MAX) fail("host pointer cannot be returned to PE32 guest");
    return (uint32_t)(p-b);
}

/* Locked helpers. All arithmetic involving an end address is 64-bit. */
static int range(uint32_t va,uint32_t size,size_t *start,size_t *count) {
    if (!size || va<0x10000 || (uint64_t)va+size>((uint64_t)1<<32)) return 0;
    *start=va/page;
    *count=(((uint64_t)va+size+page-1)/page)-*start;
    uint32_t id=owner[*start];
    if (!id) return 0;
    for (size_t k=0;k<*count;k++) if (owner[*start+k]!=id) return 0;
    return 1;
}
static int native_prot(uint32_t p) {
    switch (p) {
    case 0x01:return PROT_NONE;
    case 0x02:case 0x20:return PROT_READ;
    case 0x04:case 0x40:return PROT_READ|PROT_WRITE;
    default:return -1;
    }
}
uint32_t gm_reserve(uint32_t preferred,uint32_t size) {
    if (!gm_init() || !size) return 0;
    size_t n=((uint64_t)size+page-1)/page,start=0;
    if (n>npages) return 0;
    pthread_mutex_lock(&lock);
    if (preferred) {
        if (preferred<0x10000 || preferred%page || (uint64_t)preferred+n*page>((uint64_t)1<<32)) goto done;
        start=preferred/page;
        for (size_t k=0;k<n;k++) if (owner[start+k]) {start=0;goto done;}
    } else {
        size_t run=0,limit=0x70000000/page;
        for (size_t k=0x10000000/page;k<limit;k++) {
            run=owner[k]?0:run+1;
            if (run==n) {start=k+1-n;break;}
        }
        if (!start) goto done;
    }
    for (size_t k=0;k<n;k++) owner[start+k]=(uint32_t)start+1;
    spans[start]=(uint32_t)n;
done:
    pthread_mutex_unlock(&lock);
    return (uint32_t)(start*page);
}
int gm_commit(uint32_t va,uint32_t size,uint32_t prot) {
    if (!gm_init()) return 0;
    int flags=native_prot(prot),ok=0;size_t start,n;
    if (flags<0) return 0;
    pthread_mutex_lock(&lock);
    if (range(va,size,&start,&n) && !mprotect(arena+start*page,n*page,flags)) {
        for (size_t k=0;k<n;k++) protection[start+k]=(unsigned char)prot;
        ok=1;
    }
    pthread_mutex_unlock(&lock);return ok;
}
static int discard(size_t start,size_t n) {
    /* MAP_FIXED is confined to pages in our owned reservation after checking
       allocation metadata, never used on a raw guest VA or unrelated mapping. */
    return mmap(arena+start*page,n*page,PROT_NONE,
                MAP_FIXED|MAP_PRIVATE|MAP_ANON,-1,0)!=MAP_FAILED;
}
int gm_decommit(uint32_t va,uint32_t size) {
    if (!gm_init() || va%page || size%page) return 0;
    size_t start,n;int ok=0;
    pthread_mutex_lock(&lock);
    if (range(va,size,&start,&n) && discard(start,n)) {
        memset(protection+start,0,n);ok=1;
    }
    pthread_mutex_unlock(&lock);return ok;
}
int gm_release(uint32_t base) {
    if (!gm_init() || base%page) return 0;
    size_t start=base/page;int ok=0;
    pthread_mutex_lock(&lock);
    size_t n=spans[start];
    if (n && owner[start]==start+1 && discard(start,n)) {
        memset(owner+start,0,n*sizeof *owner);memset(protection+start,0,n);
        spans[start]=0;ok=1;
    }
    pthread_mutex_unlock(&lock);return ok;
}
int gm_protect(uint32_t va,uint32_t size,uint32_t prot,uint32_t *old) {
    if (!gm_init() || va%page || size%page) return 0;
    size_t start,n;int ok=0,p=native_prot(prot);
    if (p<0) return 0;
    pthread_mutex_lock(&lock);
    if (range(va,size,&start,&n)) {
        for (size_t k=0;k<n;k++) if (!protection[start+k]) goto done;
        uint32_t previous=protection[start];
        if (!mprotect(arena+start*page,n*page,p)) {
            for (size_t k=0;k<n;k++) protection[start+k]=(unsigned char)prot;
            if (old) *old=previous;
            ok=1;
        }
    }
done:pthread_mutex_unlock(&lock);return ok;
}
int gm_query(uint32_t va,uint32_t out[7]) {
    if (!gm_init() || !out) return 0;
    size_t i=va/page,end=i+1;pthread_mutex_lock(&lock);
    uint32_t id=owner[i];unsigned char p=protection[i];
    while (end<npages && owner[end]==id && protection[end]==p) end++;
    out[0]=(uint32_t)(i*page);out[1]=id?(uint32_t)((id-1)*page):0;
    out[2]=id?0x04:0;out[3]=(uint32_t)((end-i)*page);
    out[4]=id?(p?0x1000:0x2000):0x10000;out[5]=p?p:0x01;out[6]=id?0x20000:0;
    pthread_mutex_unlock(&lock);return 1;
}
int gm_accessible(uint32_t va,uint32_t size,int write_access) {
    if (!size) return 1;
    if (!gm_init()) return 0;
    size_t start,n;int ok=0;pthread_mutex_lock(&lock);
    if (range(va,size,&start,&n)) {
        ok=1;
        for (size_t k=0;k<n;k++) {
            int p=native_prot(protection[start+k]);
            if (p<0 || !(p&PROT_READ) || (write_access && !(p&PROT_WRITE))) {ok=0;break;}
        }
    }
    pthread_mutex_unlock(&lock);return ok;
}
void *gm_alloc(size_t size) {
    if (size>UINT32_MAX) return NULL;
    uint32_t va=gm_reserve(0,(uint32_t)(size?size:1));
    if (!va) return NULL;
    if (!gm_commit(va,(uint32_t)(size?size:1),0x04)) {gm_release(va);return NULL;}
    return gm_ptr(va);
}
void *gm_calloc(size_t n,size_t size) {
    if (size && n>SIZE_MAX/size) return NULL;
    return gm_alloc(n*size); /* fresh anonymous memory is zero */
}
void gm_free(void *p) {
    if (p && !gm_release(gm_va(p))) fail("free is not an allocation base");
}
void *gm_realloc(void *p,size_t size) {
    if (!p) return gm_alloc(size);
    if (!size) {gm_free(p);return NULL;}
    uint32_t va=gm_va(p);size_t start=va/page,old;
    pthread_mutex_lock(&lock);old=spans[start]*page;pthread_mutex_unlock(&lock);
    if (!old || va%page) fail("realloc is not an allocation base");
    void *q=gm_alloc(size);
    if (q) {memcpy(q,p,old<size?old:size);gm_free(p);}
    return q;
}
char *gm_strdup(const char *s) {
    size_t n=strlen(s)+1;char *p=gm_alloc(n);if (p) memcpy(p,s,n);return p;
}
