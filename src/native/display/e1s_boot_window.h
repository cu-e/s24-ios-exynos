/* SPDX-License-Identifier: GPL-2.0-only
 *
 * Read-only reader for the boot scanout window that S-Boot leaves on the
 * s5e9945 (Exynos 2400, SM-S921B "e1s") DECON0. UI-007, 2026-11-10.
 *
 * Register offsets and bit fields are transcribed from the pinned Samsung
 * kernel (source id s24-linux, dx4m/android-kernel-samsung-e1s
 * 417484173abc2c4fa93e738ea82ad9f2e84911b1; identical in s24-bsp-reference
 * f85e53cfa5497ead5d78821efbac84e51f37a4e1), CAL directory cal_rt selected for
 * CONFIG_SOC_S5E9945 by drivers/gpu/drm/samsung/dpu/Makefile:7-9.
 * Exact file:line citations are in research/notes/native/UI-007-decon-boot-window.md
 * and src/native/display/register_facts.json. MMIO bases come from this
 * phone's runtime FDT (docs/procedures/ui-007/dpu-dt-facts.json).
 *
 * Contract: freestanding, <stdint.h> only, no libc calls, no writes. Every
 * hardware access is one aligned volatile 32-bit load from a caller-supplied
 * base. Nothing here has run on the phone: power-domain state, the meaning of
 * the shadow copies and SysMMU bypass remain native-run questions.
 */
#ifndef E1S_BOOT_WINDOW_H
#define E1S_BOOT_WINDOW_H

#include <stdint.h>

#define E1S_BW_WINDOWS		16u	/* MAX_WIN_PER_DECON, regs-decon.h:21 */
#define E1S_BW_CHANNELS		16u	/* DPP L0..L15 with dpp,id 0..15 (runtime FDT) */
#define E1S_BW_SYSMMU_MAX_VM	8u

/* DECON "main" (DECON0 0x19100000). */
#define E1S_DECON_GLOBAL_CON		0x0020u	/* regs-decon.h:134 */
#define E1S_GLOBAL_CON_OPMODE_CMD	(1u << 8)	/* regs-decon.h:140-142 */
#define E1S_GLOBAL_CON_RUN_STATUS	(1u << 4)	/* regs-decon.h:144 */
#define E1S_GLOBAL_CON_DECON_EN		(1u << 1)	/* regs-decon.h:145 */
#define E1S_GLOBAL_CON_DECON_EN_F	(1u << 0)	/* regs-decon.h:146 */
#define E1S_DECON_RSC_STATUS_0		0x0100u	/* channel 0..7 owner, regs-decon.h:257 */
#define E1S_DECON_RSC_STATUS_2		0x0108u	/* window 0..7 owner, regs-decon.h:277 */
#define E1S_RSC_IDLE			7u	/* exynos_drm_debug.c:49 */

/* DECON_WIN (0x19110000, one block for all DECONs: decon_reg.c:76-83) and
 * DECON0_WINCON (0x19130000): window n at n * 0x1000 (regs-decon.h:633). */
#define E1S_WIN_STRIDE			0x1000u
#define E1S_DECON_SHADOW		0x0800u	/* SHADOW_OFFSET, regs-decon.h:123 */
#define E1S_WIN_START_POSITION		0x000Cu	/* regs-decon.h:673 */
#define E1S_WIN_END_POSITION		0x0010u	/* regs-decon.h:677 */
#define E1S_WIN_POS_MASK		0x3FFFu	/* X [13:0], Y [29:16], regs-decon.h:674-679 */
#define E1S_DECON_CON_WIN		0x0000u	/* regs-decon.h:704 */
#define E1S_WINCON_EN			(1u << 0)	/* regs-decon.h:708 */
#define E1S_WINCON_MAPCOLOR_EN		(1u << 1)	/* regs-decon.h:707 */
#define E1S_WINCON_CHMAP_SHIFT		4u	/* regs-decon.h:705-706 */
#define E1S_WINCON_CHMAP_MASK		0xFu

