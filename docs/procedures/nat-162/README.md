# NAT-162: display-hardware scaling of the iOS surface (source review)

- **Evidence kind:** source review. No device was used.
- **Source:** `references/s24-linux` 417484173abc2c4fa93e738ea82ad9f2e84911b1, the Samsung e1s kernel. Read with `git show HEAD:path`,
  because the working copy is sparse.
- **Prepared by:** a research subagent.
- **Re-checked in this session:** the `cal_rt` selection, the DPP1 attributes and scale limits, the ratio formula, and the DECON
  `TRIG_CON`/`SHD_REG_UP_REQ`/`DECON_INT_EN` offsets.

Short paths below:
- `dts` = `arch/arm64/boot/dts/exynos/s5e9945-drm-dpu.dtsi`;
- `rt/` = `drivers/gpu/drm/samsung/dpu/cal_rt/`;
- `dpp.c` / `decon.c` = `drivers/gpu/drm/samsung/dpu/exynos_drm_{dpp,decon}.c`.

**S** marks what the source states. **I** marks inference.

## Why

NAT-159 measured the CPU copy at 26 ms per frame with `fb_filter=0` (70.7 ms bilinear). The display controller can do that scaling
itself if its layer (DPP) scans the iOS surface directly. Then the copy goes away entirely, and the frame needs no CPU pass at all.

## Findings

1. **The build uses `cal_rt` (S).**
   - `dpu/Makefile:7-8`: `ifdef CONFIG_SOC_S5E9945` → `cal-dir := cal_rt`.
   - `arch/arm64/configs/e1s_defconfig:6638`: `CONFIG_SOC_S5E9945=y`, with EVT0 unset.
2. **Scaling channels.**
   - **S:** only the odd layers L1, L3, … L15 carry `DPP_ATTR_SCALE`, with `scale_down=<4>` and `scale_up=<8>` (dts:110-117 for L1,
     `dpp,id=<1>`, dts:119).
   - **S:** the even layers have no scaler.
   - **S:** a DECON window's `CHMAP` holds the DPP id (decon.c:819).
   - **I, with NAT-070:** win3 has CHMAP 1, so S-Boot already drives win3 through DPP1, which has a scaler. win2 (CHMAP 0) goes
     through DPP0, which has none.
3. **Corrections to NAT-070's reading of the registers (S).**
   - The RDMA word 0x40000000 is `IDMA_ASSIGNED_MO(0x40)` (rt/regs-dpp.h:75), not an enable bit.
   - On this chip `TRIG_CON` = 0x30, `SHD_REG_UP_REQ` = 0x50, `DECON_INT_EN` = 0x60 and `DATA_PATH_CON` = 0x200/0x204
     (rt/regs-decon.h:148, 206, 215, 348/370). The S9-style offsets in the NAT-070 README do not apply.
4. **Stock sequence for one scaled layer (S, `dpp_reg_configure_params`, rt/dpp_reg.c:1558-1628).** Bases for L1: DMA 0x19901000,
   DPP 0x19931000, SRAMC 0x19951000, SCL_COEF 0x19940000 (dts:93-99).
   1. **SRAMC:** `+0x14` destination position; `+0x10` mode with `SCL_EN` bit 12.
   2. **Scaler:** `DPP+0x80 SCL_CTRL` (bit 0 enable; coefficient set `(id%8)/2`). `+0x88/+0x8C` H/V ratio = `(src<<20)/dst`
      (dpp.c:346-347): 1125→1080 gives 0x10AAAA, and 2436→2340 gives 0x10A80A.
   3. **Coefficients:** 9 phases × 8 taps horizontal and 9 × 4 vertical, 11-bit, from `exynos_dpp_coef.h` (rt/dpp_reg.c:826-886).
      The ratio 1.04 selects table 1 (rt/dpp_reg.c:33-34).
   4. **Sizes:**
      - DMA `+0x10` `SRC_WIDTH` (pitch in pixels) and `+0x14` `SRC_HEIGHT`;
      - `+0x18` offset;
      - `+0x1C` `IMG_SIZE` 2436<<16 | 1125;
      - DPP `+0x3C` source size;
      - `+0x84` scaled size 2340<<16 | 1080.
   5. **Address:** DMA `+0x40 BASEADDR_P0`. Linear buffers write no stride register.
   6. **Format:** DMA `+0x08` bits 13:8. iOS BGRA in memory is DRM ARGB8888, IDMA code 0; XRGB code 4 avoids alpha.
   7. **DECON window and commit, command mode:**
      - wait for `SHD_REG_UP_REQ` 0x19100050 = 0;
      - mask the trigger (`TRIG_CON` 0x19100030 bit 4);
      - write;
      - `SHD_REG_UP_REQ |= 0xFFFF`, then bit 31;
      - unmask; the panel's TE then starts the frame and latches the shadows (decon.c:1013/1199/1205/1390,
        rt/decon_reg.c:2342-2361, 2476-2556).
