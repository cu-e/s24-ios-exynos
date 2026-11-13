# GPU-017: Xclipse 940 (SGPU) bring-up sequence in the pinned Samsung e1s kernel

Date: 2026-11-14. Evidence kind: **source-review** only. Nothing ran on the phone, and no native GPU result exists.

Source: `references/s24-linux` at 417484173abc2c4fa93e738ea82ad9f2e84911b1. The checkout is sparse, so most files were read with
`git show HEAD:<path>`. Config branches are resolved against `arch/arm64/configs/e1s_defconfig`:
- SGPU_EXYNOS=y (4958);
- SGPU_BUILTIN_FIRMWARE off (4955);
- EXYNOS_IMGLOADER=m (6725) and EXYNOS_S2MPU=m (6730). The driver guards them with `IS_ENABLED`, so the module builds count.

The review was drafted by a delegated reader. The owner of this task re-checked these citations at the pinned SHA:
- the firmware name (gfx_v10_0.c:343-346);
- SMC 0x82000520 (gfx_v10_0.c:376, 474, 5495);
- GPU IRQ 388 (dt-bindings s5e9945.h:420);
- `pd_g3dcore` (s5e9945-pm-domains.dtsi:117-126);
- the sgpu `reg` list (s5e9945-sgpu_common.dtsi:25-33);
- the `IS_ENABLED` branch selection (gfx_v10_0.c:350-384, 436-460).

Paths below use these prefixes: `D/` = `drivers/gpu/drm/samsung/gpu/sgpu/`, `DT/` = `arch/arm64/boot/dts/exynos/`, and
`PMU/` = `drivers/soc/samsung/cal-if/s5e9945/pmucal/flexpmu_cal_local_s5e9945.h`.

## Blocks

| Name | Base | Size |
| --- | --- | --- |
| gpu | 0x22200000 | 0x100000 |
| doorbell | 0x22300000 | 0x2000 |
| debug | 0x220F0000 | 0x40000 |
| pwrctl (BG3D_PWRCTL) | 0x220D0000 | 0x10000 |
| sysreg | 0x22000000 | 0x2000 |
| htu | 0x22040000 | 0x10000 |

Source: DT/s5e9945-sgpu_common.dtsi:25-33.

- Power domain `pd_g3dcore`: PMU 0x12861E40, cal_id 0xB1380009, need_smc 0x22010204, cmu 0x22030000.
- S2MPU G3D_S0: 0x22A50000.
- GPU interrupt: GIC SPI 388, level-high.
- The node is `dma-coherent`. There is no SysMMU; the GPU has its own VM, with GART in system RAM (`amdgpu_force_gtt=1`).

## Sequence, with the owner of each step

1. **Power domain on.** Kernel MMIO through PMUCAL `g3dcore_on` (PMU/:962-968):
   - BG3D_PWRCTL_CTL2 [8:0] = 0x12 or 0x8a, depending on bits [8:7];
   - wait for STATUS bit 1 (GPUPWRACK);
   - wait for PMU 0x12861E44 bit 0;
   - set 0x22030844 bit 0;
   - first-on CMU 0x22031800[4:0] = 2.

   Each wait has a 200 ms timeout. The reverse is `g3dcore_off` (PMU/:977-981).
2. **Secure restore.** SMC 0x82000410 (1, 0x22010204, 2), the DTZPC "prepare PD on/off", then HVC 0xC6000108 (S2MPU restore).
3. **Driver:** sysreg+0x8 = 6 (MGCG).
4. **Firmware.** One unified file, `sgpu/vangogh_lite_unified_evt%d.bin`, from /vendor/firmware:
   - It goes into a zeroed, cache-cleaned 0xE0000 DMA32 buffer.
   - HVC 0xC6000110 verifies the subsystem firmware ("G3D_TMR", idx 7).
   - HVC 0xC6000111 is the stage-2 grant to the AP.
   - **SMC 0x82000520(0,0,0)** does the RLC self-load. It has no symbolic name in the tree.
   - The driver then polls CP_STAT == 0 and RLC BOOTLOAD_COMPLETE.

   There are no separate RLC/ME/PFP/MEC files, and no SDMA or MES block (IP list: common, gmc, ih, gfx). The SMC
   0x82000520(0x10000, base, size) variant at :376/:474 belongs to the non-S2MPU build and is not the e1s path.
5. **GPU VM:** gfxhub VMID0 page table, aperture, TLB and L2. This is MMIO inside the GPU block.
6. **Rings:**
   - IH ring;
   - async GFX queues through direct HQD writes, compute MQDs, and ME/PFP unhalt;
   - submit by WPTR doorbell.

   The smallest proof that a packet executed is a scratch register set to 0xCAFEDEAD, then a WRITE_DATA of 0xDEADBEEF, polled by
   the CPU. No IRQ is needed. The fence is RELEASE_MEM → sequence number in memory plus an EOP interrupt.
7. **Clocks.** DVFS is ACPM IPC (`exynos_acpm_set_rate`); ACPM sets the PLL and the voltage. The lowest-risk choice is to stay at
   the boot frequency.

## What this means for the port

- The Xclipse cannot be started by kernel MMIO alone. The e1s path needs the secure monitor (SMC 0x82000410, 0x82000520) and an EL2
  that serves the S2MPU HVCs (0xC6000108/110/111).
  - Under Android that EL2 is pKVM or a raw HVC handler (`exynos-hyp.c:53-66`).
  - Whether those calls answer when XNU, not Linux, is running is **the** open question. It is not in the source.
- The firmware is a vendor blob from /vendor/firmware. It may be read on the phone for a native test, but it must not be committed.
- Risk classes for a future native run, each needing its own decision:
  - PMU and power-controller writes: a new class, reversible by `g3dcore_off`;
  - secure calls of unknown semantics: the 0x82000520 handler is opaque;
  - a stage-2 grant that is released only by another HVC.

  The GPU-internal MMIO is reversible.

## Gaps

None of the following is in the pinned source:
- the 0x82000520 handler and the firmware TOC;
- whether S-Boot leaves VDD_G3D (ACPM domain 45) on;
- which EL2 serves the HVCs without Linux;
- the real return values and order on this phone.

An android-userland read of the running SGPU driver's own logs would show the order and return values without new risk (dmesg lines
only; no debugfs clk_summary). Do it only if those lines are still in the ring.

## Next (proposed, not started)

1. GPU-018 (android-userland, read-only):
   - the firmware file names and sizes present under /vendor/firmware/sgpu (names and hashes only, not the blob);
   - dmesg SGPU init lines if any remain;
   - G3D power domain state from sysfs `power/runtime_status`.
2. Then a host decision plan for a first native "power domain on + read GPU ID register" run. That run touches PMU and makes secure
   calls, so it needs a concrete plan and the owner's decision, beyond decision 0052, which names only PMIC/ACPM LDO9/LDO18 operations.
