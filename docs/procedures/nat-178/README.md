# NAT-178: stock register sequence for one scaled linear RGB layer on DMA1/DPP1 (source review)

- **Evidence kind:** source review. No device, adb or phone access was used.
- **Source:** `references/s24-linux` 417484173abc2c4fa93e738ea82ad9f2e84911b1 (Samsung e1s kernel), read with `git show HEAD:path`.
- **Device inputs (not re-measured):** NAT-177 snapshot, `artifacts/nat-177/analysis/dpp-lines.txt` (123.09 s and 300.34 s, identical except FRAME_COUNT).
- **Marks:** **S** = stated by the source at the cited line; **I** = inference by this review.

Short paths:
- `rt/` = `drivers/gpu/drm/samsung/dpu/cal_rt/`; `cm/` = `drivers/gpu/drm/samsung/dpu/cal_common/`;
- `dpu/` = `drivers/gpu/drm/samsung/dpu/`; `dts` = `arch/arm64/boot/dts/exynos/s5e9945-drm-dpu.dtsi`.

## 0. Build selection and bases

| Fact | Mark | Citation |
|---|---|---|
| `CONFIG_SOC_S5E9945=y` selects `cal_rt`; HDR code is `dpu/exynos_drm_hdr.c` (`CONFIG_DRM_MCD_HDR` unset) | S | `dpu/Makefile:7-8,35-39,72-73`; `arch/arm64/configs/e1s_defconfig:4764,4784,6638` |
| L1 (`dpp,id=1`, DPUF0) bases: DMA 0x19901000, DPP 0x19931000, SRAMC 0x19951000, vOTF 0x19920000, **SCL_COEF 0x19940000 (size 0x4000, shared by all DPUF0 layers)**, HDR_COMM 0x19961000, HDR_CUSTOM 0x19971000 | S | dts:93-100, 119-120 |
| L1 attrs: SAJC, FLIP, ROT, CSC, SCALE, SBWC, IDMA, DPP, SRAMC, HDR_COMM, WCG, HDR, HDR10_PLUS; no BLOCK, no RCD, no ODMA; `scale_down=4`, `scale_up=8` | S | dts:110-117 |
| DECON0: MAIN 0x19100000, WIN 0x19110000, WINCON 0x19130000, SRAMC0_D0 0x19958000; `op_mode=1` (command), `trig_mode=0` (HW trigger), `te_from=0` | S | dts:820-831, 871-876 |
| Per-window offset `0x1000*win` in WIN and WINCON; window shadow at +0x800 | S | `rt/regs-decon.h:123,633,704`; `rt/decon_reg.c:2788-2800` |
| Shadow copies: DMA +0x400, DPP +0x100, SRAMC +0x800, HDR_COMM +0x800, SCL_COEF +0x200 (per coef set) | S | `rt/regs-dpp.h:72,1073,1319,1404,1264`; `rt/dpp_reg.c:1757-1760,1796-1840` |
| `cal_write` is a 32-bit `writel`; `cal_write_mask` is read-modify-write `(val & mask) | (old & ~mask)` | S | `cm/cal_config.h:113-141` |

## 1. Our case as stock would compute it

| Parameter | Value | Mark | Citation |
|---|---|---|---|
| `src` = (0,0,1125,2436), `src.f_w/f_h` = fb width/height = 1125/2436 (pixels, not pitch) | — | S | `dpu/exynos_drm_dpp.c:364-369` |
| `dst` = (0,0,1080,2340) | — | S | `dpu/exynos_drm_dpp.c:371-376` |
| `h_ratio = (src_w<<20)/dst_w` = (1125<<20)/1080 | **0x0010AAAA** (1092266) | S formula, I arithmetic | `dpu/exynos_drm_dpp.c:346` |
| `v_ratio = (src_h<<20)/dst_h` = (2436<<20)/2340 | **0x0010A80A** (1091594) | S formula, I arithmetic | `dpu/exynos_drm_dpp.c:347` |
| `is_scale` = true (a ratio != 1<<20) | — | S | `dpu/exynos_drm_dpp.c:349-350` |
| Limits pass: ratio <= 4.0 and >= 1/8; src_w 16..4096, src_h 8..4320, align 1 | — | S | `dpu/exynos_drm_dpp.c:583-594`; dts:1156-1183 |
| DRM ARGB8888: `dma_fmt` 0, `dpp_fmt` 0, bpc 8, `len_alpha` 8, RGB | — | S | `dpu/exynos_drm_format.c:46-56` |
| Linear (no modifier): `comp_type` NONE, `addr[0]` = buffer, `addr[1]` = fb obj[1] (0 when absent), **no stride set** | — | S | `dpu/exynos_drm_dpp.c:261-266`; `dpu/exynos_drm_fb.c:264-276` |
| `in_bpc` = DPP_BPC_8 (0) unless crtc in_bpc >= 10 | — | S | `dpu/exynos_drm_dpp.c:749`; `cm/dpp_cal.h:149-151` |
| `rcv_num` = DISP devfreq aclk in kHz | depends on clock | S | `dpu/exynos_drm_dpp.c:202-222,407` |
| `hdr_en` = 0, no `hdr_ctx` → `exynos_hdr_update` writes nothing | — | S | `dpu/exynos_drm_dpp.c:413,758`; `dpu/exynos_drm_hdr.c:458-471,813-826` |
| Coef set for DPP1: `coef_id = (id % 8)/2` = **0** → base 0x19940000 + `SCL_COEF_OFFS(0)` = 0x19940000 | — | S | `rt/dpp_reg.c:890`; `rt/regs-dpp.h:1267` |
| Coef table index: ratio <= `DPP_SC_RATIO_MAX` (1<<20) → 0; <= `DPP_SC_RATIO_7_8` ((1<<20)*8/7 = 1198372) → **1** | **1** for both H and V | S thresholds, I arithmetic | `rt/dpp_reg.c:33-34,830-833,861-864` |

