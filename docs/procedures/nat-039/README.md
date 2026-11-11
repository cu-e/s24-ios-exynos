# NAT-039: read-only inventory of the live USB stack (SM-S921B, running Android)

Evidence category: **android-userland**. A read-only measurement on this S24 (device tree, sysfs, procfs through `adb shell su -c`). It says
what the running Android has; it says nothing about the state the loader finds on the RECOVERY path.

Date: 2026-11-11. Device: SM-S921B / e1s, firmware S921BXXS9BYH3, kernel 6.1.93-android14-11, `getenforce` = Enforcing, `sys.usb.config` = adb
(phone enumerated by the host, UDC `configured`).

## What ran

* `capture.py` runs 51 commands as root, each one a read (`ls`, `cat`, `grep`, `find` without actions, `od`, `readlink`, `dmesg`, `logcat -d`
  filtered). Before the first adb call every command is checked against a deny-list (`>` except `2>&1` and `2>/dev/null`, `tee`, `setprop`,
  `settings put`, `mount`, `insmod`, `dd`, `rm`, `mv`, `cp`, `kill`, `reboot`, `am`, `pm`, `cmd`, `start`/`stop`, `devmem`, `busybox`, shells
  and interpreters, `find -exec/-delete/-fprint`). The only adb verbs are `get-state` and `shell su -c '<one command>'`. This is a safety
  net; the reading of `COMMANDS` is the control. `test_nat039.py` proves the list passes, 36 write-like commands are refused, and nothing
  else reaches adb.
* Nothing was mounted, written, started or stopped. `debugfs` is registered in `/proc/filesystems` but **not mounted** on this phone, and I did
  not mount it: that would be a state change on the phone with a hang risk in `clk_summary` (clock rate recalculation can read CMU registers),
  and Android's own state is not what NAT-043 needs. No register was read (no `devmem`, no debugfs `regdump`).
* Four captures were taken while the command list grew: capture-001 (28 commands), 002 (42), 003 (49), 004 (51). **capture-004 is the evidence
  run**; it contains every earlier command. Raw files stay in `artifacts/nat-039/` (git-ignored); they were scanned for the device serial,
  MAC-like strings and 14-16 digit numbers (none). After the run the deny-list was tightened (`python3` was not caught, and the default
  argument bound the command list at import); the command set is unchanged, and `manifest.json` carries `commands_sha256`, which the test
  compares with the script's current list.
* `compare.py extract` writes `capture-extract/`: the 30 raw files the comparison reads (regulator list cut to the four USB rails), plus
  `manifest.json` with the SHA-256 of each raw file. `compare.py compare` checks the extract against the NAT-040 plan (`plan.json`,
  `README.md`). Every expectation is anchored: the cited plan step must contain the value, otherwise the comparison refuses to run.

Reproduce without a phone: `python3 -I docs/procedures/nat-039/compare.py compare --capture docs/procedures/nat-039/capture-extract`
(exit 0 = no mismatch). Tests: `python3 -I docs/procedures/nat-039/test_nat039.py` (56 tests).

## Result: 39 rows, 0 mismatches

20 match, 4 consistent, 13 new, 2 unresolved (`comparison.json` has every row with its expected and observed value and its source file).

| Fact the NAT-040 plan relies on | Result |
|---|---|
| DWC3 at `0x17900000`, window `0x10000`, SPI 403 (GIC hwirq 435 live) | confirmed; the kernel claims `0x1790c100-0x1790ffff`, so GSNPSID (`+0xc120`) is inside the mapped window |
| USBCON `0x178a0000`, eUSB2 control `0x178b0000`, eUSB2 PHY `0x178c0000`, USBDP `0x178d0000`, TCA `0x178e0000` | confirmed (one `phy@178A0000` node, five windows, all claimed) |
| SYSREG_HSI0 `0x17820000` | confirmed (DT `reg`) |
| PMU `0x12860000`; pd_hsi0 window `0x12862000` (0x20); PMU USB isolation `+0x61c`, DP `+0x620` | confirmed |
| CMU_HSI0 `0x17800000` | confirmed as `pd_hsi0/cmu_id`; no platform device or iomem entry exists for it |
| CMU_TOP `0x22b20000` | confirmed (`clock-controller@22B20000`, window `0x8000`, `samsung,s5e9945-clock`); the three L2 read addresses lie inside it |
| DTZPC SMC register `need_smc = 0x17810204` | confirmed |
| repeaters TUSB2E11 `0x3e`, PTN3222 `0x4f` on `hsi2c` `0x110b0000` | confirmed (both `status = "okay"`, Linux bus 9, both drivers bound) |
| `maximum-speed = super-speed` in the board DT | confirmed |
| four rails `vdd075 s5_l2`, `vdd12 s4_l4`, `vdd18 l7`, `vdd33 l11` | rails exist and sit on the PMIC instances the names imply (`s2mps28-5`, `s2mps28-4`, `s2mps27`, `s2mps27`); the LDO index is not exposed by sysfs |

## What this resolves, and what it does not

* **U1 (supplies)**: in Android all four are `enabled` with one user each: `vdd075_usb` 0.75 V, `vdd12_usb` 1.2 V, `vdd18_usb` 1.8 V,
  `vdd33_usb` 3.1 V. The sysfs path puts them under `acpm_mfd_bus@...` PMICs, so the AP probably reaches them through the ACPM firmware
  rather than plain I2C (inferred from the device names, not verified). The loader-entry state is still U1 for NAT-043.
* **U2 (pd_hsi0)**: `need_smc` and the window are confirmed. The domain state is in debugfs (not mounted); the consumers `17900000.usb` and
  `17900000.dwc3` are `runtime_status = active`, so the domain is on in this Android state (an inference from the genpd contract, not a
  read). Loader-entry state: NAT-043 L1.
* **U3 (clocks)**: bases confirmed; **mux/gate/divider values and rates were not read** (no debugfs `clk_summary`, no register reads). The
  DT shows the clock indices the glue consumes (`aclk` 0x387, `sclk` 0x386, `bus` 0x388), which are vendor-driver table indices, not rates.
  Open: NAT-043 L2/L3 reads the registers natively.
* **U4 (repeater)**: both nodes are enabled and both drivers are bound, but both vendor probe functions (pin
  `417484173abc2c4fa93e738ea82ad9f2e84911b1`: `tusb2e11_repeater.c:299-357`, `ptn3222_repeater.c:254-302`) only parse the DT and register
  callbacks. No I2C transaction happens at probe, so **which repeater is fitted is not established** and the I2C bus was not touched.
  The DT tuning pairs (register, value) are recorded (TUSB2E11: `0x70=0x5d, 0x71=0x2e, 0x73=0x86, 0x79=0x40, 0x76=0x27`; PTN3222:
  `0x06=0x30, 0x07=0x21, 0x08=0x62, 0x09=0x02, 0x0a=0x00, 0x17=0x5d`, two reserved `0xff` entries).
* **U5 (DMA path)**: no `iommus`, `dma-coherent` or `dma-ranges` on the glue, the controller or the PHY (only an empty `ranges`), and no
  sysmmu in the 0x178x-0x179x region. Linux therefore treats the controller as un-translated and non-coherent, consistent with the plan
  placing the event buffer and TRBs in loader-owned non-cacheable memory. The S2MPU in front of HSI0 is secure-world state and is not visible
  from Android.
* **U6**: the live UDC is `configured` at `high-speed` against this host (maximum `super-speed`) with the combo PHY initialised by Android.
  That says nothing about HS-only operation with the USB3 PHY never initialised, and the reference clock rate was not readable.
* **U7**: `phy,gpio_phy_port = <0x65 1 0>`: pin 1 agrees with the plan; the bank behind phandle 0x65 was not resolved and the level was not
  read.
* **GSNPSID / IP id and PHY revision registers**: not read (no register reads from Android). The DT says `phy_version = 0x600`,
  `sub_phy_version = 0x801`; the controller IP id remains the first value NAT-043 logs.

## New facts for NAT-041/043/045

* The PHY tune tables (`hs_tune_phy`, `ss_tune`, phandles 0x4b1/0x4b2) are `status = "disabled"` in this DT and nearly every entry is the
  `0xff` sentinel; the vendor constants therefore come from the driver, not from the DT.
* Glue/controller properties the plan does not mention: `snps,dis-u1-entry-quirk`, `snps,dis-u2-entry-quirk`,
  `snps,dis-u2-freeclk-exists-quirk`, `snps,gfladj-refclk-lpm-sel-quirk`, `snps,has-lpm-erratum`, `snps,lpm-nyet-threshold = 0`,
  `exynos,force_gen1`, `exynos,adj-sof-accuracy`, `dr_mode = otg` with `usb-role-switch`; only `snps,quirk-frame-length-adjustment = 0x20`
  appears in the plan.
* Android's state at capture: role `b_peripheral`, `b_sess = 1`, Type-C `port0` with a partner, `usb_data_enabled = enabled`.

## Not established

Anything about the loader-entry state of the rails, domain, clocks or repeater (that is the native run); the register contents of CMU_TOP,
CMU_HSI0, SYSREG_HSI0, the USB block and the PHY; the controller IP id; the S2MPU; the I2C answer of either repeater. No native-device
evidence is claimed. Acceptance gap: the task text asks for `clk_summary` lines and a controller `regdump`; both live in debugfs, which is not
mounted. A follow-up (NAT-051) records the debugfs reads as a separately scoped, reverted-mount experiment.

## Files

* `capture.py`: the read-only capture (the command list is the specification).
* `compare.py`: `extract` (sanitized subset + manifest) and `compare` (39 rows against the NAT-040 plan).
* `capture-extract/`: the 30 sanitized files and `manifest.json`.
* `comparison.json`: the rows for capture-004.
* `test_nat039.py`: 56 host tests (capture safety 8, parsers 6, real-extract values 8, 18 change-detection cases, 8 plan-anchor cases, extract sanitizing 8).
* `evidence.json`.
