/* Accepted synthetic AVF runtime unchanged; its XTS cookie/labels retained. */
#include "runtime.h"
extern int cts3_suite(unsigned *count);
__attribute__((used,aligned(16))) unsigned char cts3_stack[65536];
__attribute__((noreturn)) void cts3_guest(const struct boot_args*args)
{
 xts_runtime_begin(args);
#ifdef CTS3_SPIN
 text("CTS3 SYNTHETIC SPIN-CONTROL\n");for(;;)__asm__ volatile("wfe");
#else
 unsigned count;int failure=cts3_suite(&count);
 text(failure?"CTS3 ARM FAIL checks=":"CTS3 ARM PASS checks=");hex(count);text(" failure_line=");hex((unsigned)failure);text("\n");stop();
#endif
 __builtin_unreachable();
}
__attribute__((naked,noreturn)) void xts_entry(void)
{__asm__ volatile("adrp x9, _cts3_stack@PAGE\nadd x9,x9,_cts3_stack@PAGEOFF\nadd x9,x9,#16,lsl #12\nmov sp,x9\nb _cts3_guest");}