Note (S): the range comments in `cm/exynos_dpp_coef.h:17,35` use a 16-bit scale (65536 = 1.0); the selection code uses the 20-bit
thresholds in `rt/dpp_reg.c:33-38`. Both put a ratio in (1.0, 8/7] into table 1.

## 2. Ordered write list (one commit, stock order)

Stock commit order (S): `decon_atomic_begin` (`dpu/exynos_drm_decon.c:987-1039`) → `decon_update_plane` (window regs, then
`dpp_update`) (`dpu/exynos_drm_decon.c:755-852`; `dpu/exynos_drm_dpp.c:733-763`) → `decon_atomic_flush`
(`dpu/exynos_drm_decon.c:1199-1205`) → `wait_framestart` → `set_trigger` (`dpu/exynos_drm_drv.c:1634-1638`).

"RMW" = `cal_write_mask` with the given mask. All values are for the case in section 1. Column "NAT-177" is the current value.

### 2a. DECON begin (per commit)

| # | Address | Register | Access | Value / mask | NAT-177 | Citation |
|---|---|---|---|---|---|---|
| A1 | 0x19100050 | SHD_REG_UP_REQ | poll | until == 0, 10 µs step, 300 ms timeout | 0 | S `rt/decon_reg.c:2539-2556`; `dpu/exynos_drm_decon.c:89,1013` |
| A2 | 0x19100030 | TRIG_CON | RMW | mask 0x11, val 0x11 (HW_TRIG_EN + HW_TRIG_MASK_DECON) → **0x3073** | 0x3063 | S `rt/decon_reg.c:2513-2520,2558-2569` |
| A3 | 0x19100020 | GLOBAL_CON | RMW | mask bit 20 (TEN_BPC), val 0 for 8 bpc | not read | S `rt/decon_reg.c:904-914,2453-2464`; `rt/regs-decon.h:136` |

### 2b. DECON window 3 (per commit in stock; values unchanged for our case)

Stock rewrites the window every commit (S `rt/decon_reg.c:2485-2499`). With the window still full panel, every value equals the
NAT-177 readback, so writing them is optional (I).

| Address | Register | Value (= NAT-177) | Citation |
|---|---|---|---|
| 0x19113004 | WIN_FUNC_CON_0: ALPHA0 [23:16], FUNC [11:8], ALPHA_MULT_SRC_SEL [1:0] | 0x00ff0d02 (alpha0 0xff, PD_FUNC_USER_DEFINED 0xd, SEL_AF 2) | S `rt/regs-decon.h:649-661`; `cm/decon_cal.h:167`; `rt/decon_reg.c:55-58,2077-2147` |
| 0x19113008 | WIN_FUNC_CON_1 | 0x0a0b0a0b (ALPHA_MULT / 1-ALPHA_MULT = coverage blend) | S `rt/regs-decon.h:663-671`; `rt/decon_reg.c:39-52,2169-2173` |
| 0x1911300C / 0x19113010 | WIN_START/END_POSITION | 0 / 0x09230437 ((1079,2339)) | S `rt/regs-decon.h:673-679`; `dpu/exynos_drm_decon.c:267-275` |
| 0x19113014 / 0x19113018 / 0x1911301C | COLORMAP_0/1, START_TIME_CON | 0 / 0 / 0 | S `rt/regs-decon.h:681-698`; `dpu/exynos_drm_decon.c:813-817` |
| 0x19133000 | WINCON3: CHMAP [7:4] = DPP id, MAPCOLOR_EN bit 1, EN bit 0 | 0x11 | S `rt/regs-decon.h:704-708`; `dpu/exynos_drm_decon.c:819`; `rt/decon_reg.c:916-923,2033-2042` |

### 2c. `dpp_reg_configure_params(1, …)` (per commit), `rt/dpp_reg.c:1558-1628`

| # | Address | Register (block+off) | Access | Value for our case | NAT-177 | Mark, citation |
|---|---|---|---|---|---|---|
| C1 | 0x19951014 | SRAMC1 DST_POSITION: BOTTOM [29:16], TOP [13:0] | W | **0x09230000** (top 0, bottom 2339) | 0 | S `rt/dpp_reg.c:141-145,155`; `rt/regs-dpp.h:1349-1353` |
| C2 | 0x19951010 | SRAMC1 MODE: SCL_ALPHA_EN b13, SCL_EN b12, COMP b8, ROT b4, FORMAT [1:0] (RGB32 = 0) | W | **0x00003000** | 0 | S `rt/dpp_reg.c:157-188`; `rt/regs-dpp.h:1332-1346` |
| — | — | CSC | skip | RGB format: not called | — | S `rt/dpp_reg.c:1571-1572` |
| C3 | 0x19931080 | DPP1 SCL_CTRL: ENABLE b0 | RMW | mask 0x1, val 1 | 0 | S `rt/dpp_reg.c:892-893`; `rt/regs-dpp.h:1211-1215` |
| C4 | 0x19931080 | DPP1 SCL_CTRL: COEF_SEL [5:4] | RMW | mask 0x30, val 0 → reg **0x00000001** | 0 | S `rt/dpp_reg.c:895-897` |
| C5 | 0x19931088 | DPP1 SCL_MAIN_H_RATIO [22:0] | RMW | **0x0010AAAA** | 0x100000 | S `rt/dpp_reg.c:898-899`; `rt/regs-dpp.h:1223-1225` |
| C6 | 0x1993108C | DPP1 SCL_MAIN_V_RATIO [22:0] | RMW | **0x0010A80A** | 0x100000 | S `rt/dpp_reg.c:900-901`; `rt/regs-dpp.h:1227-1229` |
| C7 | 0x19940090… | H coefficients, 72 writes | W | section 3 | not read | S `rt/dpp_reg.c:845-854` |
| C8 | 0x19940000… | V coefficients, 36 writes | W | section 3 | not read | S `rt/dpp_reg.c:876-885` |
| C9 | 0x19901018 | DMA1 SRC_OFFSET: Y [31:16], X [15:0] | W | 0 | 0 | S `rt/dpp_reg.c:268-269`; `rt/regs-dpp.h:169-173` |
| C10 | 0x19901010 | DMA1 SRC_WIDTH [23:0] (frame width, pixels) | W | **0x465** (1125) | 0x438 | S `rt/dpp_reg.c:270`; `rt/regs-dpp.h:161-163` |
| C11 | 0x19901014 | DMA1 SRC_HEIGHT [23:0] | W | **0x984** (2436) | 0x924 | S `rt/dpp_reg.c:271` |
| C12 | 0x1990101C | DMA1 IMG_SIZE: H [31:16], W [15:0] | W | **0x09840465** | 0x09240438 | S `rt/dpp_reg.c:272-273`; `rt/regs-dpp.h:175-179` |
| C13 | 0x19931064 | DPP1 SUB_CON2: X_ODD b16, Y_ODD [2:0] (crop x/y parity) | RMW | mask 0x10007, val 0 | not read | S `rt/dpp_reg.c:664-671,1196`; `rt/regs-dpp.h:1203-1207` |
| C14 | 0x19961020 | HDR_COMM1 SIZE: V [28:16], H [12:0] = **dst** size | W | 0x09240438 (same as unscaled) | not read | S `rt/dpp_reg.c:1082-1086,1197`; `rt/regs-dpp.h:1453-1457` |
| C15 | 0x1993103C | DPP1 IMG_SIZE: H [29:16], W [13:0] = **src** size (no rotation) | W | **0x09840465** | 0x09240438 | S `rt/dpp_reg.c:975-978,1198-1201`; `rt/regs-dpp.h:1147-1151` |
| C16 | 0x19931090 | DPP1 SCL_HPOSITION (initial phase, S11.20) | RMW (full mask) | 0 | 0 | S `rt/dpp_reg.c:917-918`; `rt/regs-dpp.h:1231-1245` |
| C17 | 0x19931094 | DPP1 SCL_VPOSITION | RMW (full mask) | 0 | 0 | S `rt/dpp_reg.c:919-920`; split NONE skips the rest `:922` |
| C18 | 0x19931084 | DPP1 SCL_SCALED_IMG_SIZE: H [28:16], W [12:0] | W | **0x09240438** | 0 | S `rt/dpp_reg.c:980-984,1204-1207`; `rt/regs-dpp.h:1217-1221` |
| C19 | 0x19901008 | DMA1 IN_CTRL_0: ROT [6:4] | RMW | mask 0x70, val 0 | 0 | S `rt/dpp_reg.c:288-291,1580-1581`; `rt/regs-dpp.h:143-144` |
| C20 | 0x19901040 | DMA1 BASEADDR_P0 | W (32-bit) | **buffer PA** | 0xfa200000 | S `rt/dpp_reg.c:1177`; `rt/regs-dpp.h:201` |
| C21 | 0x19901044 | DMA1 BASEADDR_P1 | W | 0 | not read | S `rt/dpp_reg.c:1178`; `dpu/exynos_drm_fb.c:268-269` |
| C22–C25 | 0x19901050/54/58/5C | DMA1 SRC_STRIDE_0..3 (`STRIDE_SEL` b31) | W | 0, 0, 0, 0 | +0x50 = 0, others not read | S `rt/dpp_reg.c:1156-1166`; `rt/regs-dpp.h:206-213` |
| — | — | block mode | skip | no BLOCK attr on L1 | — | S `rt/dpp_reg.c:1591-1593`; dts:110-114 |
| C26 | 0x19901008 | DMA1 IN_CTRL_0: IMG_FORMAT [13:8] | RMW | mask 0x3f00, val 0 (ARGB8888) | 0 | S `rt/dpp_reg.c:308-312,1222`; `rt/regs-dpp.h:102-105` |
| C27 | 0x1996105C | HDR_COMM1 HDR_BYPASS b0 | W | 1 | not read | S `rt/dpp_reg.c:1144-1147,1230`; `rt/regs-dpp.h:1494-1496` |
| C28 | 0x19961014 | HDR_COMM1 DITH_CON: DITH_EN [5:4] | RMW | mask 0x30, val 0 | not read | S `rt/dpp_reg.c:1047-1051,1231` |
| C29 | 0x19931038 | DPP1 IO_CON: BPC_MODE b6 | RMW | mask 0x40, val 0 | 0x80 | S `rt/dpp_reg.c:1007-1011,1232` |
| C30 | 0x1996100C | HDR_COMM1 IO_CON: BPC_MODE b6 | RMW | mask 0x40, val 0 | not read | S `rt/dpp_reg.c:1026-1030,1233` |
| C31 | 0x19931038 | DPP1 IO_CON: BEXT_MODE b8 (1 = zero padding) | RMW | mask 0x100, val 0x100 | 0x80 | S `rt/dpp_reg.c:991-994,1235`; `rt/regs-dpp.h:1128-1131` |
| C32 | 0x19931038 | DPP1 IO_CON: ALPHA_SEL b7 (1 = per pixel) | RMW | mask 0x80, val 0x80 | 0x80 | S `rt/dpp_reg.c:996-999,1219,1236`; `rt/regs-dpp.h:1132-1135` |
| C33 | 0x19931038 | DPP1 IO_CON: IMG_FORMAT [2:0] | RMW | mask 0x7, val 0 → reg **0x00000180** | 0x80 | S `rt/dpp_reg.c:1001-1005,1237` |
| C34 | 0x1996100C | HDR_COMM1 IO_CON: IMG_FORMAT [2:0] | RMW | mask 0x7, val 0 | not read | S `rt/dpp_reg.c:1032-1036,1238` |
| C35 | 0x19901008 | DMA1 IN_CTRL_0: SBWC_EN b2, SAJC_EN b1, SBWC_LOSSY b14 | RMW | mask 0x4006, val 0 → reg stays 0xff400000 | 0xff400000 | S `rt/dpp_reg.c:349-370,1598-1599` |
| C36 | 0x19901070 | DMA1 RECOVERY_CTRL: EN b0 | RMW | mask 0x1, val 0 | not read | S `rt/dpp_reg.c:372`; `rt/regs-dpp.h:256-259` |
| C37 | 0x19901100 | DMA1 DEADLOCK_CTRL: NUM_EN b0 | RMW | mask 0x1, val 1 | not read | S `rt/dpp_reg.c:375-382,1606` |
| C38 | 0x19901100 | DMA1 DEADLOCK_CTRL: NUM [31:1] | RMW | mask 0xfffffffe, val `(aclk_kHz*51) << 1` | not read | S `rt/dpp_reg.c:380-381,1601-1606`; `rt/regs-dpp.h:261-264` |
| C39 | 0x19901180 | DMA1 VOTF_EN [1:0] | RMW | mask 0x3, val 0 (vOTF off) | not read | S `rt/dpp_reg.c:1612,1697-1700`; `rt/regs-dpp.h:313-320` |

Notes:
- **I:** for C38 stock uses 51 ms worth of DISP aclk cycles (comment `rt/dpp_reg.c:1601-1605`). The clock in our kernel is not
  known from this review, so the safe choice is to read 0x19901100 first and keep the S-Boot value.
- **I:** C1, C14, C16, C17, C19, C21–C30, C34–C36, C39 equal what stock writes for the unscaled case too. Only C2–C8, C10–C12,
  C15, C18, C20 and C31 (BEXT bit 8: S-Boot left 0x80, stock writes 0x180) differ from an unscaled stock commit.
- **S:** stock writes no register for pitch on a linear buffer; `SRC_WIDTH` is `fb->width` (`dpu/exynos_drm_dpp.c:368`). **I:** the
  DMA derives the line pitch from `SRC_WIDTH` × 4 B, so 1125 px gives exactly the required 4500 B stride.
- **S:** stock never writes RDMA BUS_CTRL (+0x110), LLC_CTRL (+0x114), PERF_CTRL (+0x120), MST/SLV_SECURITY (+0x200/+0x204) or
  `IDMA_SFR_UPDATE_FORCE` (RDMA_ENABLE b4) for an IDMA layer (grep of `rt/dpp_reg.c` and `dpu/*.c`; the force bit is used only for
  RCD, `rt/dpp_reg.c:1422`). NAT-177 read +0x200 = 1; leave it.

### 2d. Init-time writes (`dpp_reg_init`, once when the DPP goes from OFF to ON), `rt/dpp_reg.c:1434-1491`

Called from `__dpp_enable` only if `dpp->state != DPP_STATE_ON` (S `dpu/exynos_drm_dpp.c:446-452`). S-Boot already runs DPP1 with
IN_CTRL 0xff400000 = ALPHA 0xff + IC_MAX 0x40 (`rt/regs-dpp.h:96-100`), which equals the init values, so **I:** do not re-run init;
read the rest and compare.

| Address | Register | Stock init value | NAT-177 | Citation |
|---|---|---|---|---|
| 0x1995100C | SRAMC1 PSLVERR_CON b0 | 1 | not read | `rt/dpp_reg.c:127-134,1440` |
| 0x19951010 | SRAMC1 MODE | 0 | 0 | `rt/dpp_reg.c:1441` |
| 0x19901338 → 0x19901000 | if IRQ_STATUS b2 (DEADLOCK): RDMA_ENABLE b8 SRESET, poll clear (2 ms) | conditional | 0x338 = 0 | `rt/dpp_reg.c:1445-1448,240-264` |
| 0x19901334 | IRQ_MASK [20:0] | 0 (all unmasked) | not read | `rt/dpp_reg.c:193-198,1449` |
| 0x19901330 | IRQ_CTRL b0 | 1 | not read | `rt/dpp_reg.c:200-203,1450` |
| 0x19901130 / 0x19901134 | QOS_LUT_LOW / HIGH | 0x44444444 / 0x44444444 | not read | `rt/dpp_reg.c:210-219,1451-1452` |
| 0x19901140 | DYNAMIC_GATING_EN: b31 SRAM_CG, [30:0] | 0 / 0 | not read | `rt/dpp_reg.c:221-233,1454-1455` |
| 0x19901008 | IN_CTRL_0 ALPHA [31:24], IC_MAX [23:16] | 0xff, 0x40 | 0xff, 0x40 | `rt/dpp_reg.c:276-286,1456-1457` |
| 0x19901000 | RDMA_ENABLE ASSIGNED_MO [31:24] | 0x40 | not read here (NAT-070: 0x40000000) | `rt/dpp_reg.c:245-249,1458` |
| 0x1990130C | PSLV_ERR_CTRL b0 | 1 | not read | `rt/dpp_reg.c:340-347,1459` |
| **0x1990100C** | `dpp_reg_set_pslave_err` writes `DPP_COM_PSLVERR_CON` (0x0C) **through the DMA accessor**, i.e. DMA1+0x0C b0, not DPP1+0x0C | 1 | DMA1 +0x0C = 0 | S `rt/dpp_reg.c:646-653,1464` (stock bug, I) |
| 0x19961000 | HDR_COMM1 LC_CON: MODE b1 = 0, EN b0 = 1 | 0x1 | not read | `rt/dpp_reg.c:1015-1024,1468` |
| 0x19961018 | HDR_COMM1 PSLVERR_CON | 1 | not read | `rt/dpp_reg.c:1067-1073,1469` |
| 0x1996105C | HDR_COMM1 HDR_BYPASS | 0 at init (HDR10_PLUS attr), then 1 per frame (C27) | not read | `rt/dpp_reg.c:1471-1474,1230` |

`dpp_reg_set_linecnt` is a no-op for id 1 (S `rt/dpp_reg.c:611-614`).

### 2e. DECON flush and completion (per commit)

| # | Address | Access | Value | Citation |
|---|---|---|---|---|
| D1 | 0x19100050 SHD_REG_UP_REQ | RMW | set [15:0] = 0xFFFF (all windows) | S `rt/decon_reg.c:2476-2483`; `rt/regs-decon.h:212-213`; `dpu/exynos_drm_decon.c:1199` |
| D2 | 0x19100020 GLOBAL_CON | RMW | set b1 DECON_EN, b0 DECON_EN_F | S `rt/decon_reg.c:283-290,2350`; `rt/regs-decon.h:145-146` |
| D3 | 0x19100050 SHD_REG_UP_REQ | RMW | set b31 GLOBAL **and b20 CMP**; DQE b28/b30 only if DATA_PATH_CON[14:12] != 0 | S `rt/decon_reg.c:1873-1896`; `rt/regs-decon.h:206-211,355-361` |
| D4 | 0x19100020 GLOBAL_CON | poll | until b4 RUN_STATUS = 1, 10 µs step, 2 ms timeout | S `rt/decon_reg.c:297-312,2353-2357` |
| D5 | 0x19100030 TRIG_CON | RMW | mask 0x11, val 0x1 → **0x3063** (unmask) | S `rt/decon_reg.c:2359-2361,2513-2520` |
| D6 | 0x19100070 DECON_INT_PEND | poll, W1C | b12 FRAME_START (stock waits ≤ 5 frames for it); clear by writing 0x1000 | S `dpu/exynos_drm_decon.c:1299-1335,1965-1967`; `rt/decon_reg.c:2717-2721`; `rt/regs-decon.h:232-237` |
| D7 | 0x19100050 SHD_REG_UP_REQ | poll | until == 0 (300 ms) — this is the "update done" stock checks | S `dpu/exynos_drm_decon.c:1351,1374`; `rt/decon_reg.c:2539-2556` |
| D8 | 0x19100030 TRIG_CON | RMW | stock masks again → 0x3073 | S `dpu/exynos_drm_decon.c:1386-1391` |

- **S:** NAT-177's DATA_PATH_CON 0xb1 is `DPATH_DSCC_DSCENC01_OUTFIFO01_DSIMIF0` (`cm/decon_cal.h:56`); bits [7:4] are
  `COMP_DSC_MASK` (`rt/decon_reg.c:623-625`), so stock adds b20 in D3; ENHANCE_PATH [14:12] = 0, so no DQE bits. D3 therefore sets
  **0x80100000**; after D1 the register is 0x8010FFFF until hardware clears it (I).
- **S:** "For command mode, TE unmask is added later, so Global SHD Update … occurs … by TE" (`rt/decon_reg.c:1882-1884`); "DECON goes
  to run-status as soon as request shadow update without HW_TE" (`rt/decon_reg.c:2353-2356`).
- **I:** S-Boot leaves the trigger unmasked (TRIG_CON 0x3063), and FRAME_COUNT advances at 120 Hz. Stock masks after each frame and
  only refreshes on commit. To keep NAT-177 behaviour (continuous TE-driven refresh from memory), skip D8 and leave 0x3063.

TRIG_CON bits (S `rt/regs-decon.h:148-167`) for 0x3063: b13 HW_TRIG_ACTIVE_VALUE, b12 HW_TRIG_EDGE_POLARITY, b6 HW_TRIG_MASK_SLAVE1,
b5 HW_TRIG_MASK_SLAVE0, b1 SW_TRIG_DET_EN, b0 HW_TRIG_EN; b4 HW_TRIG_MASK_DECON = 0 (unmasked); [25:24] HW_TRIG_SEL = 0 (DDI0);
b8 SW_TRIG_EN = 0. Stock init sets EN, SEL and MASK_DECON only (`rt/decon_reg.c:979-1000`); the other bits came from S-Boot (I).

SHD_REG_UP_REQ bits (S `rt/regs-decon.h:206-213`): b31 GLOBAL, b30 DQE_CGC, b29 DQE_ROI, b28 DQE, b20 CMP, b(n) window n.

**Window registers:** they do not need to change when only the source becomes scaled; the window stays (0,0)–(1079,2339) and CHMAP 1
(I, from section 2b). DPP1 already carries the scaler (dts:110-117). **S:** the source does not say which SHD_REG_UP_REQ bit latches
the DMA/DPP/SRAMC/SCL_COEF shadows; stock always requests 0xFFFF + GLOBAL, so do the same.

## 3. Scaler coefficients (table 1, 9 phases)

- **S:** `h_coef_8t[7][16][8]` and `v_coef_4t[7][16][4]` are `s16` (`cm/exynos_dpp_coef.h:16,146`); stock uses only phases 0..8
  (`rt/dpp_reg.c:845-846,876-877`). Table 1 rows used: H `cm/exynos_dpp_coef.h:36-44`, V `cm/exynos_dpp_coef.h:166-174`.
- **S:** addresses `DPP_H_COEF(cid,n,s) = SCL_COEF_OFFS(cid) + 0x90 + n*4 + s*0x24`, `DPP_V_COEF(cid,n,s) = SCL_COEF_OFFS(cid) +
  n*4 + s*0x24` with n = phase i, s = tap j (`rt/regs-dpp.h:1266-1276`). Loop order: phase outer, tap inner (`rt/dpp_reg.c:845-854,
  876-885`). Field `DPP_SCL_COEF_MASK` = 0x7FF (11 bits, `rt/regs-dpp.h:1271-1272`).
- **S:** the value goes through `coef_write` → `cal_write(u32)`, so a negative `s16` is written sign-extended (e.g. -32 → 0xFFFFFFE0)
  (`rt/dpp_reg.c:91-92,851-852`; `cm/cal_config.h:113-117`). **I:** hardware keeps [10:0]; write the sign-extended word to match stock.
- **S:** written every commit when scaling (`rt/dpp_reg.c:903-904`); sfr-DMA path only if SFR DMA is enabled, otherwise direct
  `cal_write` (`rt/dpp_reg.c:115-117,847-852`). Each row sums to 512 (I, arithmetic).
- Shadow copy at +0x200 (0x19940200..0x199403AC) (S `rt/regs-dpp.h:1264`; `rt/dpp_reg.c:1757-1760`).

H table 1 (phase i × tap j):

