// VM-054 CPACR synchronization probe: an arm64 Linux Image for s24vmm. XNU's common_start writes
// CPACR_EL1.FPEN = 0b11 with no ISB after it (osfmk/arm64/start.s:762-763, xnu c54f35ca) and then
// reaches its first FP instruction in cpu_data_init without any context synchronization event.
// This probe checks whether, in a guest on this CPU, an FP instruction after such an unsynchronized
// write still traps on the old FPEN = 0b00. MMU off; output to the 8250 THR at 0x3f8; PSCI SYSTEM_OFF.
// No UART write (a VM exit, hence a context synchronization event) happens between the write and
// the FP instruction it tests.
//   "A" FPEN 00 (isb), FPEN 11 with no isb, fmov at once
//   "B" as A, then XNU's next instructions (TPIDR_EL1, MDSCR_EL1, a call and return) before fmov
//   "D" as A, then ~1M ALU instructions before fmov
//   "S" control: FPEN 00 (isb), FPEN 11 then isb, fmov (must not trap)
// A trap prints "E<stage> esr=<hex> elr=<hex>", sets FPEN 11 with an isb and returns, so the
// instruction re-executes; each stage then prints "<stage> t<traps so far>".
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

    .macro fp_off_synced            // FPEN = 0b00, synchronized
    msr     cpacr_el1, xzr
    isb
    .endm

    .macro report stage
    putc    \stage
    putc    ' '
    putc    't'
    add     w9, w21, #'0'
    strb    w9, [x19]
    putc    '\n'
    .endm

start:
    movz    x19, #0x3f8
    mov     x21, #0
    adr     x0, vectors
    msr     vbar_el1, x0
    adr     x0, stack_top
    mov     sp, x0
    isb
    putc    'Q'
    putc    '\n'
    mov     x22, #0x300000          // CPACR_EL1.FPEN = 0b11

    mov     x20, #'A'
    fp_off_synced
    msr     cpacr_el1, x22          // no isb
    fmov    d0, xzr
    report  'A'

    mov     x20, #'B'
    fp_off_synced
    msr     cpacr_el1, x22          // no isb, then what common_start does next
    msr     tpidr_el1, xzr
    mrs     x12, mdscr_el1
    msr     mdscr_el1, x12
    bl      leaf
    fmov    d0, xzr
    report  'B'

    mov     x20, #'D'
    fp_off_synced
    msr     cpacr_el1, x22          // no isb, then about a million ALU instructions
    movz    x13, #0x4, lsl #16
1:  add     x14, x14, x13
    eor     x14, x14, x13, lsl #3
    subs    x13, x13, #1
    b.ne    1b
    fmov    d0, xzr
    report  'D'

    mov     x20, #'S'
    fp_off_synced
    msr     cpacr_el1, x22
    isb
    fmov    d0, xzr
    report  'S'
    b       off

leaf:
    ldr     x15, [sp, #-16]!        // a load and store through the stack, as a call would do
    str     x15, [sp], #16
    ret

trap:
    add     x21, x21, #1
    putc    'E'
    strb    w20, [x19]
    putc    ' '
    mrs     x10, esr_el1
    bl      hex
    putc    ' '
    mrs     x10, elr_el1
    bl      hex
    putc    '\n'
    mrs     x10, esr_el1
    lsr     x10, x10, #26
    cmp     x10, #7                 // only FP traps are recoverable here
    b.ne    off
    mov     x0, #0x300000
    msr     cpacr_el1, x0
    isb
    eret

hex:                                // prints x10 as 16 hex digits; clobbers x9, x11, x12
    mov     x11, #60
2:  lsr     x12, x10, x11
    and     x12, x12, #0xf
    cmp     x12, #10
    add     x9, x12, #'0'
    add     x12, x12, #('a' - 10)
    csel    x9, x12, x9, ge
    strb    w9, [x19]
    subs    x11, x11, #4
    b.ge    2b
    ret

off:
    movz    w0, #0x8400, lsl #16    // PSCI SYSTEM_OFF
    movk    w0, #0x0008
    hvc     #0
3:  wfi
    b       3b

    .balign 2048
vectors:                            // all 16 entries go to trap
    .rept 16
    b       trap
    .balign 128
    .endr
    .balign 16
    .space  1024
stack_top:
_end:
