/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-022 framebuffer band markers. Host-testable; no libc, no globals.
 *
 * A frame is 32 bits: kind[31:28] idx[27:24] data16[23:8] crc8[7:0].
 * It is drawn as MK_BANDS contiguous 256 KiB bands of the bootargs-reported
 * framebuffer (s3cfb.bootloaderfb): band 0 all-ones (sync high), band 1 zero
 * (sync low), bands 2.. the 32 bits MSB first. Bands are contiguous memory, so
 * the decoder is independent of the unknown row stride; only the stride is
 * needed to map a photographed row to a band (decode.py searches candidates).
 * One-bits are 0xFFFFFFFF, zero-bits 0x00000000: no assumed channel order.
 */
#ifndef NAT022_MARKER_H
#define NAT022_MARKER_H
#include <stdint.h>

#define MK_FB_BASE	0xFA200000ULL	/* NAT-005: normal-boot bootarg; unverified for this loader entry */
#define MK_BAND_BYTES	0x40000ULL
#define MK_PAYLOAD_BITS	32
#define MK_BANDS	(2 + MK_PAYLOAD_BITS)
#define MK_FREQ_FALLBACK 25600000ULL
#define MK_DWELL_TENTHS	12		/* 1.2 s per frame */

enum mk_kind {
	MK_ENTRY = 1,	/* data: EL[15:14] M C I (current EL) [13:11], M C I (EL1) [10:8] */
	MK_BOOTID = 2,	/* idx 0 = CNTVCT[15:0], idx 1 = CNTVCT[31:16] at first instruction */
	MK_STAGE = 3,	/* data = enum mk_stage */
	MK_ESR = 4,	/* idx 0..3 = bits 63:48 .. 15:0 */
	MK_ELR = 5,
	MK_FAR = 6,
	MK_SLOT = 7,	/* vector slot 0..15 */
	MK_CHECK = 8,	/* canary self-checks: stack word, call depth */
	MK_REG = 9	/* canary-trig only: DECON0 kick report, idx = enum mk_reg_idx */
};

/* DECON0 kick report (canary-trig). Values are what the code read, not inferences. */
enum mk_reg_idx {
	MK_REG_STATUS = 0,	/* data = enum mk_kick_status of the most recent kick */
	MK_REG_GC_HI = 1, MK_REG_GC_LO = 2,	/* GLOBAL_CON as read before the writes */
	MK_REG_TC0_HI = 3, MK_REG_TC0_LO = 4,	/* TRIG_CON as read before the writes */
	MK_REG_TC1_HI = 5, MK_REG_TC1_LO = 6,	/* TRIG_CON read back after the writes */
	MK_REG_FC_PREV = 7, MK_REG_FC_NOW = 8,	/* FRAME_COUNT[15:0] at the previous / this kick */
	MK_REG_N = 9			/* data = kick count */
};

enum mk_kick_status {
	MK_KS_NONE = 0,
	MK_KS_SENT_HW = 1,	/* global update request + HW-trigger unmask written */
	MK_KS_SENT_SW = 2,	/* global update request + SW-trigger written */
	MK_KS_SKIP_OFF = 3,	/* GLOBAL_CON shows DECON not enabled: nothing written */
	MK_KS_SKIP_VIDEO = 4,	/* GLOBAL_CON shows video mode: nothing written */
	MK_KS_SKIP_MMU = 5,	/* MMU on at the current EL: MMIO mapping unknown, nothing touched */
	MK_KS_POISONED = 6	/* an earlier kick faulted: no further MMIO */
};

/* NAT-022 canary-trig register contract (source: decon-trigger-facts.md). */
#define MK_DECON0_BASE		0x19100000ULL
#define MK_DECON_FRAME_COUNT	0x0004u
#define MK_DECON_GLOBAL_CON	0x0020u
#define MK_DECON_TRIG_CON	0x0030u
#define MK_DECON_SHD_REG_UP_REQ	0x0050u
#define MK_GC_DECON_EN		((1u << 1) | (1u << 0))
#define MK_GC_OP_CMD		(1u << 8)
#define MK_TC_HW_TRIG_EN	(1u << 0)
#define MK_TC_SW_TRIG_DET_EN	(1u << 1)
#define MK_TC_HW_TRIG_MASK	(1u << 4)
#define MK_TC_SW_TRIG_EN	(1u << 8)
#define MK_SHD_GLOBAL		(1u << 31)

enum mk_stage {
	MK_ST_ENTRY = 0x01,	/* first instruction drawn */
	MK_ST_GATE_MC = 0x02,	/* halted: MMU or cache on at entry */
	MK_ST_GATE_EL = 0x03,	/* halted: unsupported EL */
	MK_ST_CANARY_C = 0x10,	/* canary C code reached through a call with a valid stack */
	MK_ST_CANARY_BRK = 0x11,	/* about to execute BRK #0x1234 (fault variant) */
	MK_ST_EXC = 0x1f,	/* exception record follows */
	MK_ST_LOADER_MAIN = 0x20,
	MK_ST_LOADER_FB = 0x21,
	MK_ST_LOADER_MEM = 0x30,	/* memory window chosen */
	MK_ST_LOADER_ZERO = 0x31,
	MK_ST_LOADER_COPY = 0x32,
	MK_ST_LOADER_ADT = 0x33,
	MK_ST_PRE_JUMP = 0x40,	/* loader finished; jump pending. NOT proof of kernel entry */
	MK_ST_XNU_ENTRY = 0x50	/* reserved: only a marker executed inside XNU's first instructions may use it */
};

static inline uint32_t mk_crc8(uint32_t v24)
{
	uint32_t crc = 0;
	for (int b = 2; b >= 0; b--) {
		crc ^= (v24 >> (8 * b)) & 0xff;
		for (int i = 0; i < 8; i++)
			crc = (crc & 0x80) ? ((crc << 1) ^ 0x07) & 0xff : (crc << 1) & 0xff;
	}
	return crc;
}

static inline uint32_t mk_frame(uint32_t kind, uint32_t idx, uint32_t data16)
{
	uint32_t v = ((kind & 0xf) << 20) | ((idx & 0xf) << 16) | (data16 & 0xffff);
	return (v << 8) | mk_crc8(v);
}

/* Bit of band b (b >= 2) for a frame: MSB first. */
static inline uint32_t mk_band_value(uint32_t frame, uint32_t b)
{
	if (b == 0) return 1;
	if (b == 1) return 0;
	return (frame >> (31 - (b - 2))) & 1;
}

/* Library entry points (markerlib.c). They need a valid sp. A caller that
 * cannot prove the mapping (MMU on at entry) still calls them: a failed draw
 * is indistinguishable from the old silent halt and is reported as such. */
/* Nonzero only if neither the image, nor a valid-magic DTB at dtb, overlaps the
 * marker region. Prevents the canary from overwriting itself or its inputs. */
int mk_fb_safe(uint64_t image_start, uint64_t image_end, uint64_t dtb);
void mk_entry_frame(uint64_t currentel, uint64_t sctlr_cur, uint64_t sctlr_el1);
void mk_gate_halt(uint64_t stage, uint64_t currentel, uint64_t sctlr_cur, uint64_t sctlr_el1) __attribute__((noreturn));
void mk_stage(uint32_t stage);

void mk_canary_loop(uint64_t currentel, uint64_t sctlr_cur, uint64_t sctlr_el1, uint32_t stack_ok, int fault);

/* Cycles BOOTID/ENTRY/STAGE then exception registers. */
void mk_exception_loop(uint32_t slot, uint64_t esr, uint64_t elr, uint64_t far) __attribute__((noreturn));
#endif
