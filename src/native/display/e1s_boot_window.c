/* SPDX-License-Identifier: GPL-2.0-only
 *
 * Read-only s5e9945 DECON0 boot-window reader (UI-007). See e1s_boot_window.h
 * for the contract and research/notes/native/UI-007-decon-boot-window.md for
 * the register citations and the facts that remain unverified natively.
 */
#include "e1s_boot_window.h"

static uint32_t rd(uintptr_t base, uint32_t off)
{
	return *(const volatile uint32_t *)(base + off);
}

static void clear(struct e1s_boot_window *w)
{
	/* Field by field: a struct initialiser may become a memset call, which
	 * the -nostdlib loader does not provide. */
	w->status = E1S_BW_ERR_ARGS;
	w->enabled = 0; w->window = 0; w->channel = 0;
	w->base = 0; w->stride = 0; w->format = 0; w->bytes_per_pixel = 0;
	w->width = 0; w->height = 0; w->src_width = 0; w->src_height = 0;
	w->src_x = 0; w->src_y = 0;
	w->win_x0 = 0; w->win_y0 = 0; w->win_x1 = 0; w->win_y1 = 0;
	w->enabled_mask = 0; w->colormap_mask = 0; w->flags = 0;
	w->global_con = 0; w->in_ctrl = 0;
}

/* Bytes per pixel of the packed RGB IDMA formats, regs-dpp.h:105-134.
 * YUV, SBWC and unknown codes return 0. */
static uint32_t format_bpp(uint32_t fmt)
{
	if (fmt <= 7u)
		return 4;	/* ARGB/ABGR/RGBA/BGRA/XRGB/XBGR/RGBX/BGRX 8888 */
	if (fmt == 8u || fmt == 9u)
		return 2;	/* RGB565 / BGR565 */
	if (fmt >= 16u && fmt <= 19u)
		return 4;	/* 2101010 / 1010102 */
	if (fmt >= 32u && fmt <= 39u)
		return 8;	/* FP16 */
	return 0;
}

/* Register and its shadow copy must agree; otherwise an update is pending. */
static int stable(uintptr_t base, uint32_t off, uint32_t shadow, uint32_t *value)
{
	uint32_t a = rd(base, off), b = rd(base, off + shadow);
	*value = a;
	return a == b;
}

static uint32_t owner(uint32_t lo, uint32_t hi, uint32_t idx)
{
	uint32_t word = idx < 8u ? lo : hi;
	return (word >> ((idx & 7u) * 4u)) & 0xFu;	/* decon_reg.c:2887-2895 */
}

uint32_t e1s_boot_window_read(const struct e1s_dpu_mmio *m, struct e1s_boot_window *w)
{
	uint32_t i, win = 0, found = 0, wincon = 0, v;

	if (!w)
		return E1S_BW_ERR_ARGS;
	clear(w);
	if (!m || !m->decon_main || !m->decon_win || !m->decon_wincon ||
	    ((m->decon_main | m->decon_win | m->decon_wincon) & 3u))
		return w->status;

	w->global_con = rd(m->decon_main, E1S_DECON_GLOBAL_CON);
	if (w->global_con & (E1S_GLOBAL_CON_DECON_EN | E1S_GLOBAL_CON_DECON_EN_F))
		w->flags |= E1S_BW_F_DECON_ENABLED;
	if (w->global_con & E1S_GLOBAL_CON_RUN_STATUS)
		w->flags |= E1S_BW_F_DECON_RUNNING;
	if (w->global_con & E1S_GLOBAL_CON_OPMODE_CMD)
		w->flags |= E1S_BW_F_CMD_MODE;

	for (i = 0; i < E1S_BW_WINDOWS; i++) {
		if (!stable(m->decon_wincon, i * E1S_WIN_STRIDE + E1S_DECON_CON_WIN,
		    E1S_DECON_SHADOW, &v))
			return w->status = E1S_BW_ERR_UNSTABLE;
		if (!(v & E1S_WINCON_EN))
			continue;
		w->enabled_mask |= 1u << i;
		if (v & E1S_WINCON_MAPCOLOR_EN) {
			/* Solid-colour window: no DMA fetch behind it. */
			w->colormap_mask |= 1u << i;
			w->flags |= E1S_BW_F_COLORMAP_WINDOWS;
			continue;
		}
		found++;
		win = i;
		wincon = v;
	}
	if (!found)
		return w->status = E1S_BW_ERR_NO_WINDOW;
	if (found > 1)
		return w->status = E1S_BW_ERR_MULTIPLE;

	w->window = win;
	w->channel = (wincon >> E1S_WINCON_CHMAP_SHIFT) & E1S_WINCON_CHMAP_MASK;

	{
		uint32_t s, e, off = win * E1S_WIN_STRIDE;
		if (!stable(m->decon_win, off + E1S_WIN_START_POSITION, E1S_DECON_SHADOW, &s) ||
		    !stable(m->decon_win, off + E1S_WIN_END_POSITION, E1S_DECON_SHADOW, &e))
			return w->status = E1S_BW_ERR_UNSTABLE;
		w->win_x0 = s & E1S_WIN_POS_MASK;
		w->win_y0 = (s >> 16) & E1S_WIN_POS_MASK;
		w->win_x1 = e & E1S_WIN_POS_MASK;	/* inclusive: exynos_drm_decon.c:272-275 */
		w->win_y1 = (e >> 16) & E1S_WIN_POS_MASK;
	}

	{
		uint32_t ch0 = rd(m->decon_main, E1S_DECON_RSC_STATUS_0);
		uint32_t ch1 = rd(m->decon_main, E1S_DECON_RSC_STATUS_0 + 4u);
		uint32_t wn0 = rd(m->decon_main, E1S_DECON_RSC_STATUS_2);
		uint32_t wn1 = rd(m->decon_main, E1S_DECON_RSC_STATUS_2 + 4u);
		if (owner(ch0, ch1, w->channel) != 0u || owner(wn0, wn1, win) != 0u)
			w->flags |= E1S_BW_F_RSC_MISMATCH;	/* informational only */
	}

	{
		uintptr_t dma = m->dpp_dma[w->channel];
		uint32_t ctrl, sw, sh, so, is, p0, st;
		if (!dma || (dma & 3u))
			return w->status = E1S_BW_ERR_NO_CHANNEL;
		if (!stable(dma, E1S_RDMA_IN_CTRL_0, E1S_DMA_SHADOW, &ctrl) ||
		    !stable(dma, E1S_RDMA_SRC_WIDTH, E1S_DMA_SHADOW, &sw) ||
		    !stable(dma, E1S_RDMA_SRC_HEIGHT, E1S_DMA_SHADOW, &sh) ||
		    !stable(dma, E1S_RDMA_SRC_OFFSET, E1S_DMA_SHADOW, &so) ||
		    !stable(dma, E1S_RDMA_IMG_SIZE, E1S_DMA_SHADOW, &is) ||
		    !stable(dma, E1S_DMA_BASEADDR_P0, E1S_DMA_SHADOW, &p0) ||
		    !stable(dma, E1S_DMA_SRC_STRIDE_0, E1S_DMA_SHADOW, &st))
			return w->status = E1S_BW_ERR_UNSTABLE;

		w->in_ctrl = ctrl;
		w->format = (ctrl >> E1S_IDMA_IMG_FORMAT_SHIFT) & E1S_IDMA_IMG_FORMAT_MASK;
		w->bytes_per_pixel = format_bpp(w->format);
		w->base = p0;
		w->src_width = sw & E1S_RDMA_SRC_SIZE_MASK;
		w->src_height = sh & E1S_RDMA_SRC_SIZE_MASK;
		w->src_x = so & 0xFFFFu;
		w->src_y = so >> 16;
		w->width = is & 0xFFFFu;
		w->height = is >> 16;
		if (ctrl & E1S_IDMA_BLOCK_EN)
			w->flags |= E1S_BW_F_BLOCK_MODE;
		if (ctrl & (E1S_IDMA_SAJC_EN | E1S_IDMA_SBWC_EN | E1S_IDMA_CSET_EN |
		    E1S_IDMA_ROT_MASK | E1S_IDMA_SBWC_LOSSY))
			return w->status = E1S_BW_ERR_LAYOUT;
		if (!w->bytes_per_pixel)
			return w->status = E1S_BW_ERR_FORMAT;
		if (!w->width || !w->height || !w->src_width || !w->src_height ||
		    w->win_x1 < w->win_x0 || w->win_y1 < w->win_y0 ||
		    (uint64_t)w->src_x + w->width > w->src_width ||
		    (uint64_t)w->src_y + w->height > w->src_height)
			return w->status = E1S_BW_ERR_GEOMETRY;
		if (st & E1S_DMA_STRIDE_SEL) {
			/* Explicit pitch (written only with DMA_STRIDE_SEL,
			 * dpp_reg.c:1162). Its width below bit 31 is not stated. */
			w->stride = st & ~E1S_DMA_STRIDE_SEL;
			w->flags |= E1S_BW_F_EXPLICIT_STRIDE;
		} else {
			/* Samsung programs no pitch for uncompressed RGB and puts
			 * the frame width in RDMA_SRC_WIDTH (exynos_drm_dpp.c:368,
			 * dpp_reg.c:1156-1166): pitch = SRC_WIDTH * bytes/pixel.
			 * That the hardware derives it so is an inference. */
			uint64_t pitch = (uint64_t)w->src_width * w->bytes_per_pixel;
			if (pitch > 0xFFFFFFFFu)
				return w->status = E1S_BW_ERR_GEOMETRY;
			w->stride = (uint32_t)pitch;
		}
		if ((uint64_t)w->stride < (uint64_t)w->src_width * w->bytes_per_pixel)
			return w->status = E1S_BW_ERR_GEOMETRY;
	}

	if (m->sysmmu && !(m->sysmmu & 3u) && m->sysmmu_vmid_mask) {
		w->flags |= E1S_BW_F_SYSMMU_CHECKED;
		for (i = 0; i < E1S_BW_SYSMMU_MAX_VM; i++) {
			if (!(m->sysmmu_vmid_mask & (1u << i)))
				continue;
			if (rd(m->sysmmu, E1S_SYSMMU_CTRL_VM + i * E1S_SYSMMU_VM_STRIDE) &
			    E1S_SYSMMU_CTRL_MMU_ENABLE)
				w->flags |= E1S_BW_F_SYSMMU_TRANSLATING;
		}
	}

	w->enabled = 1;
	return w->status = E1S_BW_OK;
}

uint32_t e1s_boot_window_validate(const struct e1s_boot_window *w, uint64_t expect_base,
    uint64_t expect_size, uint32_t width, uint32_t height, uint32_t options)
{
	uint64_t need;

	if (!w || !width || !height)
		return E1S_BW_ERR_ARGS;
	if (w->status != E1S_BW_OK || !w->enabled)
		return w->status != E1S_BW_OK ? w->status : E1S_BW_ERR_NO_WINDOW;
	if (!(w->flags & E1S_BW_F_DECON_ENABLED))
		return E1S_BW_ERR_DECON_OFF;
	if (w->flags & E1S_BW_F_SYSMMU_TRANSLATING)
		return E1S_BW_ERR_TRANSLATED;
	if (!(w->flags & E1S_BW_F_SYSMMU_CHECKED) &&
	    !(options & E1S_BW_ALLOW_UNKNOWN_TRANSLATION))
		return E1S_BW_ERR_TRANSLATION_UNKNOWN;
	if (w->format != E1S_FMT_ARGB8888 && w->format != E1S_FMT_XRGB8888)
		return E1S_BW_ERR_PIXEL;
	if (w->src_x || w->src_y || w->width != width || w->height != height ||
	    w->src_width != width || w->src_height != height ||
	    w->win_x0 || w->win_y0 || w->win_x1 != width - 1u || w->win_y1 != height - 1u)
		return E1S_BW_ERR_MODE;
	/* A block region is a plane sub-rectangle programmed with IDMA_BLOCK_EN
	 * (exynos_drm_dpp.c:432-439, dpp_reg.c:293-303); what the panel shows
	 * there is not stated in source, so the frame is not known to be shown
	 * unmodified. */
	if (w->flags & E1S_BW_F_BLOCK_MODE)
		return E1S_BW_ERR_BLOCK;
	/* Windows stack by index (zpos k = k-th reserved window). A solid-colour
	 * window above the frame may hide it. window <= 15, so the shift is
	 * defined for uint32_t. */
	if (w->colormap_mask >> (w->window + 1u))
		return E1S_BW_ERR_COVERED;
	if (w->base != expect_base)
		return E1S_BW_ERR_BASE;
	if ((w->stride & 3u) || w->stride < (uint64_t)width * 4u)
		return E1S_BW_ERR_SIZE;
	need = (uint64_t)w->stride * height;	/* <= 2^32 * 2^16: no overflow */
	if (!expect_size || need > expect_size || expect_base > UINT64_MAX - need)
		return E1S_BW_ERR_SIZE;
	return E1S_BW_OK;
}

void e1s_dpu_mmio_default(struct e1s_dpu_mmio *m)
{
	uint32_t i;

	if (!m)
		return;
	m->decon_main = E1S_PA_DECON0_MAIN;
	m->decon_win = E1S_PA_DECON_WIN;
	m->decon_wincon = E1S_PA_DECON0_WINCON;
	for (i = 0; i < E1S_BW_CHANNELS; i++)
		m->dpp_dma[i] = E1S_PA_DPP_DMA(i);
	m->sysmmu = E1S_PA_SYSMMU_DPU_DMA;
	m->sysmmu_vmid_mask = E1S_PA_SYSMMU_VMID_MASK;
}
