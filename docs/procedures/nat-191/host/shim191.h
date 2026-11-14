/* SPDX-License-Identifier: GPL-2.0-only */
/* Stand-ins for the kernel headers e1s_display.c includes (NAT-191 host harness = NAT-189's (NAT-185's plus threads, saved user state and the
 * shared region), and the interrupt precondition of recount_current_*). */
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>
typedef uintptr_t vm_offset_t; typedef uintptr_t vm_size_t; typedef int wait_result_t;
typedef struct host_thread *thread_t;
typedef struct host_proc *proc_t; typedef struct host_proc *task_t;
typedef struct host_sr *vm_shared_region_t;
typedef uint64_t mach_vm_offset_t;
typedef int kern_return_t;
typedef int (*proc_iterate_fn_t)(proc_t, void *);
struct arm_saved_state { uint64_t pc, lr; };
#define TASK_NULL ((task_t)0)
#define PROC_NULL ((proc_t)0)
#define PROC_RETURNED 0
#define PROC_ALLPROCLIST 1U
#define KERN_SUCCESS 0
#define NSEC_PER_USEC 1000ull
#define NSEC_PER_SEC 1000000000ull
#define ARM64_BOARD_CONFIG_E1S 1
#define __unused __attribute__((unused))
struct vc_info { unsigned v_width, v_height, v_depth, v_rowbytes; unsigned long long v_physaddr; uintptr_t v_baseaddr; };
struct vc_info vinfo;
struct recount_times_mach { uint64_t rtm_user, rtm_system; };
extern uint64_t host_ns;
void host_delay(uint64_t n, uint64_t scale);
int host_thread_start(void (*f)(void *, int), void *a, void **t);
int PE_parse_boot_argn(const char *n, void *v, int s);
void proc_iterate(unsigned int flags, proc_iterate_fn_t callout, void *arg, proc_iterate_fn_t filterfn, void *filterarg);
int proc_pid(proc_t p);
task_t proc_task(proc_t p);
char *proc_best_name(proc_t p);
proc_t proc_find(int pid);
int proc_rele(proc_t p);
struct recount_times_mach recount_task_times(task_t t);
uint64_t recount_thread_time_mach(thread_t th);
uint64_t recount_current_thread_time_mach(void);     /* aborts: asserts interrupts off (NAT-190) */
struct recount_times_mach recount_current_thread_times(void);   /* aborts too */
thread_t current_thread(void);
uint64_t thread_tid(thread_t th);
vm_shared_region_t vm_shared_region_get(task_t t);
kern_return_t vm_shared_region_start_address(vm_shared_region_t sr, mach_vm_offset_t *start, task_t t);
void vm_shared_region_deallocate(vm_shared_region_t sr);
static inline uint64_t get_saved_state_pc(const struct arm_saved_state *s) { return s->pc; }
static inline uint64_t get_saved_state_lr(const struct arm_saved_state *s) { return s->lr; }
#define delay_for_interval host_delay
#define kernel_thread_start(f, a, t) host_thread_start((void (*)(void *, int))(f), (a), (void **)(t))
static inline void thread_deallocate(thread_t t) { (void)t; }
static inline uint64_t mach_absolute_time(void) { return host_ns; }
static inline void absolutetime_to_nanoseconds(uint64_t a, uint64_t *n) { *n = a; }
#define Z_WAITOK 1
#define Z_ZERO 2
void *host_kalloc(size_t size, int flags);
#define kalloc_data(size, flags) host_kalloc((size), (flags))
