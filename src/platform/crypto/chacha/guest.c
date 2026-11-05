/* Own algorithm entry/stack; accepted immutable runtime retains XTS names. */
#include "runtime.h"
extern int chacha_suite(unsigned *count);
__attribute__((used,aligned(16))) unsigned char chacha_stack[65536];
__attribute__((noreturn)) void chacha_guest(const struct boot_args *args)
{
    xts_runtime_begin(args);
#ifdef CHACHA_SPIN
    text("CHACHA SYNTHETIC SPIN-CONTROL\n");for (;;) __asm__ volatile("wfe");
#else
    unsigned count;int failure=chacha_suite(&count);
    text(failure?"CHACHA ARM FAIL checks=":"CHACHA ARM PASS checks=");hex(count);
    text(" failure_line=");hex((unsigned)failure);text(" incnonce=UNQUALIFIED\n");
    xts_runtime_finish(count,failure);
#endif
    __builtin_unreachable();
}
/* The immutable harness validates this historical entry symbol by address.
 * Only this owned entry is linked, never the original XTS guest object. */
__attribute__((naked,noreturn)) void xts_entry(void)
{
    __asm__ volatile("adrp x9, _chacha_stack@PAGE\nadd x9, x9, _chacha_stack@PAGEOFF\n"
                     "add x9, x9, #16, lsl #12\nmov sp, x9\nb _chacha_guest");
}
