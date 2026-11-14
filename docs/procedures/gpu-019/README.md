# GPU-019: stock-binary values for the first GPU step, and who serves the S2MPU calls (source review)

**Evidence kind:** source-review of this phone's stock BYH3 binaries, with read-only device-tree reads in Android. Date: 2026-11-14.

Sources:
- the stock `vendor_boot` ramdisk 2 modules extracted in GPU-018 (`artifacts/gpu-018/run-001/vendor_boot/rd2/lib/modules`, gitignored),
  disassembled with the NDK llvm-objdump/readelf;
- the pinned source `references/s24-linux` 417484173abc;
- `/proc/device-tree` read as root.

Nothing was written on the phone.

## 1. The G3D power-domain sequence: the stock binary equals the source

The `struct pmucal_seq` tables were decoded from `cmupmucal.ko` (`.data`; 80-byte entries: type, name, base_pa, offset, mask, value,
cond_base_pa, cond_offset, cond_mask, cond_value). Types: 0 READ, 1 WRITE, 3 COND_WRITE, 6 WAIT.

| table | entries (stock binary) |
|---|---|
| `g3dcore_on` | (a) COND_WRITE 0x220D0004 [8:0] = 0x12 if [8:7] = 0; (b) COND_WRITE 0x220D0004 [8:0] = 0x8A if [8:7] = 1; (c) WAIT 0x220D0008 bit 1 = 1; (d) WAIT 0x12861E44 bit 0 = 1; (e) WRITE 0x22030844 bit 0 = 1 |
| `g3dcore_cmu_init` | WRITE 0x22031800 [4:0] = 2 (first power-on only) |
| `g3dcore_status` | READ 0x12861E44 bit 0 |
| `g3dcore_off` | WRITE 0x220D0004 [8:0] = 0x10; WAIT 0x220D0008 [1:0] = 0; WAIT 0x12861E44 bit 0 = 0 |

Every entry equals `flexpmu_cal_local_s5e9945.h` at the pinned SHA. The power domain is "local": direct MMIO, not through ACPM.

**Order** (`cal-if.c` `cal_pd_control` → `pmucal_local_enable`):
1. the `on` table;
2. on the first power-on, `exynos_pd_tz_restore(need_smc)` and then `cmu_init`; otherwise only `tz_restore`;
3. SCI/BTS/BCM sync hooks follow when those drivers are present.

## 2. DTZPC calls (`exynos-pd_el3.ko`)

- **`exynos_pd_tz_restore(id)`.** SMC **0x82000410** with x1 = 1, x2 = id (`need_smc` 0x22010204 for g3dcore, GPU-017's DT value),
  x3 = 2, x4..x7 = 0.
  - If a0 == 0, it calls `exynos_pd_restore_s2mpu(a1)`, which issues **HVC 0xC6000108**.
- **`exynos_pd_tz_save(id)`.** SMC **0x82000410** with x1 = 0, x2 = id, x3 = 2.
  - It then calls `exynos_pd_backup_s2mpu` (also HVC 0xC6000108).

## 3. Who serves the HVCs, and where SMCs go

`exynos-hypervisor.ko` is a pKVM protected module. Its `.hyp.text` is 4 KiB:

- **`__kvm_nvhe_exynos_hyp_hvc_handler`** calls a function pointer from `.hyp.bss`, which `exynos_hyp_plugin_init` installs. It contains
  no S2MPU logic itself.
- **`__kvm_nvhe_exynos_hyp_smc_trap_handler`** takes only SMC IDs 0x82002910 and 0x82002911 (`w0 + 0x7dffd6ee` ≥ 0xfffffffe) to the
  plugin. Every other SMC, including 0x82000410 and 0x82000520, goes on to EL3 unchanged.
- **The plugin.** The device tree has `exynos-hypervisor` with `memory_region` → reserved memory:

  | node | compatible | PA | size |
  |---|---|---|---|
  | `el2_code` | `"el2,uh"` | 0xC1400000 | 0x200000 |
  | `el2_earlymem` | `"el2,uh"` | 0x9FE400000 | 0x1C00000 |
  | `s2mpu_table` | `"exynos,s2mpu_table"` | 0xC5000000 | 0x1190000 |

  The S2MPU service is Samsung's EL2 micro-hypervisor **uH**, run inside pKVM through the plugin hook.

## What this means

- **The first native GPU step (roadmap G4/G5) has stock-traceable values throughout.** Every value comes from these binaries:
  1. `g3dcore_on`, then `g3dcore_cmu_init`;
  2. SMC 0x82000410(1, 0x22010204, 2);
  3. read-only ID/status registers;
  4. SMC 0x82000410(0, 0x22010204, 2);
  5. `g3dcore_off`.

  It skips the S2MPU HVCs, since there is no DMA in that step.
- **The SMCs go straight to EL3 in Android as well.** pKVM forwards them unchanged, so calling them from XNU at EL1 is the same request
  that EL3 sees under Android. That they are answered is still a hypothesis until it is measured.
- **The S2MPU HVCs (0xC6000108/110/111) are served by uH under pKVM.** XNU has neither. Firmware verify (0x110) and the stage-2 grant
  (0x111) are therefore not available on our system as they are. That is the owner-level piece G7.
  - Options: host uH (needs a pKVM-compatible EL2 environment), or program S2MPU G3D directly. The latter changes a DMA-protection unit
    and needs the owner's decision.
  - Whether EL3's RLC self-load (SMC 0x82000520) requires a prior uH verify is not in any source.

## 4. The first register to read after power-on: GRBM_CHIP_REVISION

- **The read.** `nbio_v2_3_get_chip_revision` in the stock `sgpu.ko` reads `reg_offset[GC][0][0] + 0xdc1` through
  `amdgpu_device_rreg`.
- **Its address.** The GC segment-0 base is `GC_BASE__INST0_SEG0` = 0x1260 (`vangogh_lite_ip_offset.h`, used by
  `vangogh_lite_reg_init.c`), so the register is dword 0x2021, byte offset 0x8084 in the `gpu` block: **PA 0x22208084**.
- **The expected value.** The stock device tree, `/proc/device-tree/sgpu@22200000/chip_revision`, holds **0x02600200**: MOD 0x60,
  EVT field 2 → EVT1.0. This phone therefore loads `vangogh_lite_unified_evt1.bin`. The driver warns if the register differs from this
  DT value (`nv.c` `amdgpu_get_grbm_chip_rev`).

A power-on whose read of 0x22208084 returns 0x02600200 shows three things: the domain is up, the GC registers are reachable from the
CPU, and it is this GPU.

## Still open

- The S2MPU G3D reset state.
- Whether S-Boot loads uH into 0xC1400000 on the RECOVERY boot path too.
- Whether EL3 answers SMC 0x82000410 from XNU: the native G5 run measures it.
