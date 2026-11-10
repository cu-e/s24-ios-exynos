# NAT-005: E1S boot ABI as measured on the owner's S24

Recorded 2026-11-10 from a normal Android boot, read-only through `su` (decision 0002, item 4). Raw blobs stay in the git-ignored `devices/e1s-fdt/2026-11-10/`. They can carry identifiers and are summarized here, not published.

| Blob | Bytes | SHA-256 |
|---|---:|---|
| `/sys/firmware/fdt` (what S-Boot passed this boot) | 762,424 | `95fa811abca3f5f8889705add485f94c4490c57a853bded10539d4631bef46c3` (equal to `sha256sum` on the phone) |
| vendor_boot DTB section | 433,300 | `9b77987a324b1cdb93c8…` |
| recovery image DTB section | 433,300 | identical to the vendor_boot DTB |

Parser: [`tools/verify/fdt_facts.py`](../../../tools/verify/fdt_facts.py), tested by `tests/test_fdt_facts.py` with an independent FDT writer. It prints the names of `/chosen` properties and bootargs keys, never their values. The few values quoted below were selected by hand and identify nothing.

## Measured (normal boot)

- **RAM.** S-Boot injects seven `/memory` nodes; the vendor_boot DTB has none:
  - `0x80000000` + `0x36900000`
  - `0xc0400000` + `0x2400000`
  - `0xc2b00000` + `0x1d500000`
  - `0xe0100000` + `0x1ff00000`
  - `0x880000000`, `0x900000000` and `0x980000000`, each + `0x80000000`

  That totals about 7.9 GiB. The low banks leave holes at `0xb6900000`–`0xc0400000`, `0xc2800000`–`0xc2b00000` and `0xe0000000`–`0xe0100000`.
- **Reservations.** There are 47 `/reserved-memory` nodes. S-Boot adds `el2_code` (`el2,uh`, `0xc1400000` + 2 MiB), `el2_earlymem` (`0x9fe400000` + `0x1c00000`), `kaslr`, `sec_debug_next` (`0x91200000` + 2 MiB, `no-map`) and `wifi_region`, and shrinks `log_s2d`, `log_platform` and `s2mpu_table`. The modem uses `cp_rmem` (`0x880000000` + `0xd800000`) and `cp_rmem1` (`0x890000000` + `0x1df00000`).
- **Boot framebuffer.** The bootargs contain `s3cfb.bootloaderfb=0xfa200000`. No reservation node covers it: `0xFA200000` lies inside `/memory@e0100000`.
- **Panel.** All `e1s_panel_display_modes` are 1080×2340. Path: DSIM0 `0x190B0000` (DSIM1 disabled), DECON0 `0x19100000`. `lcdtype` / `mcd-panel.boot_panel_id` = `10551316`.
- **GIC.** GICv3: GICD `0x10200000` + 64 KiB, GICR `0x10240000` + `0x140000` (10 × 128 KiB).
- **Timer.** `arm,armv8-timer` with `clock-frequency` 25,600,000.
- **CPUs.** 10, MPIDR `0x000`…`0x900` (Aff1 = index); PSCI 1.0 via `smc`.
- **Touch.** `stm,stm_ts_spi` at `/spi@11090000/touchscreen@0`, status ok.
- **Watchdogs.** `watchdog_cl0@10040000` (`samsung,s5e9945-v1-wdt`) and `watchdog_cl1@10050000` (`v2`). Bootargs `s3c2410_wdt.tmr_atboot=1`, `nowatchdog`, `sec_debug.level=0`, `sec_debug_mode.force_upload=0x0`.
- **Placement.** In this boot S-Boot put the initrd at `0x85100000`–`0x864ef90c`. `/proc/iomem` shows Linux "Kernel code" at `0x800f0000`.

## Upstream assumptions checked

| Assumption (s24-port / Mu-Silicium) | Result |
|---|---|
| Framebuffer base `0xFA200000` | **Confirmed** for a normal boot by `s3cfb.bootloaderfb` |
| Framebuffer 1080×2340 | **Confirmed** resolution; 32 bpp, stride and pixel format are **not determinable** from the DT |
| Framebuffer size `0x9A4000` (1080×2340×4) | Consistent; not stated anywhere by S-Boot |
| Framebuffer is a reserved region | **Contradicted**: it is ordinary `/memory`, so the loader must exclude it from XNU's RAM window itself |
| S-Boot injects `/memory` | **Confirmed** |
| GICD `0x10200000`, GICR `0x10240000` | **Confirmed** |
| Log at `0x91200000` | That address is Samsung's own `sec_debug_next` region (`no-map`). Writing there overwrites Samsung debug state that Android reads on its next boot; the effect is unknown |
| Kernel loaded at DRAM base | **Inference**: "Kernel code" at `0x800f0000` is consistent with an Image at `0x80000000` plus head text |
| Entry at EL1, MMU off, `x0` = DTB | **Not determinable** from Android. `el2_code`/`uh` shows an EL2 component exists, so EL1 entry is plausible, not proven |
| CNTFRQ_EL0 at entry | **Not determinable**; the DT supplies 25.6 MHz |

## Not established

- What S-Boot changes in the DT when it boots **recovery** rather than BOOT. The recovery image carries the same base DTB; the fixups were observed only for a normal boot.
- Whether the hardware watchdog is running when S-Boot hands over, and what a watchdog reset leads to (normal boot, recovery again, or upload mode). `sec_debug.level=0` and `force_upload=0` make upload mode less likely; that is not an observation.
- The framebuffer's pixel format and stride. They live in the DECON/DPP window registers and can only be read natively.
- Whether the vendor_boot DTB section holds more than one DTB. Only the first was parsed.