| i | j0 | j1 | j2 | j3 | j4 | j5 | j6 | j7 |
|---|---|---|---|---|---|---|---|---|
| 0 | 12 | -32 | 56 | 444 | 52 | -32 | 12 | 0 |
| 1 | 9 | -24 | 29 | 445 | 82 | -39 | 13 | -3 |
| 2 | 7 | -16 | 6 | 438 | 112 | -46 | 14 | -3 |
| 3 | 5 | -9 | -14 | 426 | 144 | -52 | 15 | -3 |
| 4 | 3 | -3 | -30 | 410 | 177 | -58 | 16 | -3 |
| 5 | 2 | 2 | -43 | 390 | 211 | -63 | 16 | -3 |
| 6 | 1 | 7 | -53 | 365 | 244 | -66 | 16 | -2 |
| 7 | 0 | 10 | -60 | 338 | 277 | -66 | 15 | -2 |
| 8 | -1 | 13 | -65 | 309 | 309 | -65 | 13 | -1 |

V table 1: i0 {32,448,32,0}, i1 {17,446,55,-6}, i2 {3,437,79,-7}, i3 {-7,421,107,-9}, i4 {-14,399,138,-11}, i5 {-18,373,170,-13},
i6 {-20,343,204,-15}, i7 {-20,310,240,-18}, i8 {-19,275,275,-19}.

Exact writes (address=value; each line is one tap j, phases i = 0..8; computed from the rows above, I):

```
H j0 19940090=0000000c 19940094=00000009 19940098=00000007 1994009c=00000005 199400a0=00000003 199400a4=00000002 199400a8=00000001 199400ac=00000000 199400b0=ffffffff
H j1 199400b4=ffffffe0 199400b8=ffffffe8 199400bc=fffffff0 199400c0=fffffff7 199400c4=fffffffd 199400c8=00000002 199400cc=00000007 199400d0=0000000a 199400d4=0000000d
H j2 199400d8=00000038 199400dc=0000001d 199400e0=00000006 199400e4=fffffff2 199400e8=ffffffe2 199400ec=ffffffd5 199400f0=ffffffcb 199400f4=ffffffc4 199400f8=ffffffbf
H j3 199400fc=000001bc 19940100=000001bd 19940104=000001b6 19940108=000001aa 1994010c=0000019a 19940110=00000186 19940114=0000016d 19940118=00000152 1994011c=00000135
H j4 19940120=00000034 19940124=00000052 19940128=00000070 1994012c=00000090 19940130=000000b1 19940134=000000d3 19940138=000000f4 1994013c=00000115 19940140=00000135
H j5 19940144=ffffffe0 19940148=ffffffd9 1994014c=ffffffd2 19940150=ffffffcc 19940154=ffffffc6 19940158=ffffffc1 1994015c=ffffffbe 19940160=ffffffbe 19940164=ffffffbf
H j6 19940168=0000000c 1994016c=0000000d 19940170=0000000e 19940174=0000000f 19940178=00000010 1994017c=00000010 19940180=00000010 19940184=0000000f 19940188=0000000d
H j7 1994018c=00000000 19940190=fffffffd 19940194=fffffffd 19940198=fffffffd 1994019c=fffffffd 199401a0=fffffffd 199401a4=fffffffe 199401a8=fffffffe 199401ac=ffffffff
V j0 19940000=00000020 19940004=00000011 19940008=00000003 1994000c=fffffff9 19940010=fffffff2 19940014=ffffffee 19940018=ffffffec 1994001c=ffffffec 19940020=ffffffed
V j1 19940024=000001c0 19940028=000001be 1994002c=000001b5 19940030=000001a5 19940034=0000018f 19940038=00000175 1994003c=00000157 19940040=00000136 19940044=00000113
V j2 19940048=00000020 1994004c=00000037 19940050=0000004f 19940054=0000006b 19940058=0000008a 1994005c=000000aa 19940060=000000cc 19940064=000000f0 19940068=00000113
V j3 1994006c=00000000 19940070=fffffffa 19940074=fffffff9 19940078=fffffff7 1994007c=fffffff5 19940080=fffffff3 19940084=fffffff1 19940088=ffffffee 1994008c=ffffffed
```

Coef set 0 is shared with DPP0 (coef_id 0 for id 0 and 1), but DPP0 has no SCALE attribute (S dts:63-65), so nothing else uses it.

## 4. Base address, alignment and error/status registers

- **BASEADDR width (S):** `DMA_BASEADDR_P0..P3` = +0x40/+0x44/+0x48/+0x4C (`rt/regs-dpp.h:201-204`); the `dma_addr_t` is written with
  the 32-bit `dma_write` (`rt/dpp_reg.c:1177-1181`). There is no high-address register in `rt/regs-dpp.h` (searched for HIGH/_H/
  MSB/EXT; only QOS_LUT_HIGH 0x134 matches). The DRM platform device uses a 32-bit coherent DMA mask
  (`dpu/exynos_drm_drv.c:2090`). **I:** with the SysMMU bypassed (NAT-177 CTRL 0), the buffer must lie below 4 GiB physical.
- **Alignment:** not stated. The only related item is `IDMA_CFG_ERR_BASE_ADDR_P0` (b6 of +0x740, `rt/regs-dpp.h:436`), whose rule is
  not in the source. Size restrictions are align 1 (dts:1157-1162). **I:** S-Boot's 0xfa200000 is 2 MiB aligned; use a page-aligned (or
  2 MiB-aligned) PA to stay inside known-good territory.
- **DPP CFG_ERR** 0x1993101C (S `rt/regs-dpp.h:1097-1102`): b4 SCL_POS, b3 SCL_RATIO, b2 ODD_SIZE, b1 MAX_SIZE, b0 MIN_SIZE.
- **DMA IRQ_STATUS** 0x19901338 (S `rt/regs-dpp.h:388-405`): b20 HDR_ERR, b17 TDMC_SCL_ERR, b16 TDMC_DMA_ERR, b14 DPP_CONFIG_ERR,
  b13 DPP_INST_OFF, b12 DPP_FRAME_DONE, b9 VOTF_ERR, b8 AXI_ADDR_ERR, b7 MO_CONFLICT, b6 FBCD_ERR, b5 RECOVERY_TRG, b4 CONFIG_ERR,
  b3 READ_SLAVE_ERR, b2 DEADLOCK, b1 INST_OFF_DONE, b0 FRAME_DONE. Stock clears by writing the read value back
  (`rt/dpp_reg.c:235-238,1641-1650`).
