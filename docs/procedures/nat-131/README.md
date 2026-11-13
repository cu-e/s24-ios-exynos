# NAT-131: USB 3 SuperSpeed device-mode bring-up plan for S5E9945 (source review)

Evidence kind: **source-review**. Nothing here ran on the phone. Every `file:line` below is in the vendor kernel
`references/s24-linux` at the pin `417484173abc2c4fa93e738ea82ad9f2e84911b1` unless another repository path is given.
`python3 -I -B docs/procedures/nat-131/check_cites.py` checks that the cited text is on each cited line (204 citations,
`cites.tsv`). It does not check that my reading of a line is right. Whether the running firmware S921BXXS9BYH3 matches the
pin is not established, as in NAT-040.

This plan adds to the USB2 ladder (NAT-040 plan, NAT-045 rungs L0-L8) and does not replace it. The USB2 rungs L1-L5 stay
as they are and remain the fallback. The SuperSpeed (SS) part replaces only NAT-040 steps 4.05/4.06 (pipe3 detach), and it
adds DWC3 and engine work around L6-L8.

## 0. Findings in short

1. **The compiled SS path is small and fully in the source.** The e1s build uses `CONFIG_PHY_EXYNOS_USBDRD_EUSB=m`
   (`arch/arm64/configs/e1s_defconfig:7494`). Its objects are `phy-exynos-usbdrd-eusb.c`, `exynos-usb-blkcon.c` and
   `phy-exynos-snps-usbdp.c` (`drivers/phy/samsung/Makefile:24`). The SS PHY is a Synopsys USB/DP combo PHY: DT
   `sub_phy_version = <0x801>` and `snps_usbdp_ram_mode = <1>` (`s5e9945-usb.dtsi:127,129`). In device mode, Android
   brings it up in `exynos_usbdrd_pipe3_init` (`phy-exynos-usbdrd-eusb.c:1487-1556`) in four steps:
   - read the orientation GPIO;
   - release PMU isolation at `PMU+0x620`;
   - run `exynos_usbcon_ready_to_pipe3_phy`;
   - run `phy_exynos_snps_usbdp_phy_enable` (`phy-exynos-snps-usbdp.c:869-925`). This step resets the PHY, sets the
     power, loads **6144 16-bit words of PHY SRAM firmware** through the CR port, waits for RX calibration, applies
     analog tuning, and switches the Type-C Assist (TCA) from NC to USB mode.
2. **The SS link is Gen1 (5 Gb/s) by design.** The DT sets `exynos,force_gen1` (`s5e9945-usb.dtsi:51`). The glue then sets
   `LLUCTL.FORCE_GEN1` (bit 10 of `0x1790d024`, `dwc3-exynos.c:381-382`), but only on DWC_usb31 1.20a or later
   (`dwc3-exynos.c:375`). The loader has logged GSNPSID `0x33313130` (DWC_usb31, NAT-043 run-002 and NAT-058 run-001
   analysis). The revision itself lives in `VER_NUMBER` (`0x1790c1a0`, `core.c:1001`), which has not been read yet.
3. **Orientation comes from a GPIO, not from the PD stack.** `CONFIG_CHECK_CTYPE_SIDE` is not set (`e1s_defconfig:5916`),
   so the driver reads `phy,gpio_phy_port = <&gpc7 1 0x0>` (`s5e9945-e1s_common.dtsi:1316`, `phy-exynos-usbdrd-eusb.c:1514-1521`).
   The DP driver reads the same pin (`dp,usb_con_sel`, `s5e9945-e1s_common.dtsi:1269`) and logs it as "Get direction From
   PDIC CC1/CC2" (`exynos_drm_dp.c:3306-3312`). That suggests the CC controller (MAX77775, `e1s_defconfig:8583`) drives the pin
   (**inferred**). GPC7 is bank `0x1a0` of PERIC2 `0x11830000` (`pinctrl-exynos-arm64.c:1085`, `s5e9945.dts:377`), so
   CON = `0x118301a0` (pin 1 = bits [7:4]) and DAT = `0x118301a4` (bit 1); the CON/DAT offsets 0x00/0x04 come from
   `pinctrl-exynos-arm64.c:50`. The value picks the CR lane offsets (`phy-exynos-snps-usbdp.c:34-35`) and the PHY's
   `TCA_CONFIG.typec_flip_invert` (`:389-393`). The TCA's own orientation bit is always written as 0 (`:275`). A wrong value
   makes "USB3.0 work only in one direction" (`phy-exynos-usbdrd-eusb.c:2105`).
4. **TCA mode is USB-only.** `nc2usb_mode(info, FLD_OP_MODE)` writes `TCPC.mux = 1` (USB31), `valid = 1`, and waits up to
   1000 µs for `xa_ack` (`phy-exynos-snps-usbdp.c:257-298`). The DP-alt modes (2, 3) are not used for USB.
5. **Nothing in S-Boot's state is known to help.** The loader runs from RECOVERY after S-Boot, not after Android.
   S-Boot's own USB (upload mode) enumerated at **High Speed 480 Mbps**
   (`artifacts/recovery-qualification/attempt-001/lsusb-04e8-685d-sec-upload.txt`). The only HSI0 state that is known to be
   inherited is "pd_hsi0 on" (`pd_was_on = 1` in the NAT-043/NAT-058 ladder records). So every SS step below is classed
   **must-do**. Only the USB2 prerequisites are inherited, through the existing ladder.
