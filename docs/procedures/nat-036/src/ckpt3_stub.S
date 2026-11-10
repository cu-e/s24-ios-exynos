/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-036: the return stub of loader-diag-xnu-ckpt3. The prologue and the frame are NAT-034's (ckpt2_stub.S): a 0x100 frame
 * on _stack_top holding x0..x30 and the kernel's SP, the MMU turned off first when the arrival came from loader_jump with
 * the private TTBR0. The C routine is nat036_ckpt_c and it returns two values in x0, x1:
 *
 *   x1 == 0  assembly resume: x0 is the continuation, every register but x9 is restored from the frame (as NAT-034).
 *   x1 != 0  C resume (the arrival was a C checkpoint, inside the kernel's loader_jump): x0 is a struct nat036_cres
 *            { ttbr0, ret, gadget }. The state loader_jump had at the early-return test is rebuilt, and the stub branches
 *            to the kernel's own _set_mmu_ttb (gadget) with x0 = the kernel's TTBR0 and x30 = loader_jump's early-return
 *            epilogue (ret). The gadget replaces the private TTBR0 with the kernel's, the epilogue restores x29/x30 from
 *            loader_jump's frame (still on the kernel stack) and returns into arm_init as an ordinary return.
 *
 * What the C resume restores: x18..x28 (loader_jump on the early-return path leaves callee-saved registers untouched, and
 * the stub's own C code preserves them by the ABI), the kernel's SP, SCTLR_EL1 with M and C back on (the arrival value, saved
 * by the prologue in the x11 slot). x0 and x30 are set as above; x1..x17 and x29 are scratch for the kernel at this point
 * (the checkpoint call is a function call: caller-saved registers are dead, x29 comes back from the frame). NZCV is not
 * restored (dead across the call). DAIF is not touched: loader_jump masked it before the branch and the kernel runs with it
 * masked there (NAT-035 section 2; not provable in the model, see the README).
 *
 * Everything from the first instruction to the msr that turns the MMU on again runs with the MMU off, so every access by
 * physical address is valid; from that msr to the branch the MMU is on with the private table, which maps only the 2 MiB
 * block holding this code (the loader's installer refuses an image whose stub straddles a block). The branch itself is the
 * last instruction of the block. TLB: the stage-1 TLB is invalidated (local) before the MMU is turned on, so no entry made
 * for any earlier TTBR0 survives into the private-table window. The tlbi is a non-shareable vmalle1: one CPU runs. */
	.text
	.balign	16
	.globl	nat036_stub
	.globl	nat036_stub_end
nat036_stub:
	mrs	x11, sctlr_el1
	tbz	w11, #0, 1f
	mov	x10, #5
	bic	x10, x11, x10
	msr	sctlr_el1, x10
	isb
1:
	mov	x9, sp
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
	bl	nat036_ckpt_c
	cbnz	x1, 2f
	/* assembly resume */
	mov	x9, x0
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
2:
	/* C resume. All loads from the frame and from the cres block are done here, MMU off. */
	mov	x9, x0
	ldp	x18, x19, [sp, #144]
	ldp	x20, x21, [sp, #160]
	ldp	x22, x23, [sp, #176]
	ldp	x24, x25, [sp, #192]
	ldp	x26, x27, [sp, #208]
	ldr	x28, [sp, #224]
	ldr	x11, [sp, #88]			/* the arrival SCTLR_EL1 (M and C set) */
	ldr	x10, [sp, #248]			/* the kernel's SP */
	ldp	x0, x30, [x9]			/* x0 = the kernel's TTBR0, x30 = loader_jump's epilogue */
	ldr	x12, [x9, #16]			/* the gadget: _set_mmu_ttb */
	mov	sp, x10
	dsb	sy
	tlbi	vmalle1
	dsb	nsh
	isb
	msr	sctlr_el1, x11
	isb
	br	x12
nat036_stub_end:
