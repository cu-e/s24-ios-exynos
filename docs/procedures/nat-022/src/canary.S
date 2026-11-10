/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-022 XNU-free stage-0 canary. Draws a marker before any decision, never
 * halts silently. The plain and fault images perform no MMIO other than
 * framebuffer stores; the canary-trig image (markerlib.c built with MK_TRIG=1)
 * additionally reads DECON0 GLOBAL_CON/TRIG_CON/FRAME_COUNT and writes only
 * TRIG_CON and SHD_REG_UP_REQ (see decon-trigger-facts.md), after the first
 * marker has been drawn. */
	.section .text.head, "ax"
	.globl _head
_head:
	b	_start
	.long	0
	.quad	0x80000
	.quad	_payload_start
	.quad	0xa
	.quad	0
	.quad	0
	.quad	0
	.ascii	"ARM\x64"
	.long	0

	.text
	.globl _start
_start:
	msr	daifset, #0xf
	/* Unlike the XNU loader's silent halt, a set MMU/cache bit is reported, not
	 * a reason to stop before drawing. If M=1 the mapping of this image, its
	 * stack and the framebuffer is unknown; the draw is then best effort. */
	msr	spsel, #1
	adr	x1, _stack_top
	mov	sp, x1
	mov	x22, x0			/* S-Boot DTB pointer, not dereferenced unless magic-checked */
	adr	x0, _head
	adr	x1, _end
	mov	x2, x22
	bl	mk_fb_safe
	cbz	x0, halt		/* would overwrite ourselves or the DTB: no marker */
	mrs	x19, CurrentEL
	mov	x20, xzr
	mov	x21, xzr
	cmp	x19, #8
	b.ne	1f
	mrs	x20, sctlr_el2
1:	mrs	x21, sctlr_el1
	/* Current-EL SCTLR is x20 at EL2, x21 at EL1. */
	cmp	x19, #8
	csel	x20, x20, x21, eq
	mov	x0, x19
	mov	x1, x20
	mov	x2, x21
	bl	mk_entry_frame
	cmp	x19, #4
	b.eq	3f
	cmp	x19, #8
	b.eq	3f
	mov	x0, #3			/* MK_ST_GATE_EL */
	mov	x1, x19
	mov	x2, x20
	mov	x3, x21
	bl	mk_gate_halt
3:	adr	x1, vectors
	cmp	x19, #8
	b.eq	4f
	msr	vbar_el1, x1
	b	5f
4:	msr	vbar_el2, x1
5:	isb
	mov	x0, x19
	mov	x1, x20
	mov	x2, x21
	bl	canary_main
	b	.

halt:
	wfe
	b	halt

.macro vent slot
	.balign	0x80
	mov	x0, #\slot
	b	exc_common
.endm
	.balign	0x800
vectors:
	vent 0
	vent 1
	vent 2
	vent 3
	vent 4
	vent 5
	vent 6
	vent 7
	vent 8
	vent 9
	vent 10
	vent 11
	vent 12
	vent 13
	vent 14
	vent 15

exc_common:
	adr	x1, _exc_stack_top
	mov	sp, x1
	mrs	x1, CurrentEL
	cmp	x1, #8
	b.eq	6f
	mrs	x1, esr_el1
	mrs	x2, elr_el1
	mrs	x3, far_el1
	b	7f
6:	mrs	x1, esr_el2
	mrs	x2, elr_el2
	mrs	x3, far_el2
7:	bl	mk_exception_loop
	b	.

	.section .data, "aw"
	.balign 16
	.space 0x4000
_stack_top:
	.space 0x4000
_exc_stack_top:
