# UI-007 — s5e9945 DECON0/DPP boot-window registers and a read-only reader

Date: 2026-11-10. Evidence category: **source-review + host-test**. Nothing here ran on the phone, and no MMIO was read from Android (MMIO probes from Android are not authorized). The reader is meant for a future native run; it has no hardware result.

Owner history: written by `claude-display-scanout-20261110-u7` (stopped session); transferred under decision 0003 to `claude-takeover-20261110-6c8f`, who reviewed it, fixed one test defect and two validation gaps, and wrote this note and the evidence.

## Sources

- `s24-linux` = dx4m/android-kernel-samsung-e1s @ `417484173abc2c4fa93e738ea82ad9f2e84911b1`. All citations below are against this revision.
- `s24-bsp-reference` @ `f85e53cfa5497ead5d78821efbac84e51f37a4e1`. The cited DPU files are byte-identical except `exynos_drm_debug.c` (+3 lines; `RSC_STATUS_IDLE` is still 7). `tests/test_native_boot_window.py` checks every cited line at both revisions.
- e1s builds `CONFIG_DRM_SAMSUNG_DPU=m` (`arch/arm64/configs/e1s_defconfig:4746`) → `drivers/gpu/drm/samsung/dpu/` (`drivers/gpu/drm/Makefile:107`), and `CONFIG_SOC_S5E9945` selects `cal_rt` (`dpu/Makefile:7-9`). The `dpu_dual/cal_rt` register headers are identical to the `dpu/cal_rt` ones.
- The local checkout is a `blob:none` partial clone. Under `drivers/gpu/drm/samsung`, `drivers/video`, `init` and `arch/arm64/boot/dts/exynos` no blob is missing. The whole tree lacks only three symlink blobs (qcacld-3.0 `cmn`/`api`, Mali `uapi`), so the tree-wide negative search below is complete for source files.

## Cited from source (verbatim in `src/native/display/register_facts.json`)

| What | Where |
|---|---|
| 16 windows per DECON | `cal_rt/regs-decon.h:21` |
| DECON shadow copy at +0x800 (main, WIN, WINCON) | `regs-decon.h:123`; used for WIN/WINCON at `cal_rt/decon_reg.c:2796,2799` |
| `GLOBAL_CON` 0x20: cmd mode bit 8, RUN_STATUS bit 4, DECON_EN bits 1/0 | `regs-decon.h:134-146` |
| `RSC_STATUS_0/1` channel owners, `RSC_STATUS_2/3` window owners, 4-bit field per index, 7 = idle | `regs-decon.h:257,277`; `decon_reg.c:2879-2895`; `exynos_drm_debug.c:49` |
| WIN block shared by all DECONs (descriptor 0), WINCON per DECON | `decon_reg.c:78,89` |
| Window n at n × 0x1000; START/END_POSITION 0xC/0x10, X [13:0], Y [29:16]; END is inclusive (x2−1, y2−1) | `regs-decon.h:633,673-679`; `exynos_drm_decon.c:272-275` |
| `DECON_CON_WIN` 0x0: CHMAP [7:4], MAPCOLOR_EN bit 1, WIN_EN bit 0 | `regs-decon.h:704-708` |
| Channel number = DPP id (`dpp,id` in DT) | `exynos_drm_decon.c:819` |
| Stacking: zpos k = k-th reserved window in ascending index order, so a higher index is stacked above | `exynos_drm_decon.c:709-711` |
| DPU_DMA shadow copy at +0x400 | `cal_rt/regs-dpp.h:72`; dump at `cal_rt/dpp_reg.c:1796` |
| `RDMA_IN_CTRL_0` 0x8: format [13:8], SBWC_LOSSY 14, ROT [6:4], CSET 3, SBWC 2, AFBC/SAJC 1, BLOCK 0 | `regs-dpp.h:96-159` |
| Format codes: ARGB8888 0 … BGRX8888 7, RGB565 8/9, 2101010 16-19, YUV 24-29/56-61, FP16 32-39 | `regs-dpp.h:105-141` |
| `RDMA_SRC_WIDTH/HEIGHT` 0x10/0x14 [23:0] = frame size `f_w/f_h` = `fb->width/height` | `regs-dpp.h:161-167`; `dpp_reg.c:270`; `exynos_drm_dpp.c:368-369` |
| `RDMA_SRC_OFFSET` 0x18 (Y [31:16], X [15:0]); `RDMA_IMG_SIZE` 0x1C (H [31:16], W [15:0]) | `regs-dpp.h:169-179` |
| `DMA_BASEADDR_P0` 0x40 = plane-0 DMA address, written as 32 bits | `regs-dpp.h:201`; `dpp_reg.c:1177`; `exynos_drm_dpp.c:264`; `exynos_drm_fb.c:276` |
| `DMA_SRC_STRIDE_0` 0x50, written only with `DMA_STRIDE_SEL` (bit 31) and a non-zero stride; only SBWC sets one | `regs-dpp.h:206-212`; `dpp_reg.c:1156-1166`; `exynos_drm_dpp.c:279-283` |
| Block region: plane sub-rectangle with `IDMA_BLOCK_EN` + `RDMA_BLOCK_OFFSET/SIZE` | `exynos_drm_dpp.c:432-439`; `dpp_reg.c:293-303` |
| SysMMU v9: per-VM `REG_MMU_CTRL_VM` 0x8000 + vm × 0x1000, `CTRL_MMU_ENABLE` bit 0, written for each VM in `vmid_mask` | `drivers/iommu/samsung/samsung-iommu-v9.h:14,31,40,43`; `samsung-iommu-v9.c:142,238-247` |

### How Linux treats `s3cfb.bootloaderfb`

- No source file at the pinned revision contains `bootloaderfb`. The only `s3cfb` matches are `s3cfb_pm_ops` in the unrelated legacy `drivers/video/fbdev/s3c-fb.c`.
- An unknown dotted boot parameter is accepted and dropped: `init/main.c:592` returns 0 for a `.` in the name.
- Linux's own boot-framebuffer handover uses the DSIM node's `memory-region` phandle and `lk-fb-win-id` instead (`exynos_drm_dsim.c:877,912`). With a handover, Linux keeps that window while disabling the others (`exynos_drm_decon.c:1654`) and releases it at the first plane disable (`exynos_drm_decon.c:871`).
- Inference, not shown in source: a prebuilt vendor module outside the GPL release could still read the parameter.

## Measured on this phone (NAT-005 runtime FDT, normal Android boot)

Blob `devices/e1s-fdt/2026-11-10/runtime.dtb` (private, not in Git), SHA-256 `95fa811abca3f5f8889705add485f94c4490c57a853bded10539d4631bef46c3`. The sanitized facts in `docs/procedures/ui-007/dpu-dt-facts.json` regenerate from it byte for byte.

- **DECON0** `/drmdecon@19100000`: `main` 0x19100000, `win` 0x19110000, `wincon` 0x19130000; `op_mode = 1` (command mode, matching `s5e9945-drm-dpu.dtsi:871`).
- **DPP channels 0-7** DMA at 0x19900000 + n × 0x1000; channels 8-15 at 0x19B00000 + (n−8) × 0x1000. Channels 16 and 17 also exist (0x1990C000 okay, 0x19B0C000 disabled), but `WIN_CHMAP` is 4 bits wide, so no window can map them.
- **SysMMU**: every DPP DMA node with `dpp,id` < 16 points at a single SysMMU, `/sysmmu@19840000`, with `vmid_mask = 3`.
- **No Linux handover**: DSIM0 has neither `memory-region` nor `lk-fb-win-id`.
- **Framebuffer memory**: the bootarg base 0xFA200000 lies in ordinary `/memory@e0100000` and has no reservation (as NAT-005 found).
- **Size correction to NAT-005**: 1080 × 4 B × 2340 = 10 108 800 B = 0x9A3F80. The NAT-005 figure 0x9A4000 is that value rounded up to a 4 KiB page, not the exact product.

