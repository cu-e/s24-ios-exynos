/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-062: what nat036_ckpt_c calls to send the payload kernel's own console log (loader_log, NAT-061) to the host over the
 * NAT-047 USB log engine. Declarations only; the code is glue62_impl.h, included by markerlib52.c after glue52_impl.h (it needs
 * markerlib47.c's n47_* formatters and g_nat047 and markerlib.c's mk_wait_tenths, which are static in that translation unit). */
#ifndef NAT062_GLUE62_H
#define NAT062_GLUE62_H
#include <stdint.h>

#define NAT062_WHY_FINAL	1u	/* the last stop of the list: the kernel is resumed after the dump and runs on */
#define NAT062_WHY_RETURN	2u	/* the kernel's own return (reason 0: loader_return / loader_return_after / a panic): the loader holds after the dump */

/* The payload's loader_log (NAT-029 payload analysis, NAT-061): VA of the first byte, and the size of the array. A stop passes the
 * log in x0 (PA), x1 (length) because loader_jump() does; nothing is read unless x0 is exactly this symbol's PA and x1 fits. */
#define NAT062_LOG_VA		0xfffffff007b90a00ULL
#define NAT062_LOG_MAX		0x180000ULL

/* Send the log of the kernel as TEXT records `KL begin ...`, `KL <offset> <escaped text>`, `KL end ...` (or `KL refused ...` when x0/x1
 * are not what loader_jump hands over). x0, x1 are the stop's registers, pa_minus_va the payload's PA - VA delta, why one of the above.
 * No-op while the engine is not up. Paced: after about 8 KiB of records it polls the engine for half a second, so the host (which
 * never acknowledges) reads the 32 KiB ring before it can wrap. */
void nat062_dump_log(uint64_t x0, uint64_t x1, uint64_t pa_minus_va, uint32_t why);
#endif
