/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-028: template of the stub the loader copies over the first words of the XNU kernel
 * copy's entry point (loader-diag-xnu-entry only). Position independent: only ADR and
 * PC-relative literal loads. The loader fills the two literal slots (a stack top and the
 * address of mk_xnu_entry_hold) after the copy. At entry x0 is whatever the loader's jump
 * left there (boot_args PA); it is passed on, together with the stub's own PC, so the marker
 * can show where the stub really ran. The stub never returns and replays no kernel word.
 *
 * Layout (40 bytes; literals 8-byte aligned when the copy is):
 *   +0x00 mov x1, x0
 *   +0x04 adr x0, .Lstub0                (the stub's own address; a local label, so the assembler
 *                                         resolves it and the template bytes are final before linking)
 *   +0x08 ldr x16, nat028_lit_sp
 *   +0x0c mov sp, x16
 *   +0x10 ldr x16, nat028_lit_fn
 *   +0x14 br  x16
 *   +0x18 .quad stack top
 *   +0x20 .quad mk_xnu_entry_hold
 */
	.text
	.balign	8
	.globl	nat028_stub_begin
	.globl	nat028_stub_end
nat028_stub_begin:
.Lstub0:
	mov	x1, x0
	adr	x0, .Lstub0
	ldr	x16, nat028_lit_sp
	mov	sp, x16
	ldr	x16, nat028_lit_fn
	br	x16
nat028_lit_sp:
	.quad	0
nat028_lit_fn:
	.quad	0
nat028_stub_end:
	.if (nat028_lit_sp - nat028_stub_begin) != 0x18
	.error "NAT028_LIT_SP_OFF changed"
	.endif
	.if (nat028_lit_fn - nat028_stub_begin) != 0x20
	.error "NAT028_LIT_FN_OFF changed"
	.endif
	.if (nat028_stub_end - nat028_stub_begin) != 0x28
	.error "NAT028_STUB_BYTES changed"
	.endif
