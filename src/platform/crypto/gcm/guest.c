/* Own bounded CPU entry, accepted synthetic handoff; not XNU or a phone. */
#include "runtime.h"
extern int s24_gcm_suite(void);
extern unsigned s24_gcm_suite_checks(void);
__attribute__((used,aligned(16))) unsigned char gcm_stack[65536];
__attribute__((noreturn)) void gcm_guest(const struct boot_args *args)
{
 gcm_runtime_begin(args);
#ifdef GCM_SPIN
 text("GCM SYNTHETIC SPIN-CONTROL\n");for(;;)__asm__ volatile("wfe");
#else
 int failure=s24_gcm_suite();gcm_runtime_finish(s24_gcm_suite_checks(),failure);
#endif
 __builtin_unreachable();
}
__attribute__((naked,noreturn)) void gcm_entry(void)
{
 __asm__ volatile("adrp x9, _gcm_stack@PAGE\nadd x9, x9, _gcm_stack@PAGEOFF\nadd x9, x9, #16, lsl #12\nmov sp, x9\nb _gcm_guest");
}
