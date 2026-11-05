/* Actual algorithm fixture entry, with an owned64KiB stack. MMU remains off. */
#include "runtime.h"
extern int xts_suite(unsigned *count);
__attribute__((used,aligned(16))) unsigned char xts_stack[65536];
__attribute__((noreturn)) void xts_guest(const struct boot_args *args)
{
    xts_runtime_begin(args);
#ifdef XTS_SPIN
    text("XTS SYNTHETIC SPIN-CONTROL\n");
    for (;;) __asm__ volatile("wfe");
#else
    unsigned count;
    int failure=xts_suite(&count);
    xts_runtime_finish(count,failure);
#endif
    __builtin_unreachable();
}
__attribute__((naked,noreturn)) void xts_entry(void)
{
    __asm__ volatile("adrp x9, _xts_stack@PAGE\nadd x9, x9, _xts_stack@PAGEOFF\n"
                     "add x9, x9, #16, lsl #12\nmov sp, x9\nb _xts_guest");
}