/* DPU_DMA RDMA per channel (L0 0x19900000 ... see runtime FDT "dma" reg). */
#define E1S_DMA_SHADOW			0x0400u	/* DMA_SHD_OFFSET, regs-dpp.h:71-72 */
#define E1S_RDMA_IN_CTRL_0		0x0008u	/* regs-dpp.h:96 */
#define E1S_IDMA_IMG_FORMAT_SHIFT	8u	/* regs-dpp.h:102-103 */
#define E1S_IDMA_IMG_FORMAT_MASK	0x3Fu
#define E1S_IDMA_ROT_MASK		(0x7u << 4)	/* regs-dpp.h:144 */
#define E1S_IDMA_CSET_EN		(1u << 3)	/* regs-dpp.h:154 */
#define E1S_IDMA_SBWC_EN		(1u << 2)	/* regs-dpp.h:155 */
#define E1S_IDMA_SAJC_EN		(1u << 1)	/* AFBC/SAJC, regs-dpp.h:156-157 */
#define E1S_IDMA_BLOCK_EN		(1u << 0)	/* regs-dpp.h:159 */
#define E1S_IDMA_SBWC_LOSSY		(1u << 14)	/* regs-dpp.h:101 */
#define E1S_RDMA_SRC_WIDTH		0x0010u	/* [23:0], regs-dpp.h:161-163 */
#define E1S_RDMA_SRC_HEIGHT		0x0014u	/* [23:0], regs-dpp.h:165-167 */
#define E1S_RDMA_SRC_SIZE_MASK		0xFFFFFFu
#define E1S_RDMA_SRC_OFFSET		0x0018u	/* Y [31:16], X [15:0], regs-dpp.h:169-173 */
#define E1S_RDMA_IMG_SIZE		0x001Cu	/* H [31:16], W [15:0], regs-dpp.h:175-179 */
#define E1S_DMA_BASEADDR_P0		0x0040u	/* regs-dpp.h:193-201 */
#define E1S_DMA_SRC_STRIDE_0		0x0050u	/* regs-dpp.h:206 */
#define E1S_DMA_STRIDE_SEL		(1u << 31)	/* regs-dpp.h:211 */

/* IDMA_IMG_FORMAT codes, regs-dpp.h:105-141. */
#define E1S_FMT_ARGB8888	0u
#define E1S_FMT_XRGB8888	4u

/* SysMMU v9 (samsung-iommu-v9.h): per-VM control at 0x8000 + vm * 0x1000. */
#define E1S_SYSMMU_CTRL_VM		0x8000u	/* samsung-iommu-v9.h:31 */
#define E1S_SYSMMU_VM_STRIDE		0x1000u	/* samsung-iommu-v9.h:14,40 */
#define E1S_SYSMMU_CTRL_MMU_ENABLE	(1u << 0)	/* samsung-iommu-v9.h:43 */

/* Physical bases measured in this phone's runtime FDT (NAT-005 blob,
 * sanitized in docs/procedures/ui-007/dpu-dt-facts.json). */
#define E1S_PA_DECON0_MAIN	0x19100000u
#define E1S_PA_DECON_WIN	0x19110000u
#define E1S_PA_DECON0_WINCON	0x19130000u
#define E1S_PA_SYSMMU_DPU_DMA	0x19840000u
#define E1S_PA_SYSMMU_VMID_MASK	0x3u
#define E1S_PA_DPP_DMA(n)	((n) < 8u ? 0x19900000u + 0x1000u * (n) \
				 : 0x19B00000u + 0x1000u * ((n) - 8u))

/* Caller-supplied bases (identity-mapped or device-mapped MMIO). Zero means
 * "not mapped": the reader never touches it. */
struct e1s_dpu_mmio {
	uintptr_t decon_main;
	uintptr_t decon_win;
	uintptr_t decon_wincon;
	uintptr_t dpp_dma[E1S_BW_CHANNELS];
	uintptr_t sysmmu;		/* optional: DPU_DMA_TOP SysMMU */
	uint32_t sysmmu_vmid_mask;	/* runtime FDT vmid_mask */
};

