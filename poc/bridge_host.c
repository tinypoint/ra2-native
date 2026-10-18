/* Minimal single-threaded synthetic host, NOT a port of win32hle.
 * The generated functions use the unmodified upstream recomp32 header.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "recomp_types.h"

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
static unsigned shim_calls, callback_calls;

void sub_00401000(void);
void sub_00401100(void);
void sub_00401200(void);

static void synthetic_import(void) {
    uint32_t entry_sp = g_esp;
    uint32_t value = MEM32(entry_sp + 4);
    shim_calls++;
    PUSH32(g_esp, value);
    PUSH32(g_esp, RECOMP_RETADDR);
    callback_calls++;
    sub_00401200();
    if (g_esp != entry_sp) {
        fprintf(stderr, "callback corrupted guest stack\n");
        exit(3);
    }
    g_esp += 8; /* stdcall ret + one argument */
}

recomp_func_t recomp_lookup(uint32_t va) {
    switch (va) {
    case 0x00401000: return sub_00401000;
    case 0x00401100: return sub_00401100;
    case 0x00401200: return sub_00401200;
    default:
        fprintf(stderr, "unresolved synthetic guest function %08x\n", va);
        exit(4);
    }
}
recomp_func_t recomp_lookup_manual(uint32_t va) {
    return va == 0x00401300 ? synthetic_import : NULL;
}
recomp_func_t recomp_lookup_import(uint32_t va) { (void)va; return NULL; }

int main(int argc, char **argv) {
    unsigned char *memory = calloc(1, 0x40000);
    if (!memory || argc != 2) return 2;
    g_mem_base = (ptrdiff_t)(uintptr_t)memory - 0x00400000;
    if ((uintptr_t)memory <= UINT32_MAX) {
        fprintf(stderr, "fixture requires host memory above 4 GiB\n");
        return 2;
    }
    uint32_t value = (uint32_t)strtoull(argv[1], NULL, 0);
    MEM32(0x00430100) = 0x00430200; /* object -> guest vtable */
    MEM32(0x00430104) = value;
    MEM32(0x00430200) = 0x00401100; /* vtable -> guest method */
    MEM32(0x00430300) = 0x00401300; /* synthetic IAT -> native shim ID */
    g_ecx = 0x00430100;
    g_esp = 0x00420000;
    MEM32(g_esp) = 0x00403000;
    sub_00401000();
    printf("{\"eax\":%" PRIu32 ",\"esp\":%" PRIu32
           ",\"object_result\":%" PRIu32 ",\"shim_calls\":%u,"
           "\"callback_calls\":%u,\"host_above_4g\":true}\n",
           g_eax, g_esp, MEM32(0x00430108), shim_calls, callback_calls);
    free(memory);
    return 0;
}
