/* SPDX-License-Identifier: GPL-2.0-only */
#include "xnu_entry.h"

struct nat028_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

uint64_t nat028_entry_room(const void *segs, uint32_t nsegs, uint64_t entry_va)
{
	const struct nat028_seg *s = (const struct nat028_seg *)segs;

	for (uint32_t i = 0; i < nsegs; i++)
		if (entry_va >= s[i].vmaddr && entry_va - s[i].vmaddr < s[i].file_size)
			return s[i].file_size - (entry_va - s[i].vmaddr);
	return 0;
}

int nat028_install_stub_tmpl(uintptr_t entry_pa, uint64_t room, const uint32_t *tmpl, uint32_t nwords,
    uint32_t lit_sp_off, uint32_t lit_fn_off, uint64_t sp, uint64_t fn, uint32_t *orig0)
{
	volatile uint32_t *dst = (volatile uint32_t *)entry_pa;
	uint32_t bytes = nwords * 4;

	if (nwords == 0 || lit_sp_off % 8 || lit_fn_off % 8 || lit_sp_off + 8 > bytes ||
	    lit_fn_off + 8 > bytes || lit_sp_off == lit_fn_off)
		return NAT028_BAD_TEMPLATE;
	if (entry_pa % 8)
		return NAT028_ENTRY_MISALIGNED;
	if (room < bytes)
		return NAT028_NO_ROOM;
	for (uint32_t i = 1; i < nwords; i++)
		if (dst[i] != NAT028_NOP)
			return NAT028_NOT_PADDING;
	*orig0 = dst[0];
	/* Word 0 last: until then the entry is still the kernel's own first word. */
	for (uint32_t i = nwords; i-- > 0;)
		dst[i] = tmpl[i];
	*(volatile uint32_t *)(entry_pa + lit_sp_off) = (uint32_t)sp;
	*(volatile uint32_t *)(entry_pa + lit_sp_off + 4) = (uint32_t)(sp >> 32);
	*(volatile uint32_t *)(entry_pa + lit_fn_off) = (uint32_t)fn;
	*(volatile uint32_t *)(entry_pa + lit_fn_off + 4) = (uint32_t)(fn >> 32);
#ifndef NAT028_HOST
	__asm__ volatile("dsb sy" ::: "memory");
#endif
	return NAT028_OK;
}

#ifndef NAT028_HOST
extern const uint32_t nat028_stub_begin[], nat028_stub_end[];

int nat028_install_stub(uintptr_t entry_pa, uint64_t room, uint64_t sp, uint64_t fn, uint32_t *orig0)
{
	if ((uintptr_t)nat028_stub_end - (uintptr_t)nat028_stub_begin != NAT028_STUB_BYTES)
		return NAT028_BAD_TEMPLATE;
	return nat028_install_stub_tmpl(entry_pa, room, nat028_stub_begin, NAT028_STUB_WORDS,
	    NAT028_LIT_SP_OFF, NAT028_LIT_FN_OFF, sp, fn, orig0);
}
#endif
