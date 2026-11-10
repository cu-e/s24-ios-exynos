/* SPDX-License-Identifier: GPL-2.0-only */
#include "marker.h"
#ifndef CANARY_FAULT
#define CANARY_FAULT 0
#endif

/* Reached with BL and a valid stack. The probe round-trips through sp. */
void canary_main(uint64_t currentel, uint64_t sctlr_cur, uint64_t sctlr_el1)
{
	volatile uint64_t probe[4];
	uint32_t ok = 1;
	for (int i = 0; i < 4; i++) probe[i] = 0xA5A5000000000000ULL + (uint64_t)i;
	for (int i = 0; i < 4; i++)
		if (probe[i] != 0xA5A5000000000000ULL + (uint64_t)i) ok = 0;
	mk_canary_loop(currentel, sctlr_cur, sctlr_el1, ok, CANARY_FAULT);
}