## The reader (`src/native/display/e1s_boot_window.{h,c}`)

- **Contract.** Freestanding, `<stdint.h>` only, no libc, no writes. Every access is one aligned volatile 32-bit load from a caller-supplied base; a zero base is never touched. It compiles for `aarch64-none-elf` with the s24-port loader flags and has no undefined symbols.
- **`e1s_boot_window_read`**
  - **Window selection.** Requires each register and its shadow copy to agree. Requires exactly one enabled non-colormap window on DECON0.
  - **Decoding.** Decodes channel, window rectangle, base, format, frame size, crop and stride. Without `DMA_STRIDE_SEL`, the stride is taken as `SRC_WIDTH × bytes/pixel`. That rule follows how Samsung programs the hardware; it is an inference about the hardware.
  - **Refusals.** Compressed, rotated or CSET layouts; non-RGB formats; inconsistent geometry.
  - **Informational flags.** RSC ownership mismatch, block mode, colormap windows and SysMMU translation.
- **`e1s_boot_window_validate`** accepts only all of the following:
  - DECON on;
  - translation known to be off (or explicitly allowed as unknown);
  - ARGB8888 or XRGB8888;
  - unscaled full-panel scanout from (0,0);
  - no active block region;
  - no colormap window above the frame;
  - the expected base, and stride × height inside the expected size.

### Review changes on 2026-11-10

1. **Test defect.** `test_validation_rejections` expected `FB_SIZE − 4` (0x9A3FFC) to be too small. It is not, since the frame needs 0x9A3F80. The test now checks the exact boundary (0x9A3F80 → OK, −4 → SIZE) and asserts that 0x9A3FFC passes.
2. **Validation gap: block mode.** `validate` returned OK with `IDMA_BLOCK_EN` set. Source does not state what the panel shows inside a block region, so it now returns `E1S_BW_ERR_BLOCK` (27). The read itself still succeeds and sets the flag.
3. **Validation gap: colormap window above the frame.** `validate` ignored a solid-colour window stacked above the frame. It now returns `E1S_BW_ERR_COVERED` (28) when an enabled colormap window has a higher index than the DMA window. Lower colormap windows are still allowed.

Mutation check: six single-point mutations of the reader (each new check removed, pitch from crop width, exclusive window end, shadow comparison skipped, wrong CHMAP shift) each fail the suite. This shows the tests are not a mirror of the implementation.

## Not established until a native run

- That DECON0, its DPP channel and the SysMMU are powered and clocked when the loader runs. Reading an unpowered block may hang or raise an SError. The reader cannot detect this beforehand.
- What S-Boot programs when it boots **RECOVERY** rather than BOOT. All FDT facts here are from a normal boot.
- Which window and channel S-Boot uses, whether it is a DMA window at all, and the actual format and stride. Also whether `DMA_BASEADDR_P0` equals 0xFA200000, i.e. whether the SysMMU is in bypass.
- The in-memory byte order behind IDMA code 0 ("ARGB8888"). The reader reports the code and does not infer byte order.
- Whether register and shadow copies agree on an idle command-mode panel. A disagreement makes the reader refuse (`UNSTABLE`), which is safe but would make it unusable.
- Whether the hardware derives the pitch from `SRC_WIDTH` when `DMA_STRIDE_SEL` is clear.

### Proposed native read sequence (not executed)

1. Map DECON0 `main`/`win`/`wincon`, the 16 DPP DMA blocks and the SysMMU block, device-nGnRE, read-only.
2. Call `e1s_boot_window_read`, then `e1s_boot_window_validate` with the bootarg base, the RAM-window bound and 1080 × 2340.
3. Use the framebuffer for console output only on `E1S_BW_OK`. Otherwise log the raw status, `global_con` and `in_ctrl` and do not draw.
