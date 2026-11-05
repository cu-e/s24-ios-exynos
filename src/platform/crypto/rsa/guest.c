/* Unchanged accepted virtual-board runtime;labels/cookie remain its XTS names.
 * RSA markers below identify the actual RSA suite. No XNU/phone is executed. */
#include "runtime.h"
extern int rsa_suite(unsigned *);
__attribute__((used,aligned(16))) unsigned char rsa_stack[65536];
__attribute__((noreturn)) void rsa_guest(const struct boot_args *args){
    xts_runtime_begin(args);
#ifdef RSA_SPIN
    text("RSA SYNTHETIC SPIN-CONTROL\n");for(;;)__asm__ volatile("wfe");
#else
    unsigned count=0;int failure=rsa_suite(&count);unsigned untouched=0;
    while(untouched<sizeof(rsa_stack) && rsa_stack[untouched]==0xa5)++untouched;
    unsigned used=(unsigned)sizeof(rsa_stack)-untouched;
    if(used>32768 && !failure)failure=__LINE__;
    text(failure?"RSA ARM FAIL":"RSA ARM PASS");text(" checks=");hex(count);
    text(" failure_line=");hex((unsigned)failure);text(" stack_used=");hex(used);putc('\n');
    xts_runtime_finish(count,failure);
#endif
    __builtin_unreachable();
}
__attribute__((naked,noreturn)) void xts_entry(void){
    __asm__ volatile("adrp x9, _rsa_stack@PAGE\nadd x9, x9, _rsa_stack@PAGEOFF\n"
        "mov x10, #0xa5a5\nmovk x10, #0xa5a5, lsl #16\nmovk x10, #0xa5a5, lsl #32\nmovk x10, #0xa5a5, lsl #48\n"
        "mov x11, x9\nmov x12, #4096\n1: stp x10, x10, [x11], #16\nsubs x12, x12, #1\nb.ne 1b\n"
        "add x9, x9, #16, lsl #12\nmov sp, x9\nb _rsa_guest");
}
