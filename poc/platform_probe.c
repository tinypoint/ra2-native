/* Original diagnostic fixture; no game code or assets. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

int main(void) {
    void *heap = malloc(64);
    if (!heap) return 1;
    printf("pointer_bits=%zu long_double_bits=%zu page_size=%ld\n",
           sizeof(void *) * 8, sizeof(long double) * 8, sysconf(_SC_PAGESIZE));
    printf("heap=%p fits_guest_uint32=%s\n", heap,
           (uintptr_t)heap <= UINT32_MAX ? "yes" : "no");
    /* A hint, never MAP_FIXED: this cannot overwrite an existing mapping. */
    void *hint = (void *)(uintptr_t)0x00400000u;
    size_t span = (size_t)sysconf(_SC_PAGESIZE);
    void *mapped = mmap(hint, span, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON, -1, 0);
    if (mapped == MAP_FAILED) {
        printf("low_address_hint=failed errno=%d %s\n", errno, strerror(errno));
    } else {
        printf("low_address_hint=%p actual=%p exact=%s\n", hint, mapped,
               mapped == hint ? "yes" : "no");
        munmap(mapped, span);
    }
    free(heap);
    return 0;
}
