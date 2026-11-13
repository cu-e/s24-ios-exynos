/* NAT-121 host shim: just enough of the XNU headers e1s_touch.c includes, so its own code runs on the host against a fake
 * register file. Every access is checked to fall inside one of the two mapped 4 KiB pages. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
typedef uintptr_t vm_offset_t; typedef uintptr_t vm_size_t; typedef int kern_return_t; typedef void *thread_t;
typedef int wait_result_t; typedef void *event_t;
#define KERN_SUCCESS 0
#define THREAD_UNINT 0
#define THREAD_AWAKENED 0
#define THREAD_CONTINUE_NULL 0
#define NSEC_PER_USEC 1000
#define __unused __attribute__((unused))
#define REDWOOD_TOUCH_DOWN 1
#define REDWOOD_TOUCH_MOVE 2
#define REDWOOD_TOUCH_UP 3
#define release 0
#define acquire 0
#define os_atomic_store(p, v, o) (*(p) = (v))
#define os_atomic_xchg(p, v, o) __atomic_exchange_n((p), (v), __ATOMIC_SEQ_CST)
extern uint8_t fake_page[2][4096];
extern int host_steps, host_bad, host_writes[2], host_irq_attached;
int PE_parse_boot_argn(const char *n, void *v, int s);
static inline void thread_wakeup(event_t e) { (void)e; }
static inline void assert_wait_timeout(event_t e, int a, int b, int c) { (void)e; (void)a; (void)b; (void)c; }
static inline void clear_wait(void *t, int r) { (void)t; (void)r; }
static inline void *current_thread(void) { return 0; }
static inline int thread_block(int c) { (void)c; return 0; }
static inline void delay_for_interval(int a, int b) { (void)a; (void)b; }
static inline void thread_deallocate(thread_t t) { (void)t; }
static inline kern_return_t kernel_thread_start(void (*f)(void *, wait_result_t), void *a, thread_t *t) { (void)f; (void)a; *t = 0; return 0; }
void redwood_touch_post(uint32_t type, uint32_t finger, uint32_t x, uint32_t y);
