/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-031: the loader's return stub for the payload kernel's assembly checkpoints (loader-diag-xnu-ckpt).
 *
 * The kernel's checkpoint macro (NAT-029) ends in `br x9` to slot[1], which the loader filled with the
 * address of this stub. Arrival state: EL1, MMU off, DAIF masked, x0 = x1 = 0, x2 = 2, x3 = checkpoint
 * number, SP whatever the kernel had. The macro itself clobbers x0..x3 and x9..x11 (NAT-030 checked on
 * the payload bytes that nothing after a site reads them before writing them); every other register and
 * the SP are live kernel state, so all of them are saved on the loader's own stack, the C code runs there,
 * and they are restored before the branch to the continuation (site + 60) that nat031_ckpt_c returns.
 * If nat031_ckpt_c does not return (the report is a hold) nothing is restored.
 *
 * SIMD/FP: the FP/SIMD registers are NOT saved. The loader's C code is built with zig cc, whose
 * -mgeneral-regs-only does not keep SIMD out of the marker code (the earlier loader images already contain
 * q-register copies), so the marker routines run with CPACR_EL1.FPEN as the loader set it. Model fact
 * (NAT-030): the kernel's start code writes CPACR_EL1 only after checkpoint 5 (0x300000) and executes no
 * SIMD instruction up to arm_init, so at checkpoints 1..5 FPEN is still enabled and there is no live SIMD
 * state to lose. nat031_ckpt_c and the decision code themselves are built without FP/SIMD (build.py NO_SIMD).
 *
 * The frame is struct nat031_frame (x0..x30, kernel SP): 0x100 bytes, 16-byte aligned. */
	.text
	.balign	16
	.globl	nat031_stub
nat031_stub:
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
	bl	nat031_ckpt_c
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
