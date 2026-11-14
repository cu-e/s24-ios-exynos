/* NAT-123 host shim for e1s_acpm.c + e1s_pmic.c: kernel calls mapped to a fake APM (fakeapm.c). */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t; typedef uintptr_t vm_size_t;
typedef struct { int x; } lck_grp_t; typedef struct { int x; } lck_mtx_t;
#define LCK_GRP_ATTR_NULL 0
#define LCK_ATTR_NULL 0
#define __unused __attribute__((unused))
#define NSEC_PER_USEC 1000ULL
#define NSEC_PER_MSEC 1000000ULL
#define EINVAL 22
#define EIO 5
#define ENXIO 6
#define EAGAIN 35
#define ETIMEDOUT 60
static inline lck_grp_t *lck_grp_alloc_init(const char *n, int a) { static lck_grp_t g; (void)n; (void)a; return &g; }
static inline lck_mtx_t *lck_mtx_alloc_init(lck_grp_t *g, int a) { static lck_mtx_t m; (void)g; (void)a; return &m; }
static inline void lck_mtx_lock(lck_mtx_t *m) { (void)m; }
static inline void lck_mtx_unlock(lck_mtx_t *m) { (void)m; }
void delay(int us);
void delay_for_interval(uint64_t n, uint64_t unit);
int PE_parse_boot_argn(const char *n, void *v, int s);
vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t size);
static inline uint64_t mach_absolute_time(void) { static uint64_t t; return t += 12500000; }   /* 12.5 ms per read pair */
static inline void absolutetime_to_nanoseconds(uint64_t a, uint64_t *ns) { *ns = a; }
typedef unsigned long clock_sec_t;
static inline void clock_set_calendar_microtime(clock_sec_t s, int u) { (void)s; (void)u; }
bool e1s_acpm_ready(void); void e1s_acpm_probe(void);
int e1s_acpm_mfd_read(uint8_t sid, uint8_t type, uint8_t reg, uint8_t *value);
int e1s_acpm_mfd_write(uint8_t sid, uint8_t type, uint8_t reg, uint8_t value);
int e1s_acpm_mfd_update(uint8_t sid, uint8_t type, uint8_t reg, uint8_t value, uint8_t mask);
