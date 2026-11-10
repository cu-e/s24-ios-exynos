/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-034: the return stub of loader-diag-xnu-ckpt2. The body is the NAT-031 stub (ckpt_stub.S: save x0..x30 and the
 * kernel's SP in a 0x100 frame on _stack_top, call C, restore everything but x9, branch to the continuation) and the
 * contract documented there holds unchanged. What is new is the prologue and that the C routine is nat034_ckpt_c.
 *
 * The prologue makes the stub usable from two kinds of arrival. From an assembly checkpoint (x2 = 2, x3 = 1..5) the
 * kernel's macro has cleared SCTLR_EL1.M, as before. From a C checkpoint, loader_jump has switched TTBR0_EL1 to a
 * private table that maps only the 2 MiB block holding this code and arrives with the MMU and caches on; any other
 * address, among them possibly the stack, is not mapped there, so the MMU is turned off before the first memory access.
 * SIMD/FP registers are not saved (see ckpt_stub.S). */
	.text
	.balign	16
	.globl	nat034_stub
nat034_stub:
	/* Prologue, registers only (x9/x10 are free for the stub, x11 is the slot of the arrival SCTLR_EL1). An arrival from
	 * an assembly checkpoint has the MMU off already (the kernel's macro cleared M): this is two instructions and a
	 * branch. An arrival from loader_jump has the MMU on, with only the stub's own 2 MiB mapped: clear M and C and
	 * synchronise before the first memory access (the stack may be outside the block). Instruction fetch continues
	 * at the same address, which is identity-mapped by the block, so the fetch is the same before and after. */
	mrs	x11, sctlr_el1
	tbz	w11, #0, 1f
	mov	x10, #5
	bic	x10, x11, x10
	msr	sctlr_el1, x10
	isb
1:
	mov	x9, sp			/* the kernel's SP, in whichever bank SPSel selects: restored the same way */
	adrp	x10, _stack_top
	add	x10, x10, :lo12:_stack_top
	sub	x10, x10, #0x100
	mov	sp, x10
	stp	x0, x1, [sp, #0]
	stp	x2, x3, [sp, #16]
	stp	x4, x5, [sp, #32]
	stp	x6, x7, [sp, #48]
	stp	x8, x9, [sp, #64]
	stp	x10, x11, [sp, #80]
	stp	x12, x13, [sp, #96]
	stp	x14, x15, [sp, #112]
	stp	x16, x17, [sp, #128]
	stp	x18, x19, [sp, #144]
	stp	x20, x21, [sp, #160]
	stp	x22, x23, [sp, #176]
	stp	x24, x25, [sp, #192]
	stp	x26, x27, [sp, #208]
	stp	x28, x29, [sp, #224]
	str	x30, [sp, #240]
	str	x9, [sp, #248]
	mov	x0, sp
	bl	nat034_ckpt_c
	mov	x9, x0			/* continuation */
	ldp	x0, x1, [sp, #0]
	ldp	x2, x3, [sp, #16]
	ldp	x4, x5, [sp, #32]
	ldp	x6, x7, [sp, #48]
	ldp	x10, x11, [sp, #80]
	ldp	x12, x13, [sp, #96]
	ldp	x14, x15, [sp, #112]
	ldp	x16, x17, [sp, #128]
	ldp	x18, x19, [sp, #144]
	ldp	x20, x21, [sp, #160]
	ldp	x22, x23, [sp, #176]
	ldp	x24, x25, [sp, #192]
	ldp	x26, x27, [sp, #208]
	ldp	x28, x29, [sp, #224]
	ldr	x30, [sp, #240]
	ldr	x8, [sp, #64]
	ldr	x10, [sp, #248]
	mov	sp, x10
	br	x9