- **DMA CONFIG_ERR_STATUS** 0x19901740 (S `rt/regs-dpp.h:420-443`): b21 ROTATION, b20 IMG_HEIGHT_ROTATION, b18 SAJC, b17 SBWC, b16
  BLOCK, b15 FORMAT, b14..b11 STRIDE3..0, b10 CHROM_STRIDE, b9..b6 BASE_ADDR_P3..P0, b5 SRC_OFFSET_Y, b4 SRC_OFFSET_X, b3 IMG_HEIGHT,
  b2 IMG_WIDTH, b1 SRC_HEIGHT, b0 SRC_WIDTH. **S:** "CFG_ERR is cleared when clearing pending bits", so read +0x740 and DPP +0x1C
  **before** clearing +0x338 (`rt/dpp_reg.c:1637-1645`).
- Other read-only checks after the commit:
  - DMA1 +0x730 DEBUG_ADDR_ERR [3:0] (`rt/regs-dpp.h:413-418`); RDMA_ENABLE +0x0 b2 OP_STATUS, b1 INST_OFF_PEND (`:74-84`);
  - DPP1 +0x30 OP_STATUS b0 (`:1121-1122`), +0x98 SCL_STATUS [1:0] 0 idle / 1 queued / 3 busy (`:1248-1252`);
  - SRAMC0_D0 0x1995801C INT_ERROR_STATUS: b0 SRAM_FULL, b(7+4i) SCL_FULL(i), b(6+4i) ROT, b(5+4i) SBWC, b(4+4i) SAJC
    (`rt/regs-decon.h:1205-1212`; `rt/decon_reg.c:221-245`; base dts:826);
  - shadows equal the new values: DMA1 +0x410/+0x414/+0x41C/+0x440, DPP1 +0x180/+0x184/+0x188/+0x18C/+0x13C/+0x138, SRAMC1
    +0x810/+0x814, SCL_COEF +0x200.. (offsets from section 0).
- **I:** stock also counts scaler SRAM (16 units for an alpha RGB scaler out of `rsc_sram = <42>`), but only when `dpp,rsc_check` is
  set, and it is commented out (`rt/dpp_reg.c:2048-2059`; dts:78,86). No register write follows from it.

## 5. Fallback write-back to the NAT-177 state, and the pre-write save list

### Read before the first write (save every value)

| Block | Addresses | Why |
|---|---|---|
| DECON | 0x19100004 (twice), 0x19100020, 0x19100030, 0x19100050, 0x19100070, 0x19100200 | commit control; GLOBAL_CON and INT_PEND were not read in NAT-177 |
| WIN3 / WINCON3 | 0x19113000..0x1911301C, 0x19133000 (+ shadows +0x800) | unchanged, verify |
| DMA1 | 0x19901000, +0x08, +0x0C, +0x10, +0x14, +0x18, +0x1C, +0x40, +0x44, +0x50..+0x5C, +0x70, +0x100, +0x130, +0x134, +0x140, +0x180, +0x200, +0x30C, +0x330, +0x334, +0x338, +0x730, +0x740, and shadow +0x400 of each | every register C-list or init touches |
| DPP1 | 0x19931000, +0x1C, +0x30, +0x38, +0x3C, +0x64, +0x80..+0x98, shadow +0x100.. | C-list |
| SRAMC1 | 0x1995100C, +0x10, +0x14, shadow +0x810/+0x814 | C1/C2 |
| SCL_COEF set 0 | 0x19940000..0x199401AC (108 words) and 0x19940200..0x199403AC | C7/C8; never read so far |
| HDR_COMM1 | 0x19961000..0x1996105C (24 words), shadow +0x800 | C14, C27–C30, C34; never read so far |
| SRAMC0_D0 / G | 0x1995801C; 0x1995F00C, 0x1995F010 | error status; global full-alloc setting (`rt/regs-decon.h:1216-1226`; `rt/decon_reg.c:149-190`) |

### Write-back (same DECON sequence as 2a/2e around it: A1, A2, writes, D1–D7, then TRIG_CON back to 0x3063)

| Address | Value (NAT-177) | Note |
|---|---|---|
| 0x19931080 DPP1 SCL_CTRL | 0x0 | scaler off first (stock writes only ENABLE=0 when not scaling, `rt/dpp_reg.c:892-905`) |
| 0x19931088 / 0x1993108C | 0x00100000 / 0x00100000 | |
| 0x19931084 | 0x0 | stock would write 0x09240438 here even unscaled (`rt/dpp_reg.c:1204-1207`); 0 restores S-Boot |
| 0x1993103C | 0x09240438 | |
| 0x19931038 | 0x00000080 | |
| 0x19931090 / 0x19931094 | 0 / 0 | |
| 0x19931064 | saved value | not in NAT-177 |
| 0x19901010 / 0x19901014 | 0x438 / 0x924 | |
| 0x19901018 | 0x0 | |
| 0x1990101C | 0x09240438 | |
| 0x19901040 | 0xfa200000 | |
| 0x19901008 | 0xff400000 | |
| 0x19901050 | 0x0 | |
| 0x19901044, +0x54..+0x5C, +0x70, +0x100, +0x180 | saved values | not in NAT-177 |
| 0x19951010 / 0x19951014 | 0x0 / 0x0 | |
| HDR_COMM1 words, SCL_COEF set 0 words | saved values | coefficients are unused with SCL_CTRL = 0 (I) but restore for exactness |

Then verify the shadows (+0x400 DMA, +0x100 DPP, +0x800 SRAMC) equal the NAT-177 table and SHD_REG_UP_REQ reads 0.

## 6. Open questions and the read-only check for each

| # | Question | Check that resolves it |
|---|---|---|
| Q1 | Values of the registers NAT-177 did not read (DMA1 +0x0, +0x44, +0x54..5C, +0x70, +0x100, +0x130..140, +0x180, +0x330/334; DPP1 +0x64; HDR_COMM1; SCL_COEF; GLOBAL_CON; INT_PEND) | One more read-only snapshot of the "save" table above, gated on PMU DPUF0 on as in NAT-176 |
| Q2 | Which SHD_REG_UP_REQ bit latches DMA/DPP/SRAMC/SCL_COEF shadows; stock sets 0xFFFF + b31 + b20 and does not say | After the commit, read DMA1 +0x440 and DPP1 +0x180; equal to the new values = latched |
| Q3 | BASEADDR alignment rule behind CONFIG_ERR b6 | After the commit, read DMA1 +0x740 and +0x338; b6 / b4 clear with the chosen PA |
| Q4 | Is the DMA really reading physical addresses above the 0x80000000 DRAM base with the given 32-bit value (SysMMU bypass) | NAT-177 already shows 0xfa200000 works; for the new PA check +0x338 b8 AXI_ADDR_ERR and +0x730 stay 0 |
| Q5 | Does the iOS surface use exactly 4500 B per row; stock has no pitch register for linear buffers (STRIDE_SEL b31 exists, units not stated) | Read the surface's bytes-per-row on the iOS side (host/driver code, not the DPU); if padded, do not use this path without new source evidence |
| Q6 | Per-pixel alpha: win3 blends with coverage (FUNC_CON_1 0x0a0b0a0b) over win2, which still scans 0xfa200000 | Check that the iOS buffer alpha is 0xFF everywhere; otherwise choose XRGB8888 (IDMA format 4, `len_alpha` 0 → DPP ALPHA_SEL 0, SRAMC SCL_ALPHA_EN 0; `dpu/exynos_drm_format.c:94-104`) or disable win2 (WINCON2 b0) |
| Q7 | DISP aclk for DEADLOCK_CTRL (C38) | Read 0x19901100 before the change and keep it |
| Q8 | Whether the DPP accepts the BEXT bit (C31) change from S-Boot's 0x80 to stock 0x180 without visible effect for 8-bit input | Read DPP1 +0x38 shadow (+0x138) after the commit; compare the frame |
| Q9 | Whether S-Boot's continuous unmasked trigger behaves the same after the commit (stock would mask) | FRAME_COUNT 0x19100004 read twice ~1 s apart stays ~120/s after D5 |
| Q10 | SRAM availability for the scaler (`SRAMC_SCL_FULL`) | Read 0x1995801C after the commit; b7/b11 clear |

## Not established

- No write in this README has been executed on the phone. The sequence is the stock driver's, applied by hand; it was not run here.
- The source does not describe how hardware maps SHD_REG_UP_REQ bits to the DPUF shadows, the base-address alignment rule, the stride
  units, or the semantics of RDMA_MST_SECURITY (+0x200 = 1 on this phone; only the name is defined, `rt/regs-dpp.h:330`).
- Files read: `rt/dpp_reg.c`, `rt/regs-dpp.h`, `rt/decon_reg.c`, `rt/regs-decon.h`, `cm/exynos_dpp_coef.h`, `cm/dpp_cal.h`,
  `cm/decon_cal.h`, `cm/cal_config.h`, `dpu/exynos_drm_dpp.c`, `dpu/exynos_drm_decon.c`, `dpu/exynos_drm_format.c`,
  `dpu/exynos_drm_fb.c`, `dpu/exynos_drm_hdr.c`, `dpu/exynos_drm_sfr_dma.c`, `dpu/exynos_drm_drv.c`, `dpu/Makefile`, dts,
  `arch/arm64/boot/dts/exynos/s5e9945-sysmmu.dtsi:153-167`, `e1s_defconfig`.

## Re-checked by the task owner, and the format chosen for NAT-179

Prepared by a research subagent and re-checked against `git show HEAD:` in this session:
- coefficient selection, `DPP_SC_RATIO_7_8` and the 9×8 / 9×4 loops (`rt/dpp_reg.c:33-34, 826-905`);
- the `DPP_H_COEF` / `DPP_V_COEF` address macros (`rt/regs-dpp.h:1273-1276`) and table 1, H phase 0 `{12,-32,56,444,52,-32,12,0}` and
  V phase 0 `{32,448,32,0}` (`cm/exynos_dpp_coef.h:35-36, 165-166`);
- TRIG_CON and SHD_REG_UP_REQ bits (`rt/regs-decon.h:148-167, 206-213`) and the 32-bit `DMA_BASEADDR_P0` with no high register
  (`rt/regs-dpp.h:201-204`).

**Format (resolves Q6).** NAT-179 uses XRGB8888 instead of ARGB8888, because win3 blends with coverage over win2, which still scans the
old buffer. A pixel alpha below 0xFF must not let stale content through.
- **S:** XRGB8888 has `dma_fmt` IDMA 4 and `dpp_fmt` 0 with `len_alpha` 0 (`dpu/exynos_drm_format.c:94-104`;
  `rt/regs-dpp.h:105,109`). `len_alpha` 0 selects `DPP_ALPHA_PER_FRAME` = ALPHA_SEL 0 (`rt/dpp_reg.c:1219`;
  `rt/regs-dpp.h:1132-1135`), and SRAMC `scl_alpha_en` only applies with `len_alpha > 0` (`rt/dpp_reg.c:169-173`).
- Resulting values:
  - DMA1 IN_CTRL_0 0xff400400 (C26 with format 4);
  - DPP1 IO_CON 0x00000100 (C31–C33: BEXT 1, ALPHA_SEL 0, format 0);
  - SRAMC1 MODE 0x00001000 (C2: SCL_EN only).
- **I:** the memory byte order is the same as ARGB8888 (B, G, R, X), so iOS BGRA surfaces display unchanged.

**Q1 (unread registers).** NAT-179's image reads and logs the whole "read before the first write" table before any write, so no
separate read-only run is needed. A hang on one of those reads would show up as the last printed group, the same as a write would.
