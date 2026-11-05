/* Reuse accepted owned synthetic AVF runtime unchanged (including its labels). */
#include "runtime.h"
extern int des_suite(unsigned *count);
__attribute__((used,aligned(16))) unsigned char des_stack[65536];
__attribute__((noreturn)) void des_guest(const struct boot_args *args)
{
 xts_runtime_begin(args);
#ifdef DES_SPIN
 text("DES SYNTHETIC SPIN-CONTROL\n");for(;;)__asm__ volatile("wfe");
#else
 unsigned count;int failure=des_suite(&count);
 text(failure?"DES ARM FAIL checks=":"DES ARM PASS checks=");hex(count);text(" failure_line=");hex((unsigned)failure);text("\n");stop();
#endif
 __builtin_unreachable();
}
__attribute__((naked,noreturn)) void xts_entry(void)
{
 __asm__ volatile("adrp x9, _des_stack@PAGE\nadd x9, x9, _des_stack@PAGEOFF\n"
 "add x9, x9, #16, lsl #12\nmov sp, x9\nb _des_guest");
}
