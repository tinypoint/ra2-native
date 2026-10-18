#ifndef RA2_GUEST_CPU_H
#define RA2_GUEST_CPU_H
#include <stdint.h>
#include <time.h>
/* An explicit virtual 1 GHz timestamp counter for lifted RDTSC. This is not
 * a claim of cycle-accurate x86 timing; game timing still needs validation. */
static inline uint64_t ra2_guest_rdtsc(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    return (uint64_t)ts.tv_sec*1000000000u+(uint64_t)ts.tv_nsec;
}
#define __rdtsc ra2_guest_rdtsc
#endif