6. **The vendor has no software SS→HS fallback.** It reads the negotiated speed from `DSTS.CONNECTSPD` at CONNECTDONE
   (`gadget.c:4055-4131`). On this phone an SS-programmed controller has been seen connected at HS: NAT-039 recorded
   `maximum_speed: super-speed`, `current_speed: high-speed` (`docs/procedures/nat-039/capture-extract/udc-state.txt`). That
   was with Android's PHY initialised. With the PIPE interface detached or a PHY that never answers, falling back depends
   on the LTSSM reaching SS.Disabled, which is not guaranteed. So the loader needs its own bounded fallback (section 2).
7. **No PMIC write is involved, but the rails are an open condition.** The four USB rails (`vdd075` 0.75 V, `vdd12`
   1.2 V, `vdd18` 1.8 V, `vdd33` 3.1 V) are switched together with pd_hsi0 in Android (`exynos-pd.c:115-129`,
   `phy-exynos-usbdrd-eusb.c:1803-1851`). The source does not say which rail feeds which PHY block. Their state at loader
   entry is unknown (U6).
8. **The repository has no record of a 5000 Mbit/s link.** The only Android speed capture (NAT-039, 2026-11-11) says
   `high-speed`. The 5000 Mbit/s observation in the task brief is caller-reported (U1).

## 1. Drivers and the Android device-mode call order

| what | where |
|---|---|
| DT: controller, PHY windows, PMU offsets, PHY versions | `arch/arm64/boot/dts/exynos/s5e9945-usb.dtsi:28-157` (PHY `reg` 99-104, `pmu_offset_dp` 114, `sub_phy_version` 127, RAM mode 129, `exynos,force_gen1` 51, U1/U2 quirks 83-84) |
| board DT: `maximum-speed`, orientation GPIO, rails, SS tune table (disabled, all `0xffffffff`) | `arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi:1300, 1316, 1321-1324, 913-914` |
| PHY driver (glue to the CAL) | `drivers/phy/samsung/phy-exynos-usbdrd-eusb.c`: `exynos_usbdrd_pipe3_init` 1487, `exynos_usbdrd_pipe3_phy_isol` 673, `exynos_usbdrd_pipe3_disable` 2140, `exynos_usbdrd_pipe3_exit` 1438, probe resource map 2346-2503 |
| USBCON wrapper CAL | `drivers/phy/samsung/exynos-usb-blkcon.c`: `init_link` 28, `detach_pipe3` 88, `disable_pipe3` 109, `ready_to_pipe3` 128 |
| SNPS USB/DP PHY CAL | `drivers/phy/samsung/phy-exynos-snps-usbdp.c`: CR port 92-220, resets 222-244, TCA 251-326, initiate 346-394, enable 869-925, disable 927-945 |
| register layouts | `snps-usbdp-con-reg.h` (PHY ctrl), `snps-usbdp-tca-reg.h` (TCA), `exynos-usb-blkcon-sfr.h` (USBCON), `snps-usbdp-ram-code.h` (firmware) |
| DWC3 core / glue / OTG | `drivers/usb/dwc3/core.c` (`dwc3_core_init` 1215, `dwc3_ss_phy_setup` 766), `dwc3-exynos.c` (`dwc3_core_config` 263-409, `dwc3_exynos_core_init` 437), `dwc3-exynos-otg.c` (`dwc3_otg_start_gadget` 738), `gadget.c`, `ep0.c` |

Device-mode order in Android (all at the pin):

1. `dwc3_otg_start_gadget` (`dwc3-exynos-otg.c:738`) → `pm_runtime_get_sync` (805/812) → core runtime resume →
   `dwc3_core_init`.
2. `dwc3_core_init`: `dwc3_phy_setup` → `dwc3_ss_phy_setup` (`core.c:1233`, `:766-810`), then `phy_init(usb2)` = `utmi_init`
   (the NAT-040 USB2 sequence, `core.c:1259`), then `phy_init(usb3)` = `exynos_usbdrd_pipe3_init` (`core.c:1269`), then
   `dwc3_core_soft_reset` (`core.c:1279`), global control and the event buffers.
3. `dwc3_exynos_core_init` (`dwc3-exynos-otg.c:819`, `dwc3-exynos.c:437-470`) → `dwc3_core_config` (SS link registers).
4. `dwc3_otg_pm_ctrl(exynos, 0)`: U1/U2 off in DCTL (`dwc3-exynos-otg.c:824`, `:280-284`).
5. Gadget pull-up → `dwc3_gadget_run_stop(on)` → `__dwc3_gadget_set_speed` (DCFG speed), then `RUN_STOP` (`gadget.c:2541-2543`).

Not on the device-mode path: `usb_power_notify_control` / `usb3_phy_control` (only the xHCI host glue calls them,
`xhci-exynos.c:297`); the TCA "system configuration" branch (`phy-exynos-snps-usbdp.c:299-323`); U3 ReWA (`pipe3_vendor_set`,
suspend only); `CONFIG_CHECK_CTYPE_SIDE`; the DT SS tune values (every entry is `0xffffffff`, which becomes -1,
`phy-exynos-usbdrd-eusb.c:1157`, and is skipped, `phy-exynos-snps-usbdp.c:403`); the DT tune hook in `pipe3_tune`, which is
commented out (`phy-exynos-usbdrd-eusb.c:1757`).

Probe resource map (`phy-exynos-usbdrd-eusb.c:2346-2503`, `:1282-1285`): index 0 `0x178a0000` = USBCON (`blkcon regs_base`),
1 `0x178b0000` = eUSB2 ctrl, 2 `0x178c0000` = eUSB2 PHY, 3 `0x178d0000` = **USBDP PHY ctrl** (`regs_base` of the SNPS CAL),
4 `0x178e0000` = **TCA** (`regs_base_2nd`), 5 `0x17900000` = DWC3 (`link_base`, used for the link TX de-emphasis registers).

## 2. Ordered SuperSpeed register sequence

Physical address = DT base + offset. Bit positions come from the bitfield unions in the cited headers. Class:
**M** = must be done by the loader (the S-Boot/RECOVERY state is not Android's, and nothing shows S-Boot trains SS);
**I** = inherited from the existing USB2 ladder (already done by L1-L5 and proven by NAT-043/NAT-078); **R** = read-only
check; **E** = engine or descriptor work, not a single register. "Vendor bound" is what Android does on timeout. Android
mostly only warns, and `pipe3_init` ignores the return value of `phy_enable` (`phy-exynos-usbdrd-eusb.c:1555`). The loader
must treat every such timeout as "SS failed, go to HS" (section 3).

| # | step | register (phys) | value / mask | source | class |
|---|---|---|---|---|---|
| S0 | USB2 prerequisites: pd_hsi0 on, CMU_HSI0 replay (`hsi0_cmu_init`, incl. `MUX_CLK_HSI0_USB32DRD` and the USB32DRD user mux), Q-channels, PMU `0x1286061c` bit 0, USBCON `init_link` (incl. `link_sw_rst`), eUSB2 initiate | see NAT-040 plan 0.xx-3.xx | unchanged | `flexpmu_cal_local_s5e9945.h:1383-1394`, `exynos-usb-blkcon.c:28-73` | I |
| S0a | clocks the SS blocks need but no Linux driver enables: USBDPPHY_CTRL_PCLK gate, USBDPPHY_TCA_APB_CLK gate, USBLINK_ACLK gate, QCH_S_TCA | `0x17802058`, `0x1780205c`, `0x17802060`, `0x17803064` | read and log only. The DT lists no TCA clock, so Android relies on defaults or auto-gating (**inferred**); the bit layout of these gate registers is not decoded in this review | `cmucal-sfr.c:6235,6237,6239,6253`; vendor saves/restores QCH_S_TCA, `flexpmu…h:1427` | R |
| S1 | DWC3 SS PHY setup, **before** the PHY init | GUSB3PIPECTL(0) `0x1790c2c0` | clear bit 27 `UX_EXIT_PX` and bit 17 `SUSPHY`; no other GUSB3PIPECTL quirk is set in the DT | `core.c:766-810` (776, 779); order `core.c:1233` < `1269` | M |
| S2 | orientation | GPC7 CON `0x118301a0` [7:4], DAT `0x118301a4` bit 1 | read only: CON[7:4] must be 0 (input; Linux sets this at probe, `phy-exynos-usbdrd-eusb.c:2456`); `used_phy_port = DAT bit 1` (`reverse_con_dir` is absent from the board DT, so there is no inversion, `:2461`) | `phy-exynos-usbdrd-eusb.c:1514-1524`; DT `s5e9945-e1s_common.dtsi:1316` | M (read) |
| S3 | PIPE3 / combo-PHY isolation release | PMU `0x12860620` | bit 0 := 1 (`val = on ? 0 : mask`, called with on = 0; mask = BIT(`pmu_mask` = 0)) | `phy-exynos-usbdrd-eusb.c:673-685`, call `:1552`, mask `:2444`; DT `s5e9945-usb.dtsi:112-114` | M |
| S4 | `ready_to_pipe3` (replaces NAT-040 4.05/4.06 detach) | USBCON LINKCTRL `0x178a0004`; HSP_MISC `0x178a0114`; LINK_CLKRST `0x178a000c` | LINKCTRL bit 16 `force_pipe_en` := 0; HSP_MISC [1:0] `sel_res_tune_mux` := 1, bits 4-7 (`set_req/ack_in2/in1`) := 0; LINK_CLKRST bit 1 `link_pclk_sel` := 1 (link pclk from the PHY pipe clock) | `exynos-usb-blkcon.c:128-153`; offsets `exynos-usb-blkcon-sfr.h:52,211,649` | M |
| S5 | assert lane 0 and PHY reset | USBDP RST_CTRL `0x178d0000` | first bit 4 `pipe_lane0_reset_n` := 0 and bit 5 (ovrd) := 1; then bit 0 `phy_reset` := 1 and bit 1 (ovrd) := 1 | `phy-exynos-snps-usbdp.c:234-244, 222-232`, order `:872-873`; `snps-usbdp-con-reg.h:21` | M |
| S6 | MPLL-A configuration | PHY_CONFIG0 `0x178d0100`; DP_CONFIG12 `0x178d0234` | CONFIG0 bit 21 `ss_mplla_ssc_en` := 1; DP_CONFIG12 bits 8-11 (`dp_txN_mpll_en`) := 0 | `phy-exynos-snps-usbdp.c:631-647`; `snps-usbdp-con-reg.h:87,1102` | M |
| S7 | DP TX lanes off | DP_CONFIG13 `0x178d0238` | bits 0-3 (`dp_txN_disable`) := 1, bits 4-7 (`dp_txN_reset`) := 1 | `phy-exynos-snps-usbdp.c:328-344`, call `:880`; `snps-usbdp-con-reg.h:1143` | M |
| S8 | PHY initiate | PHY_CONFIG0 `0x178d0100`; PHY_CONFIG2 `0x178d0108`; CR_PARA_CON0 `0x178d0004`; SRAM_CON `0x178d0110`; TCA_CONFIG `0x178d016c` | CONFIG0 bit 1 `ana_pwr_en` := 1; CONFIG2 bit 24 `test_powerdown` := 0; CR_PARA_CON0 bit 0 `cr_para_sel` := 1; SRAM_CON bit 1 `ext_ld_done` := 0 and bit 0 `sram_bypass` := 0 (RAM mode); wait 10 µs; **TCA_CONFIG := 0x4 if port 1, 0x0 if port 0** (a whole-word write; bit 2 = `typec_flip_invert`) | `phy-exynos-snps-usbdp.c:346-394` (353, 358, 363, 375, 387, 391, 393); `snps-usbdp-con-reg.h:40,169,217,650` | M |
| S9 | release resets | RST_CTRL `0x178d0000` | wait 20 µs; bit 0 := 0 (bit 1 stays 1); bit 4 := 1, bit 5 := 0 | `phy-exynos-snps-usbdp.c:884-887` | M |
| S10 | wait for SRAM init | SRAM_CON `0x178d0110` bit 2 `sram_init_done` | ≤ 1000 rounds of (10 CR-clock toggles = CR_PARA_CON0 bit 8 high/low, 1 µs each, then 1 µs); vendor bound: warn and continue | `phy-exynos-snps-usbdp.c:649-666` | M |
| S11 | VCO low-frequency override, RX lanes 1 and 2 | CR `0x31c5`, `0x32c5` (through the CR port) | := `0x8000` each, no ack check | `phy-exynos-snps-usbdp.c:891-895` | M |
| S12 | PHY firmware download (RAM mode) | CR port: CR_PARA_CON0 addr [31:16], clk bit 8, ack bit 4; CON2 `0x178d000c` wr_data [31:16], wr_en bit 0 | 6144 writes from `cp_int_ref_x2_code` (`snps-usbdp-ram-code.h:35-6183`, addresses `0xC000..0xD7FF`), chosen because `VER_MINOR(0x801) = 1` (`phy-samsung-usb-cal.h:75`, `phy-exynos-snps-usbdp.c:676-679`, `skip_check_ack = 1`); then `sram_ext_ld_done`: CR clk high, SRAM_CON bit 1 := 1, clk low, poll bit 2 (≤ 1000 rounds of 8 toggles) | `phy-exynos-snps-usbdp.c:126-170, 668-715, 897-908` | M |
| S13 | RX calibration done | CR `CRREG_LANE_RX(0x303e)` = `0x313e` (port 0) / `0x323e` (port 1), bit 1 | ≤ 100 × 1 ms; vendor bound: "Fail usbdp phy init(Not check cal done)", return -1, which is ignored | `phy-exynos-snps-usbdp.c:745-754`, lane map `:34-35` | M |
| S14 | PHY identity | CR `0x003d` (PMA), `0x2010` (PCS), `0x2011`/`0x2012` (firmware) | read and log; compare with Android dmesg (U3) | `phy-exynos-snps-usbdp.c:756-764` | R |
| S15 | TX/RX analog tuning | CR `0x0022`; `CRREG_LANE_TX(0x10eb)` = `0x10eb`/`0x13eb`; `0x301a`, `0x311a`, `0x321a`, `0x331a` | `0x22`: [6:4] := 7, bit 7 := 1 (TX swing max); `10eb` \|= `0xe` (iBoost); each `xx1a`: [6:4] := 5, bit 7 := 1 (termination 50 → 44 Ω per the vendor comment); DT tune params: none (all -1) | `phy-exynos-snps-usbdp.c:766-800, 822` | M |
| S16 | link TX de-emphasis (vendor comment: Gen2 preset/de-emphasis) | DWC3 window `0x1790d060`, `0x1790d064`, `0x1790d068`, `0x1790d06c` | [17:0] := `0x8c45`, `0xe45`, `0x8d80`, `0xf80` | `phy-exynos-snps-usbdp.c:827-867`; `snps-usbdp-con-reg.h:1374-1377`. With `force_gen1` this probably has no effect (**inferred**); keep it to match the vendor | M |
| S17 | TCA: NC → USB, controller-synced | TCA `0x178e0020` CTRLSYNCMODE_CFG0; `0x178e0008` INTR_STS; `0x178e0004` INTR_EN; `0x178e0014` TCPC | CFG0 bit 16 `auto_safe_state` := 0; INTR_STS := `0xffff`; INTR_EN bits 0, 1 := 1; TCPC [1:0] `mux` := 1, bit 2 `orientation` := 0, bit 3 `low_power` := 0, bit 4 `valid` := 1; poll INTR_STS bit 0 `xa_ack_evt` ≤ 1000 × 1 µs ("Timeout on the TCA!!"); INTR_STS := `0xffff`; INTR_EN bits 0, 1 := 0 | `phy-exynos-snps-usbdp.c:251-298` (260, 264, 274-277, 281, 288); `snps-usbdp-tca-reg.h:119,214` | M |
| S18 | DWC3 core soft reset, after the PHYs are up | DCTL `0x1790c704` CSFTRST | the existing `usbmon_init` 5.04-5.05 step | `core.c:1279` | I |
| S19 | glue SS link configuration | GUSB3PIPECTL `0x1790c2c0`; LLUCTL(0) `0x1790d024`; LSKIPFREQ `0x1790d020`; BU31RHBDBG `0x1790d800`; GUCTL1 `0x1790c11c` | GUSB3PIPECTL bit 28 `DISRXDETINP3` := 1 (`!DWC3_VER_IS_PRIOR(DWC3,250A)` is true for a DWC31 IP). **If `VER_NUMBER` ≥ `0x3132302a` (1.20a):** LLUCTL [4:0] := 7 (`TX_TS1_CNT`), \|= bit 7 `PIPE_RESET`, bit 10 `FORCE_GEN1`, bit 15 `EN_US_HP_TIMER`, `0xb << 16` `PENDING_HP_TIMER`, bit 23 `LTSSM_TIMER_OVRRD`; LSKIPFREQ [23:20] := 9, [26:24] := 5, bit 27 := 1; GUSB3PIPECTL bit 28 := 0; BU31RHBDBG \|= bit 3; GUCTL1 [23:21] := 1, \|= bit 31, bit 24 | `dwc3-exynos.c:364-405`; bit defs `dwc3-exynos.h:29-55`; revision `core.h:1263`, `core.c:1001` | M (branch depends on U4) |
| S20 | device speed | DCFG `0x1790c700` [2:0] | := 4 (`SUPERSPEED`), written while `RUN_STOP` = 0 (the vendor writes it just before `RUN_STOP`) | `gadget.c:2427-2494`, `:2541-2543`; `core.h:428` | M |
| S21 | U1/U2 off | DCTL `0x1790c704` bits 9-12 | := 0; reject SET_FEATURE U1/U2_ENABLE; BOS U1/U2 exit latencies 0 (DT `snps,dis-u1/u2-entry-quirk`) | `dwc3-exynos-otg.c:280-284` via `:824`; `ep0.c:405-443`; `gadget.c:2983-2995`; DT `s5e9945-usb.dtsi:83-84` | M + E |
| S22 | event enables | DEVTEN `0x1790c708` | the existing set; optionally add bit 3 `ULSTCNGEN` for the link trace (the vendor sets it only for DWC3 < 2.50a) | `gadget.c:2741-2761` | M (optional bit) |
| S23 | run | DCTL bit 31 `RUN_STOP` := 1; wait for DSTS bit 22 `DEVCTRLHLT` = 0 | existing engine step | `gadget.c:2496-2556` | I |
| S24 | at CONNECTDONE with `DSTS[2:0]` = 4 | ep0 MPS 512 (the engine already does this); bulk `wMaxPacketSize` 1024 + SS endpoint companion; DEPCFG `BURST_SIZE`; `bcdUSB` ≥ 0x0300 with a BOS; handle SET_SEL (6-byte OUT data stage, then DGCMD `SET_PERIODIC_PAR`) and SET_ISOCH_DELAY | — | `gadget.c:4095-4114`, `:600`; `ep0.c:689-770, 805-809` | E |
| S25 | link diagnostics, any time | DSTS `0x1790c70c` [21:18] `USBLNKST`; USBCON LTSTATE_HIS `0x178a0080` (history nibbles [19:0], bit 31 `linktrn_done` = POLL→U0 seen); TCA GEN_STATUS `0x178e0034`, PSTATE `0x178e0030` | read only | `core.h:512, 817-834`; `exynos-usb-blkcon-sfr.h:608-628`; `snps-usbdp-tca-reg.h:449,494` | R |

Cost estimate (**inferred**, from the CR protocol in `phy-exynos-snps-usbdp.c:92-170`): one CR write is at least about 7-8 µs
of `udelay(1)` steps, so S12 is about 50 ms; S10 + S12 + S13 + S17 is bounded at about 160 ms in the worst case.

Not needed for USB-only SS, and so not part of the plan: the TCA system-configuration branch, the DP CAL in `drivers/gpu/drm/samsung/dpu/cal_*`,
the DP user muxes (NAT-040 0.29/0.30), `ESS_CTRL.host_force_gen1_speed` (host only, `exynos-usb-blkcon-sfr.h:265`), the U3 ReWA
block, and any LDO or PMIC control.

The bounded loops changed between trees. `phy-exynos-snps-usbdp.c` at the BSP pin `f85e53cf` (`references/s24-bsp-reference`)
has unbounded `while (1)` loops in `cr_port_clear`, `check_fw_update_done` and `sram_ext_ld_done`; the NAT-131 pin bounds
them at 1000. `snps-usbdp-ram-code.h`, `snps-usbdp-con-reg.h`, `snps-usbdp-tca-reg.h`, `exynos-usb-blkcon.c`,
`phy-exynos-usbdrd-eusb.c` and `s5e9945-usb.dtsi` are byte-identical in the two trees (sha256 compared during this review).

## 3. When SS does not train: DWC3 behaviour and a bounded fallback

### 3.1 What the code and the measurements show

* The vendor driver contains no SS→HS fallback. `dwc3_gadget_conndone_interrupt` just takes `DSTS.CONNECTSPD` and sets ep0
  to 512 (SS) or 64 (HS) (`gadget.c:4084-4131`). The speed is chosen by the controller and the host.
* An SS-programmed core connecting at HS is normal. On this phone NAT-039 recorded `maximum_speed: super-speed` with
  `current_speed: high-speed`. That DCFG was SS then is **inferred**: `__dwc3_gadget_set_speed` clamps to `maximum_speed`.
  The vendor's own workaround for DWC3 < 2.20a always programs SS ("we cannot configure the IP to any speed other than the
  SuperSpeed", `gadget.c:2446-2460`), and such cores still serve USB2-only links (**inferred**).
* The hardware HS fallback depends on the USB 3 LTSSM of the device reaching SS.Disabled after failed receiver detection or
  polling, after which the device connects on USB 2.0. This comes from the USB 3.x specification's link-training rules,
  **recalled, not checked in this review**. It assumes a PIPE PHY that answers receiver detection (`PhyStatus`). If the
  PIPE is detached with forced `phystatus = 0` (the current loader state), or the PHY is half-initialised, the LTSSM may stay
  in Rx.Detect and the USB2 pull-up may never come (**inferred risk**). This is why the existing engine programs DCFG = HS
  (`docs/procedures/nat-076/engine/usbmon.c:1365-1367`), and why a software deadline is needed.
* The vendor's reconnect rule cites the Synopsys DWC_usb31 1.90a programming guide §4.1.9: a reconnect after a
  device-initiated disconnect needs a core soft reset before `RUN_STOP` (`gadget.c:2657-2662`). The soft disconnect ends
  active transfers first (§4.1.8 Table 4-7, `gadget.c:2598`), then clears `RUN_STOP` and polls `DEVCTRLHLT`
  (`gadget.c:2499-2556`, bound 500 reads).
* The vendor's runtime "USB3 off, USB2 continues" path is exactly detach + PHY disable (`exynos_usbdrd_pipe3_disable`,
  `phy-exynos-usbdrd-eusb.c:2140-2150`, used by `usb3_phy_control(off)`, `dwc3-exynos-otg.c:307-327`). The engine can return
  to that state without a reboot.
* The link state can be pushed by hand (`DCTL.ULSTCHNGREQ` = SS.Disabled, `core.h:476`; the vendor exposes it only through
  debugfs, `debugfs.c:621-622`). It is **not established** that a DWC31 core then attaches on USB2, so the design below does
  not depend on it.

### 3.2 Fallback design for the polled engine (all bounds are proposals)

```
P0  PHY gate. S10, S12-ext_ld_done, S13 and S17 each have a hard deadline (1 ms, 1 ms, 100 ms, 1 ms).
    Any timeout, a CR ack failure during S13-S15 reads, or S2 CON != input  ->  HS_PATH (no SS attempt).
P1  t0 = RUN_STOP:=1 with DCFG=SS.  Poll at <= 1 ms intervals in the normal engine loop:
      - record each change of DSTS.USBLNKST (and LTSTATE_HIS once per change) in a 32-entry trace;
      - CONNECTDONE & CONNECTSPD==4        -> SS_OK (keep going; MPS 512/1024);
      - CONNECTDONE & CONNECTSPD==0 (HS)   -> HS_NATURAL (hardware fell back; keep going at HS);
      - USBLNKST in {SS_INACT 0x6, CMPLY 0xa} seen, or no CONNECTDONE by t0 + T_SS  -> FORCED.
    T_SS proposal: 1500 ms. It covers the spec's Rx.Detect/Polling timeouts (hundreds of ms, recalled) plus host
    connect debounce and port reset; to be refined from the P1 trace of the first run.
FORCED (once per boot, never back to SS):
    1. DCTL.RUN_STOP := 0; keep acknowledging events; wait DSTS.DEVCTRLHLT == 1 (deadline 50 ms).
    2. pipe3_disable: USBCON detach (LINKCTRL bit16:=1, bit17:=0, bit18:=1; LINK_CLKRST bit1:=0;
       exynos-usb-blkcon.c:88-107) then PHY disable (RST_CTRL lane0/phy reset, CONFIG2 bit24:=1,
       CONFIG0 bit1:=0; phy-exynos-snps-usbdp.c:927-945).  PMU 0x12860620 left released (the vendor's
       pipe3_disable also leaves it).
    3. usbmon_init again with DCFG = HS (it does CSFTRST, event buffer, DEPSTARTCFG, ep0, DEVTEN):
       the reconnect rule of gadget.c:2657-2662.
    4. RUN_STOP := 1  ->  the HS path proven by NAT-043/NAT-078.
HS_PATH: pipe3 detach (NAT-040 4.05/4.06, today's L5) and DCFG = HS: exactly the current image.
Report: once any transport is up, emit one record: port, CON/DAT raw, S10/S12/S13/S17 times, PMA/PCS/FW IDs,
        VER_NUMBER, the LTSSM trace, outcome {SS_OK, HS_NATURAL, FORCED, HS_PATH}, t0-relative times.
```

Worst-case extra time before the HS log appears: the P0 deadlines (about 160 ms including the firmware download) +
`T_SS` (1.5 s) + 50 ms + one `usbmon_init` (less than 0.1 s). That is about 2 s, against a deadline of 45-60 s in the
current images. With no host attached, the run takes the FORCED path once and then waits as it does today. On the host,
the collector must accept the device on the xHCI USB3 root hub (SS) or on its USB2 root hub (HS). They are different
`bus` numbers on Linux (**inferred**, standard Linux xHCI behaviour); the NAT-043/NAT-058 runs saw bus 5 at HS.

## 4. Unknowns and the read-only check that resolves each

None of these checks uses debugfs. `clk_summary` crashed the phone once and is never to be read; debugfs is not mounted
and must not be mounted for this. No devmem. "Android" means `adb shell su -c '<one read command>'` under the NAT-039
deny-list.

| id | unknown | why it matters | check |
|---|---|---|---|
| U1 | Is the 5000 Mbit/s link real, on which host port, cable and orientation? NAT-039 (2026-11-11) recorded `high-speed` | it is the only proof the board path supports SS; it also gives the orientation case that worked | Android: `cat /sys/class/udc/17900000.dwc3/current_speed` (expect `super-speed`); host at the same time: `lsusb -t` and `cat /sys/bus/usb/devices/<port>/speed` (expect `5000`), plus the root-hub bus number |
| U2 | GPC7_1 value versus cable orientation; does the driver's sample match the plug? | S8 (`TCA_CONFIG`) and the S13/S15 lane offsets depend on it | Android: `cat /sys/devices/platform/178a0000.phy/exynos_usbdrd_phy_port` (the attribute group `exynos_usbdrd_groups`, `phy-exynos-usbdrd-eusb.c:288-299, 2631`; the path comes from the DT node name and is **inferred**, so confirm with `ls /sys/bus/platform/drivers/phy_exynos_usbdrd/`); `dmesg \| grep 'phy port'` (`:1522`); `cat /sys/class/typec/port0/orientation` if present. Repeat after the owner flips the plug. Never write the attribute: its store changes the port (`:303-317`) |
| U3 | Does the Android PHY init succeed, and which PMA/PCS/firmware IDs does it report? | gives reference values for S14 and confirms that the pinned RAM code is what runs | Android, after a cable replug: `dmesg \| grep -E 'PHY Boot mode\|PMA version\|PCS ID\|Firmware ID\|Timeout on the TCA\|Fail usbdp phy init\|CR write failed\|failed (cr_port_clear\|check_fw_update_done\|phy_exynos_snps_usbdp_phy_sram_ext_ld_done)'` (strings at `phy-exynos-snps-usbdp.c:120, 167, 288, 663, 714, 752, 757-764, 902`) |
| U4 | DWC_usb31 revision (`VER_NUMBER` `0x1790c1a0`, `VER_TYPE` `0x1790c1a4`) | it decides whether S19's LLUCTL/FORCE_GEN1 branch exists at all | no Android path without debugfs or devmem; native read-only probe (section 5) |
| U5 | State at loader entry of PMU `0x12860620`, the USBDP ctrl block, the TCA block and the CMU gates S0a | S-Boot is not Android; the plan assumes cold | native read-only probe |
| U6 | Are the four rails on at loader entry, and which feeds the combo PHY? Android: all four enabled (NAT-039); the source gives no per-block mapping | an unpowered combo PHY never sets `sram_init_done` or RX calibration; PMIC writes are out of scope | Android: `cat /sys/class/regulator/regulator.*/name`, `…/state`, `…/microvolts` (as NAT-039 did). Native: indirect only, through PHY_CONFIG0 bits 2/14/15 (`ana/pcs/pma_pwr_stable`, `snps-usbdp-con-reg.h:87-`) after `ana_pwr_en`, then S10 and S13. HS working proves only the eUSB2 rails. If the SS rails are off, SS needs a separate PMIC decision; this plan does not include one |
| U7 | Can PERIC2 GPIO (`0x11830000`) be read at loader entry (clock and power of PERIC2)? | S2; a read of an unclocked block can stall the bus | native probe, done last and after the log ring is drained; Android has no read-only value path without debugfs (the sysfs attribute in U2 gives the driver's sample, which is enough for U2) |
| U8 | Does S-Boot's Download Mode ever use SS? Upload mode was HS 480 Mbps (`artifacts/recovery-qualification/attempt-001/lsusb-04e8-685d-sec-upload.txt`) | if it did, some S-Boot state might be reusable | host only, read-only: `lsusb -t` and `lsusb -v -d 04e8:685d \| grep -i speed` the next time the phone is in Download Mode for a restore |
| U9 | Is the current 16 MB/s link-bound or engine-bound? | if the polled engine is the limit, SS gains little until the engine changes | host test or simulator: time per TRB and per poll in the NAT-076 engine. HS bulk can practically reach more than twice 16 MB/s (**inferred**, a general figure, not measured here) |
| U10 | The GPL-2.0 header on `snps-usbdp-ram-code.h` covers 6144 firmware words | embedding them in the loader is a licensing decision, not a technical one | owner/project decision under AGENTS.md (preserve component licenses) |
| U11 | `samsung,no-extra-delay` (DT, `s5e9945-usb.dtsi:49`) and the driver key `exynos,no_extra_delay` (`dwc3-exynos.c:998`) do not match, so Android probably runs without `GUCTL.NOEXTRDL` (**inferred**) | small; follow Android (do not set it) | none needed; a native GUCTL read in the probe confirms the reset value |
| U12 | How long does this host take to fall back to HS, if it falls back at all, when SS fails? | sets `T_SS` | measured by the P1 trace of the first SS run |

## 5. Effort, risk, and the recommended first native experiment

**Effort (host work, separate tasks).** No dates are promised.

1. An SS rung generated from the vendor sources the same way NAT-045 `derive.py` does: S1-S17, about 60 MMIO operations,
   the CR-port protocol and the 6144-entry table, plus model tests.
2. Engine SS support: BOS and SS descriptors, MPS 1024 with burst and companion descriptors, SET_SEL/SET_ISOCH_DELAY, the
   U1/U2 rejects, and host collector support for both buses.
3. The fallback state machine with fault injection in the NAT-045 platform model.
4. The read-only probe below.

Item 1 is about the size of NAT-040 + NAT-045; item 2 is about the size of NAT-076.

**Safety risk: low to moderate.** The writes stay inside the HSI0 USB block and the DWC3 window, plus one PMU isolation bit
(`0x12860620`, the same kind of bit as the `0x1286061c` the USB2 ladder already writes). There are no PMIC writes, no
partitions, no boot chain changes and no intentional reboot. The failure modes are:

- a bus stall on an unclocked APB read (bounded by the loader's existing watchdog and autonomous return; probe order below);
- SS PHY init timeouts (handled by P0);
- an untrained link (handled by FORCED);
- a confused host port, which at worst needs a replug.

**Success risk: high uncertainty for the first SS attempt** (U2, U4, U5, U6).

**Benefit.** Gen1 raises the line rate tenfold, but the gain from the polled engine is unknown until U9 is answered.

**Recommended minimal first native experiment: a read-only SS prerequisite probe.** Add it after the HS link is up (after
L8), so the values travel over the proven HS log. It performs no writes. Each read is logged, and before every read marked
risky the ring is drained to the host. The order goes from known-clocked to unknown:

1. PMU (always on): `0x1286061c`, `0x12860620`.
2. DWC3 (clocked, HS running): `0x1790c1a0` VER_NUMBER, `0x1790c1a4` VER_TYPE, `0x1790c14c` GHWPARAMS3 (raw),
   `0x1790c2c0` GUSB3PIPECTL, `0x1790c12c` GUCTL, `0x1790c11c` GUCTL1, `0x1790d020` LSKIPFREQ, `0x1790d024` LLUCTL,
   `0x1790d060..0x1790d06c`, `0x1790c70c` DSTS.
3. USBCON (clocked): `0x178a0000` VERSION, `0x178a0004`, `0x178a000c`, `0x178a0014`, `0x178a0080` LTSTATE_HIS, `0x178a0114`.
4. CMU_HSI0 (read by L3 already): `0x17802058`, `0x1780205c`, `0x17802060`, `0x17803064`, `0x1780305c`, `0x17807064` (DBG_NFO QCH_S_TCA).
5. *Risky:* USBDP ctrl `0x178d0000`, `0x178d0004`, `0x178d0008`, `0x178d000c`, `0x178d0100`, `0x178d0108`, `0x178d0110`,
   `0x178d016c`, `0x178d0234`, `0x178d0238`. Plain MMIO reads only. No CR-port read, because a CR read writes CON0/CON1.
6. *Risky:* TCA `0x178e0000`-`0x178e0034`, `0x178e00fc` (INFO `version_id`).
7. *Risky, last:* GPIO `0x118301a0` (CON), `0x118301a4` (DAT).

This resolves U4, U5, U7 and U11, and gives the raw S-Boot values for U6's indirect check. It decides whether S19 has an
LLUCTL branch and whether S2 can read the orientation. With these values, and with U1-U3 from Android, the next decision
is a single SS attempt with the section 3 fallback. That run would also measure U12.

## Files

| file | role |
|---|---|
| `README.md` | this plan |
| `cites.tsv` | the 204 `file:line:text` citations at the pin |
| `check_cites.py` | checks every citation with `git show <pin>:<file>`; exit 0 = all hold |
| `evidence.json` | the task's evidence record |
| `task.json` | task card (generated by the registry) |
