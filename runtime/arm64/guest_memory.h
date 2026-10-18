#ifndef RA2_GUEST_MEMORY_H
#define RA2_GUEST_MEMORY_H
#include <stddef.h>
#include <stdint.h>

/* A PE32 address remains uint32_t; host pointers are never truncated. */
int gm_init(void);
void *gm_ptr(uint32_t va);
uint32_t gm_va(const void *pointer);
uint32_t gm_reserve(uint32_t preferred, uint32_t size);
int gm_commit(uint32_t va, uint32_t size, uint32_t protection);
int gm_decommit(uint32_t va, uint32_t size);
int gm_release(uint32_t base);
int gm_protect(uint32_t va, uint32_t size, uint32_t protection, uint32_t *old);
int gm_query(uint32_t va, uint32_t result[7]);
int gm_accessible(uint32_t va, uint32_t size, int write_access);
void *gm_alloc(size_t size);
void *gm_calloc(size_t count, size_t size);
void *gm_realloc(void *pointer, size_t size);
void gm_free(void *pointer);
char *gm_strdup(const char *text);
size_t gm_page_size(void);
#endif