5. **Limits (S, dpp.c:583-593).**
   - Ratios must lie between 1/8 and 4 in 20-bit fixed point; 0.96 in both directions is well inside.
   - Width at least 16 and at most 4096 (dts:1157-1171).
6. **Memory.**
   - **S:** every DPP/DECON node has `iommus = <&sysmmu_dpuf_s0>` (dts:56, 105). That SysMMU is at 0x19840000 in `pd_dpuf1`.
   - **S:** there is no framebuffer-handover memory region in the tree.
   - **I:** S-Boot's `BASEADDR_P0 = 0xfa200000` is physical, so the SysMMU is bypassed or identity-mapped. Reading `CTRL` would
     confirm it.
   - **I, if bypassed:** the source must be physically contiguous: 1125 × 2436 × 4 = 10,962,000 B per buffer. MiniIOMobileFramebuffer
     already allocates the recording with `kIOMemoryPhysicallyContiguous`, so contiguous surfaces are a driver change, not new
     hardware work.

## Risks (S/I)

- **Power domains.** Touching a block whose power domain is off can hang the bus. NAT-070 read only DMA, DECON, DSIM and PHY. Nobody
  has read DPP (0x1993xxxx), SCL_COEF (0x1994xxxx), SRAMC (0x1995xxxx) or the SysMMU (0x1984xxxx) yet.
- **SysMMU faults.** In stall mode a fault can freeze the DMA.
- **Configuration errors.** They show as `CFG_ERR` (DPP+0x1C) and a black frame, or a shadow update that never completes.

## The native step before any write: a read-only snapshot, kept for exact write-back

| Block | What to read |
| --- | --- |
| DECON | `TRIG_CON` 0x19100030, `SHD_REG_UP_REQ` 0x19100050, `FRAME_COUNT` 0x19100004 (twice), `DATA_PATH_CON` 0x19100200 |
| Windows 2/3 | WIN +0x0..0x1C and the shadow at +0x800; WINCON 0x19132000/0x19133000 |
| DMA L0/L1 | +0x08..0x1C, 0x40, 0x50, 0x200, 0x338, 0x740, and the shadow at +0x400 |
| DPP L0/L1 | +0x0 (expected 0x07030000), 0x1C, 0x30, 0x34, 0x38, 0x3C, 0x80..0x98 |
| SRAMC L1 | +0x10/+0x14 |
| SysMMU 0x19840000 | +0x0, +0x8, +0x34, +0x8000, +0x8404 |

Read these only after the power domain of each block is shown to be on: DPUF0/DPUF1 status, from the stock power-domain sources.
That check is the first open question. The second is whether S-Boot's win2 or win3 is the visible one. NAT-070 found both pointing
at 0xfa200000.

## Not established

- No register in the table was read on this phone.
- The base-address alignment rule: `CONFIG_ERR_STATUS` bit 6 exists, but its rule is not in the source.
- DECON's own scaler path (`DATA_PATH_CON` bit 24) was not reviewed.
