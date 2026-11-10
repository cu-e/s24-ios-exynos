/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-028: install the XNU-entry stub into the kernel copy. Host-testable; no libc, no globals.
 *
 * The installer only ever overwrites NOP padding: word 0 of the entry (the kernel's own first
 * instruction, a branch in the measured payload) plus the following words, which must all be
 * NOPs. Anything else, a misaligned entry or too little room makes it refuse (nonzero return,
 * nothing written). It does not replay the kernel's first instruction: the variant that uses it
 * must never be described as executing XNU code. */
#ifndef NAT028_XNU_ENTRY_H
#define NAT028_XNU_ENTRY_H
#include <stdint.h>

#define NAT028_STUB_BYTES	0x28u
#define NAT028_STUB_WORDS	(NAT028_STUB_BYTES / 4)
#define NAT028_LIT_SP_OFF	0x18u
#define NAT028_LIT_FN_OFF	0x20u
#define NAT028_NOP		0xd503201fu

enum nat028_rc {
	NAT028_OK = 0,
	NAT028_ENTRY_MISALIGNED = 1,	/* entry not 8-byte aligned: the 64-bit literals must be (MMU off) */
	NAT028_NO_ROOM = 2,		/* file-backed bytes from the entry to the segment end < stub */
	NAT028_NOT_PADDING = 3,		/* a word the stub would overwrite (after word 0) is not a NOP */
	NAT028_BAD_TEMPLATE = 4		/* literal slots outside the template or not 8-aligned */
};

/* Bytes of the segment containing entry_va that are file-backed, from the entry to the end of
 * the file-backed range; 0 if no segment contains it. segs = struct payload_seg[nsegs] of the
 * loader (four uint64_t each: vmaddr, vmsize, file_off, file_size). */
uint64_t nat028_entry_room(const void *segs, uint32_t nsegs, uint64_t entry_va);

/* Copies the nwords-word template over entry_pa, then writes sp and fn into the literal slots.
 * *orig0 receives the entry word that was replaced. All writes are aligned 32-bit stores. */
int nat028_install_stub_tmpl(uintptr_t entry_pa, uint64_t room, const uint32_t *tmpl, uint32_t nwords,
    uint32_t lit_sp_off, uint32_t lit_fn_off, uint64_t sp, uint64_t fn, uint32_t *orig0);

#ifndef NAT028_HOST
/* Loader build: the template is nat028_stub_begin..nat028_stub_end from xnu_stub.S. */
int nat028_install_stub(uintptr_t entry_pa, uint64_t room, uint64_t sp, uint64_t fn, uint32_t *orig0);
#endif
#endif