enum e1s_bw_status {
	E1S_BW_OK = 0,
	E1S_BW_ERR_ARGS = 1,		/* missing DECON bases or output */
	E1S_BW_ERR_NO_WINDOW = 2,	/* no enabled DMA window on DECON0 */
	E1S_BW_ERR_MULTIPLE = 3,	/* more than one enabled DMA window */
	E1S_BW_ERR_UNSTABLE = 4,	/* register and shadow copies disagree */
	E1S_BW_ERR_NO_CHANNEL = 5,	/* channel has no caller-supplied DMA base */
	E1S_BW_ERR_LAYOUT = 6,		/* compressed, rotated or CSET layout */
	E1S_BW_ERR_FORMAT = 7,		/* not a packed RGB format */
	E1S_BW_ERR_GEOMETRY = 8,	/* zero/inverted sizes or crop outside source */
	/* validation only */
	E1S_BW_ERR_DECON_OFF = 20,
	E1S_BW_ERR_TRANSLATED = 21,	/* SysMMU translates: base is an IOVA */
	E1S_BW_ERR_TRANSLATION_UNKNOWN = 22,
	E1S_BW_ERR_BASE = 23,
	E1S_BW_ERR_SIZE = 24,
	E1S_BW_ERR_MODE = 25,		/* not full-panel, unscaled, at origin */
	E1S_BW_ERR_PIXEL = 26		/* not ARGB8888/XRGB8888 */
};

#define E1S_BW_F_DECON_ENABLED		(1u << 0)
#define E1S_BW_F_DECON_RUNNING		(1u << 1)
#define E1S_BW_F_CMD_MODE		(1u << 2)
#define E1S_BW_F_EXPLICIT_STRIDE	(1u << 3)
#define E1S_BW_F_BLOCK_MODE		(1u << 4)
#define E1S_BW_F_COLORMAP_WINDOWS	(1u << 5)
#define E1S_BW_F_RSC_MISMATCH		(1u << 6)
#define E1S_BW_F_SYSMMU_CHECKED		(1u << 7)
#define E1S_BW_F_SYSMMU_TRANSLATING	(1u << 8)

struct e1s_boot_window {
	uint32_t status;		/* enum e1s_bw_status */
	uint32_t enabled;		/* 1 when exactly one DMA window was decoded */
	uint32_t window;		/* DECON window index */
	uint32_t channel;		/* WIN_CHMAP = DPP id (exynos_drm_decon.c:819) */
	uint64_t base;			/* DMA_BASEADDR_P0: device address of frame start */
	uint32_t stride;		/* bytes per source row */
	uint32_t format;		/* IDMA_IMG_FORMAT code */
	uint32_t bytes_per_pixel;	/* 0 when unsupported */
	uint32_t width, height;		/* RDMA_IMG_SIZE: scanned crop */
	uint32_t src_width, src_height;	/* RDMA_SRC_WIDTH/HEIGHT: frame in buffer */
	uint32_t src_x, src_y;		/* RDMA_SRC_OFFSET */
	uint32_t win_x0, win_y0, win_x1, win_y1;	/* inclusive panel rect */
	uint32_t enabled_mask;		/* every enabled window (incl. colormap) */
	uint32_t colormap_mask;		/* enabled colormap (solid colour) windows */
	uint32_t flags;			/* E1S_BW_F_* */
	uint32_t global_con;		/* raw GLOBAL_CON, for logging */
	uint32_t in_ctrl;		/* raw RDMA_IN_CTRL_0, for logging */
};

#define E1S_BW_ALLOW_UNKNOWN_TRANSLATION	(1u << 0)

/* Decode the boot window. Returns out->status. Only reads. */
uint32_t e1s_boot_window_read(const struct e1s_dpu_mmio *mmio, struct e1s_boot_window *out);

/* Check a decoded window against the expected CPU framebuffer contract:
 * DECON0 enabled, translation known to be off (unless allowed), frame start
 * at expect_base, ARGB8888/XRGB8888, full-panel unscaled scanout of
 * width x height from offset (0,0), stride*height inside expect_size. */
uint32_t e1s_boot_window_validate(const struct e1s_boot_window *w, uint64_t expect_base,
    uint64_t expect_size, uint32_t width, uint32_t height, uint32_t options);

/* Fill mmio with the physical bases from the runtime FDT facts above. */
void e1s_dpu_mmio_default(struct e1s_dpu_mmio *mmio);

#endif
