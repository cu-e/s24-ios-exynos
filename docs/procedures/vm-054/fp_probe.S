// VM-054 FP/SIMD probe: an arm64 Linux Image for s24vmm that checks whether FP/SIMD instructions run
// in a guest once CPACR_EL1.FPEN is 0b11, and that they trap to the guest's own EL1 vector when FPEN
// is 0b00. Output goes to the 8250 THR at 0x3f8 (s24vmm's console); the guest ends with PSCI
// SYSTEM_OFF. MMU off throughout. Registers: x19 UART, x20 stage, x21 traps taken.
//   "1" fmov d0,xzr with FPEN=11   "2" movi v1.2d with FPEN=11   "3" fmov with FPEN=00 (must trap)
//   "4" fmov with FPEN=11 after a ~2 s spin (host preemptions)   "C" CPACR_EL1 read back
// A trap prints "E<stage> esr=<hex> elr=<hex>"; at stage 3 the handler sets FPEN=11 and returns so the
// instruction re-executes; at any other stage it powers off.
    .text
    .globl _head
_head:
    b       start                   // code0
    .long   0                       // code1
    .quad   0                       // text_offset
    .quad   _end - _head            // image_size
    .quad   0xa                     // flags: little endian, 4K pages, placement anywhere
    .quad   0, 0, 0
    .ascii  "ARM\x64"               // magic
    .long   0

    .macro putc c
    mov     w9, #\c
    strb    w9, [x19]
    .endm

start:
    movz    x19, #0x3f8
    mov     x21, #0
    adr     x0, vectors
    msr     vbar_el1, x0
    isb
    putc    'P'
    putc    '\n'

    mov     x20, #1
    mov     x0, #0x300000           // CPACR_EL1.FPEN = 0b11
    msr     cpacr_el1, x0
    isb
    fmov    d0, xzr
    fmov    x1, d0
    putc    '1'
    putc    'o'
    putc    'k'
    putc    '\n'

    mov     x20, #2
    movi    v1.2d, #0
    putc    '2'
    putc    'o'
    putc    'k'
    putc    '\n'

    mov     x20, #3
    msr     cpacr_el1, xzr          // FPEN = 0b00: the next FP instruction must trap to our vector
    isb
    fmov    d0, xzr
    putc    '3'
    putc    'o'
    putc    'k'
    putc    ' '
    putc    't'
    add     w9, w21, #'0'
    strb    w9, [x19]
    putc    '\n'

    mov     x20, #4                 // FPEN = 0b11, then ~2 s of host preemptions, then FP
    mov     x0, #0x300000
    msr     cpacr_el1, x0
    isb
    mrs     x13, cntfrq_el0
    mrs     x14, cntvct_el0
    add     x14, x14, x13, lsl #1
3:  mrs     x15, cntvct_el0
    cmp     x15, x14
    b.lo    3b
    fmov    d0, xzr
    putc    '4'
    putc    'o'
    putc    'k'
    putc    '\n'
    mov     x20, #5                 // cpacr read back after the spin
    mrs     x10, cpacr_el1
    putc    'C'
    putc    ' '
    bl      hex
    putc    '\n'
    b       off

trap:
    add     x21, x21, #1
    putc    'E'
    add     w9, w20, #'0'
    strb    w9, [x19]
    putc    ' '
    mrs     x10, esr_el1
    bl      hex
    putc    ' '
    mrs     x10, elr_el1
    bl      hex
    putc    '\n'
    cmp     x20, #3
    b.ne    off
    mov     x0, #0x300000
    msr     cpacr_el1, x0
    isb
    eret

hex:                                // prints x10 as 16 hex digits; clobbers x9, x11, x12
    mov     x11, #60
1:  lsr     x12, x10, x11
    and     x12, x12, #0xf
    cmp     x12, #10
    add     x9, x12, #'0'
    add     x12, x12, #('a' - 10)
    csel    x9, x12, x9, ge
    strb    w9, [x19]
    subs    x11, x11, #4
    b.ge    1b
    ret

off:
    movz    w0, #0x8400, lsl #16    // PSCI SYSTEM_OFF
    movk    w0, #0x0008
    hvc     #0
2:  wfi
    b       2b

    .balign 2048
vectors:                            // all 16 entries go to trap
    .rept 16
    b       trap
    .balign 128
    .endr
_end:
