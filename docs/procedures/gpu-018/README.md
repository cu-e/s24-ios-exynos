# GPU-018: Xclipse 940 inventory from Android and the stock BYH3 binaries (android-userland, read-only)

**Evidence kind:** android-userland, plus a host read of the stock images backed up on 2026-11-10. Date: 2026-11-14.

Nothing was written on the phone. The reads were `ls`, `find`, `cat` of sysfs/procfs and `dmesg`, through `adb shell` and `su -c`.
debugfs was not touched, and clk_summary was not read.

The stock images read on the host:
- `devices/recovery/backups/2026-11-10/boot.img`, `a05a3c3b…`;
- `devices/recovery/backups/2026-11-10/vendor_boot.img`, `7d028e33…`.

Raw outputs and extracted binaries stay in the gitignored `artifacts/gpu-018/run-001/`. Nothing from them is committed except names,
sizes, hashes and call IDs.

## Results

### Firmware: in the vendor_boot ramdisk, not in /vendor/firmware

- `/vendor/firmware` has no GPU file (110 entries, listed as root).
- The kernel's `firmware_class.path=/vendor/firmware` is the fallback. The file the driver loads is in the first-stage vendor ramdisk
  (`vendor_boot`, ramdisk 1 of 2, legacy LZ4 + cpio) at `lib/firmware/sgpu/`:

  | file | size | SHA-256 |
  |---|---|---|
  | `vangogh_lite_unified_evt0.bin` | 901120 (0xDC000) | `b91d564835a3decf88ece824c73eeabc494026962a8982d71742ff1cb5f2ad2a` |
  | `vangogh_lite_unified_evt1.bin` | 901120 (0xDC000) | `c361847b65fe8f4b58ed4f10bcc573de40fd2cda37472161392aec844d8357ce` |

- The names match GPU-017's `sgpu/vangogh_lite_unified_evt%d.bin`. The size fits its 0xE0000 buffer.
- Which EVT revision this phone loads is not established. It would come from the chip ID or the driver's own log.

### The driver is a vendor module; the stock binaries confirm GPU-017's call IDs

- `sgpu` is a loadable module (`/proc/modules`: 1306624 B, 18 users). It is not in the GKI `Image`, which has no sgpu strings.
- `sgpu.ko` and the platform modules come from ramdisk 2 of `vendor_boot` (`lib/modules/`, 294 modules). They were disassembled with
  the NDK `llvm-objdump -dr`. Every `movk wN, #0x8200|#0xc600, lsl #16` was traced back to its `mov` and forward to the call:

  | module (SHA-256 prefix) | function | call |
  |---|---|---|
  | `sgpu.ko` (d2f234ab) | `gfx_v10_0_fw_init` | SMC **0x82000520** (x1..x7 = 0), `__arm_smccc_smc` |
  | `exynos-pd_el3.ko` (31d3bcf0) | `exynos_pd_tz_save`, `exynos_pd_tz_restore` | SMC **0x82000410** |
  | `exynos-s2mpu.ko` (2dc1e61d) | `exynos_pd_backup_s2mpu`, `exynos_pd_restore_s2mpu` | HVC **0xC6000108** (`exynos_hvc`) |
  | | `exynos_s2mpu_verify_subsystem_fw` | HVC **0xC6000110** |
  | | `exynos_s2mpu_request_fw_stage2_ap` / `release_…` | HVC **0xC6000111** / **0xC6000112** |
  | | others: set_stage2_ap 0x100, set_blocklist 0x101, set_all_blocklist 0x103, pd_bitmap 0x109, subsystem allowlist 0x113, probe 0x601, irq 0x602/0x603, init 0x081, test 0x121 | HVC 0xC6000xxx |
  | `exynos-hypervisor.ko` (2bde7f6f) | update_hcr_el2 0x082, fg_write_trap 0x083, set_cpu_context 0x085 | HVC 0xC6000xxx (`__arm_smccc_hvc`) |

  The SMC 0x82000520 call in the binary has all arguments zero, which matches GPU-017's e1s branch.

### Who answers the HVCs: Linux's own EL2 (pKVM)

- The stock command line has `kvm-arm.mode=protected` and `kvm-arm.protected_modules=exynos-hypervisor`.
- The device tree has `exynos-hypervisor` and 25 `pkvm-s2mpu@…` nodes, including `pkvm-s2mpu@22A50000`, the G3D S2MPU of GPU-017.
- PSCI is `arm,psci-1.0`, method `smc`; every CPU's enable-method is `psci`.

Consequence: under Android, the S2MPU HVCs (0xC6000108/110/111) are served by pKVM, Linux's own EL2 code, with Samsung's
`exynos-hypervisor` module loaded into it. Under XNU there is no pKVM. Those HVCs have no handler unless the project provides EL2 code
itself.

The loader is entered at EL2: NAT-022 ENTRY frame `0x8900`, two boots. Its `start.S` drops to EL1 before XNU. EL2 on the boot CPU is
therefore ours, and nothing is resident there after the `eret`.

### Power state in Android

- `22200000.sgpu`: runtime **suspended** (active 144 s, suspended 1811 s of uptime); devfreq `cur_freq` 0.
- The operating points are 1095000, 1000000, 900000, 800000, 700000, 650000, 600000, 545000, 500000, 450000, 400000, 350000, 315000 and
  252000 kHz.
- `/sys/kernel/gpu/gpu_model`: "Samsung Xclipse 940".
- `12861e40.pd_g3dcore` and `10090000.G3D` exist as platform devices (runtime PM unsupported on them).

The GPU is powered down when idle, so its power-on sequence runs many times a day on this phone.

### Init lines: no longer in the ring

The ring (1424 lines, from 1672 s of uptime) has only `[drm] [sgpu] MIN_REQUEST/MAX_REQUEST` DVFS lines. The probe order and return
values are not in it.

## What this establishes for a native GPU plan

1. **Stock-traceable values exist for every step up to the firmware.** Power domain (PMUCAL, GPU-017), DTZPC SMC 0x82000410 and the RLC
   SMC 0x82000520 are confirmed in this phone's own binaries.
2. **The S2MPU and firmware-verify HVCs need an EL2 service that XNU does not have.** A first native GPU step that needs no DMA:
   - power on;
   - DTZPC restore;
   - read the GPU's ID/status registers;
   - DTZPC save;
   - power off.

   It avoids those HVCs. Everything past it (firmware, rings) needs either EL2 code of our own that implements the S2MPU calls, or
   proof that the GPU can reach memory without them.
3. **SMP and GPU meet at EL2.** Both need EL2 work on our side: dropping secondaries to EL1, and possibly serving the S2MPU HVCs.

## Not established

- The EVT revision of this phone's GPU.
- The S2MPU G3D reset state (does it pass or block GPU DMA after power-on?).
- Whether EL3 accepts SMC 0x82000410 / 0x82000520 from NS-EL1 when no EL2 forwards them. In Android the host's SMCs pass through pKVM.
