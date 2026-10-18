/* ARM64 host for isolated functions lifted from a user-provided RA2 image.
 * No proprietary code is embedded here. Generated bodies and memory images
 * remain local. This is not a complete PE loader or Win32 HLE.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "recomp_types.h"
#include "game_functions.h"

uint32_t g_eax, g_ecx, g_edx, g_esp, g_ebx, g_esi, g_edi, g_ebp;
double g_st[8];
int g_fp_top;
uint16_t g_fpu_cw = 0x027f;
uint16_t g_seg_cs, g_seg_ds, g_seg_es, g_seg_fs, g_seg_gs, g_seg_ss;
uint32_t g_fs_base, g_gs_base, g_cur_func;
uint64_t g_mm[8];
xmm_t g_xmm[8];
uint32_t g_mxcsr = 0x1f80;
ptrdiff_t g_mem_base;
uint32_t g_icall_trace[ICALL_TRACE_SIZE], g_icall_from[ICALL_TRACE_SIZE];
uint32_t g_icall_trace_idx, g_icall_count;

static void die(const char *what) { perror(what); exit(2); }
static void read_exact(FILE *f, void *p, size_t n) {
    if (fread(p, 1, n, f) != n) die("read");
}
recomp_func_t recomp_lookup(uint32_t va) {
    for (size_t i = 0; i < GAME_FUNCTION_COUNT; i++)
        if (game_functions[i].address == va) return game_functions[i].func;
    fprintf(stderr, "Unresolved real game function %08x\n", va);
    exit(3);
}
recomp_func_t recomp_lookup_manual(uint32_t va) { (void)va; return NULL; }
recomp_func_t recomp_lookup_import(uint32_t va) { (void)va; return NULL; }

int main(int argc, char **argv) {
    if (argc != 5) return 2;
    const size_t arena_size = (size_t)UINT32_MAX + 1u;
    unsigned char *arena = mmap(NULL, arena_size, PROT_NONE,
                                MAP_PRIVATE | MAP_ANON, -1, 0);
    if (arena == MAP_FAILED) die("reserve guest VA");
    if ((uintptr_t)arena <= UINT32_MAX) {
        fprintf(stderr, "Expected a host arena above 4 GiB\n"); return 2;
    }
    g_mem_base = (ptrdiff_t)(uintptr_t)arena;
    FILE *image = fopen(argv[1], "rb");
    if (!image) die("open image");
    if (fseek(image, 0, SEEK_END)) die("seek image");
    long length = ftell(image);
    if (length <= 0 || length > 0x01000000 || fseek(image, 0, SEEK_SET)) return 2;
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    size_t commit = ((size_t)length + page - 1) & ~(page - 1);
    if (mprotect(arena + 0x00400000, commit, PROT_READ | PROT_WRITE)) die("commit image");
    if (mprotect(arena + 0x10000000, 0x10000, PROT_READ | PROT_WRITE)) die("commit scratch");
    unsigned char *original = malloc((size_t)length);
    if (!original) die("allocate image copy");
    read_exact(image, original, (size_t)length);
    fclose(image);
    memcpy(arena + 0x00400000, original, (size_t)length);
    FILE *input = fopen(argv[2], "rb");
    if (!input) die("open input");
    uint32_t regs[8];
    read_exact(input, regs, sizeof regs);
    read_exact(input, arena + 0x10000000, 0x10000);
    fclose(input);
    g_eax=regs[0]; g_ecx=regs[1]; g_edx=regs[2]; g_ebx=regs[3];
    g_esp=regs[4]; g_ebp=regs[5]; g_esi=regs[6]; g_edi=regs[7];
    g_flag_k=FK_EFLAGS; g_flag_a=0x202; g_flag_b=0; g_flag_cf=0;
    uint32_t entry = (uint32_t)strtoul(argv[3], NULL, 0);
    recomp_lookup(entry)();
    regs[0]=g_eax; regs[1]=g_ecx; regs[2]=g_edx; regs[3]=g_ebx;
    regs[4]=g_esp; regs[5]=g_ebp; regs[6]=g_esi; regs[7]=g_edi;
    uint32_t flags=recomp_eflags(g_flag_k,g_flag_a,g_flag_b,g_flag_cf,1);
    uint32_t depth=(uint32_t)g_fp_top;
    uint64_t fp_bits=0;
    if (depth) memcpy(&fp_bits, &g_st[depth-1], sizeof fp_bits);
    uint32_t unchanged=!memcmp(arena+0x00400000,original,(size_t)length);
    uint32_t high=1;
    FILE *output=fopen(argv[4], "wb");
    if (!output) die("open result");
    if (fwrite(regs,1,sizeof regs,output)!=sizeof regs ||
        fwrite(&flags,4,1,output)!=1 || fwrite(&depth,4,1,output)!=1 ||
        fwrite(&fp_bits,8,1,output)!=1 || fwrite(&unchanged,4,1,output)!=1 ||
        fwrite(&high,4,1,output)!=1 ||
        fwrite(arena+0x10000000,1,0x10000,output)!=0x10000 || fclose(output)) die("write result");
    free(original);
    munmap(arena,arena_size);
    return 0;
}
