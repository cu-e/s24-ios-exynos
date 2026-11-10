// VM-051 guest code. Runs at EL1 with the MMU off at guest physical 0x80000000.
// Every store to 0x09000000+off leaves the guest as KVM_EXIT_MMIO (no memslot there).
// KVM's PSCI handler writes x0-x3 (SMCCC results), so the base and counters live in x19-x22.
// The block is position independent and is copied into guest RAM by the helper.
    .section .rodata.guest, "a"
    .balign 4
    .globl vm051_guest_start, vm051_guest_end
vm051_guest_start:
    movz x19, #0x0900, lsl #16         // x19 = 0x09000000, the report window
    mov  w2, #'H'
    strb w2, [x19]                     // offset 0: console byte
    mov  w2, #'i'
    strb w2, [x19]
    movz w0, #0x8400, lsl #16          // PSCI_VERSION
    hvc  #0
    str  w0, [x19, #8]                 // offset 8: PSCI version
    mrs  x3, CurrentEL
    str  x3, [x19, #16]                // offset 16: CurrentEL
    mrs  x3, midr_el1
    str  x3, [x19, #24]                // offset 24: MIDR_EL1
    mrs  x3, cntfrq_el0
    str  x3, [x19, #32]                // offset 32: CNTFRQ_EL0
    mrs  x3, mpidr_el1
    str  x3, [x19, #40]                // offset 40: MPIDR_EL1
    movz x20, #10000                   // 10000 MMIO exits for the round-trip cost
1:  str  x20, [x19, #0x40]             // offset 0x40: exit-cost counter
    subs x20, x20, #1
    b.ne 1b
    str  xzr, [x19, #0x48]             // offset 0x48: start mark for the compute loop
    isb
    mrs  x21, cntvct_el0
    movz x20, #0x05f5, lsl #16         // 100000000 iterations
    movk x20, #0xe100
2:  subs x20, x20, #1
    b.ne 2b
    isb
    mrs  x22, cntvct_el0
    sub  x22, x22, x21
    str  x22, [x19, #48]               // offset 48: virtual-counter ticks of the loop
    movz w0, #0x8400, lsl #16          // PSCI SYSTEM_OFF = 0x84000008
    movk w0, #0x0008
    hvc  #0
3:  wfi                                 // not reached when SYSTEM_OFF works
    b    3b
vm051_guest_end:
