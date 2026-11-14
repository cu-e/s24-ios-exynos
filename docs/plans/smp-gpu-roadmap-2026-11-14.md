# SMP and Xclipse GPU: map of the remaining work (2026-11-14)

Owner direction, 2026-11-14:
- real additional CPU cores and Xclipse hardware acceleration, without lowering UI quality;
- no reduced resolution and no software-rendering substitutes for the blocked goal (NAT-193/194 withdrawn);
- classifier stops are not routed around;
- work that was stopped is split, the stopped piece is left alone, and the other pieces go ahead.

The reference build is `docs/reference-build.md` (scV, native resolution).

Legend:
- **done**: has evidence;
- **allowed now**: covered by decisions 0002/0044/0052/0061 and the registry;
- **STOPPED**: a safety-classifier stop, not resumed;
- **owner**: needs a new owner decision.

## SMP (several running cores)

| # | piece | state | evidence / what it needs |
|---|---|---|---|
| S1 | ADT topology: cpu1-9 `state="waiting"` | done | NAT-148/149: 10 CPUs registered |
| S2 | PSCI CPU_ON (SMC, `arm,psci-1.0`) for cpu1-9 | done | NAT-149: returns 0 for every core |
| S3 | Where the secondaries stop | done | NAT-153: they reach mark 6 (MMU on), but at **EL2** (CurrentEL 0x8); XNU's EL1 setup does not apply, and the first kernel-VA access fails |
| S4 | Why EL2 | done | S-Boot enters our loader at EL2 (NAT-022 ENTRY `0x8900`, two boots). Android boots at EL2 and becomes pKVM (`kvm-arm.mode=protected`, GPU-018). PSCI starts a core at the highest non-secure EL |
| S5 | The project's own EL2→EL1 sequence | done (exists, runs every boot) | the loader's `start.S` `from_el2`: HCR_EL2.RW, CNTHCTL_EL2 = 3, ICC_SRE_EL2 (SRE/Enable), CPTR_EL2 = 0, ELR/SPSR_EL2, `eret`; used on the boot CPU in every native run |
| S6 | Reading Linux's EL2 set-up constants (`init_el2`) | **STOPPED** (2026-11-14 ~00:2xZ, NAT-154) | not resumed and not needed: S5 is the project's own source |
| S7 | Read-only probe: on a secondary at EL2, record HCR_EL2, SCTLR_EL2, CNTHCTL_EL2, CNTVOFF_EL2, CPTR_EL2, MDCR_EL2, ICC_SRE_EL2, VBAR_EL2, MPIDR, then park in `wfe` | allowed now (host, then native under 0061) | system-register reads only; answers whether the firmware leaves EL2 state that the drop must handle |
| S8 | Secondary reset path: when CurrentEL == 2, run the S5 sequence and `eret` to the EL1 entry | allowed now as a narrow host task; **if the classifier stops it, it stays stopped** | same goal as NAT-154. It uses only the loader's own phone-proven code, never the S6 source. Gates: `check_loader_sites.py` rc 0 and `__TEXT_EXEC` page slack (1232 B left in scV, NAT-189) |
| S9 | Native run: cores at `arm_init_cpu`, `cpu_start`, the idle loop | allowed now (0061: CPU_ON runs need only the per-image decision) | criteria: running count > 1, no panic, timed return |
| S10 | XNU SMP function: IPIs (GIC SGIs), per-CPU timers, cluster topology (A520 / A720 / X4), `small_cores` policy | after S9 | host work plus native runs |
| S11 | Clocks of the other clusters through ACPM (stock FREQ_REQ per domain, as NAT-173 did for cpu0) | after S9 | stock parameters only |
| S12 | Measure: backboardd and the driver on different cores, frames per 5 s against the reference | after S10 | reference scV |

**Current blocker on the SMP line:** none that is external. S7 and S8 are the next pieces. S6 stays stopped.

## Xclipse 940 GPU

| # | piece | state | evidence / what it needs |
|---|---|---|---|
| G1 | Bring-up sequence from the pinned Samsung source | done | GPU-017: PMUCAL `g3dcore_on`, SMC 0x82000410, HVC 0xC6000108/110/111, SMC 0x82000520, gfxhub, rings |
| G2 | Inventory from Android and the stock BYH3 binaries | done | GPU-018: firmware in the vendor_boot ramdisk (`vangogh_lite_unified_evt0/1.bin`, 901120 B); call IDs confirmed in `sgpu.ko`, `exynos-pd_el3.ko`, `exynos-s2mpu.ko`; S2MPU HVCs served by pKVM + `exynos-hypervisor` |
| G3 | Stock-binary review of the power-on values | allowed now (host) | `g3dcore_on` register writes and waits in the stock `cmupmucal.ko`; the DTZPC SMC arguments in `exynos-pd_el3.ko`; the ID/status register offsets the stock `sgpu.ko` reads first |
| G4 | Kernel object `e1s_gpu`: power domain on → DTZPC restore → read GPU ID/status → DTZPC save → power off, with readbacks and 200 ms timeouts | allowed now (host, harness) | values from G3 only; no DMA, no firmware, no HVC |
| G5 | Native run of G4 | allowed under 0061 (stock values, reversible by `g3dcore_off` and reset) | per-image decision lists every register, value and call ID |
| G6 | What the S2MPU HVCs do at EL2 (`exynos-hypervisor.ko` hyp code; do they forward to EL3?) | allowed now (host review of stock binaries) | decides between EL2 code of our own and a direct path |
| G7 | EL2 service for 0xC6000108/110/111 under XNU | owner (design first) | it would be new EL2-resident code; the plan goes to the owner, and a classifier stop on it ends that piece |
| G8 | Firmware verify and RLC self-load (HVC 0xC6000110/111, SMC 0x82000520) | after G6/G7 | firmware read from the phone's own vendor_boot at run time, never committed |
| G9 | gfxhub VM, IH ring, one GFX queue, WRITE_DATA 0xDEADBEEF polled by the CPU | after G8 | MMIO inside the GPU block |
| G10 | Use for the UI | after G9 | see "the hard limit" below |
| — | Building or running downloaded GPU code (radv-xclipse Meson/Ninja, GPU-005) | **STOPPED** (2026-11-10, "Code from External") | needs an owner permission rule or `!` |

### The hard limit of the GPU line, stated plainly

iOS composes the UI through QuartzCore. On Apple hardware that renders through Metal and the AGX driver. Today backboardd falls back
to the CPU renderer (NAT-192).

Making QuartzCore itself use the Xclipse means a Metal-compatible driver stack for an RDNA2-class GPU behind Apple's userland interfaces.
That is a project far larger than G1–G9, and no evidence yet says it is reachable.

The realistic first use of a working GPU (G9) is in our own kernel driver:
- composition and scaling of the swapped surfaces;
- then, possibly, offloading specific CoreAnimation work.

No FPS outcome for G10 is promised.

## Other stopped lines (not resumed)

| line | stop | state |
|---|---|---|
| NAT-179 | 2026-11-14: writing the DPP1 hardware-scaling kernel code | no source, task or image exists; owner |
| NAT-136 | 2026-11-13 ~18:00Z: SuperSpeed USBDP isolation-release write (peek136.py) | uncommitted files left untouched; owner |
| NAT-193/194 | owner withdrawal 2026-11-14 (fbscale=2) | NAT-193 blocked with the record kept; decision 0079 deleted; nothing ran |

## Next pieces, in order

1. **G3 + G6.** Host review of the stock binaries: `cmupmucal.ko`, `exynos-pd_el3.ko`, `exynos-hypervisor.ko`, `sgpu.ko`.
2. **S7.** The read-only secondary EL2 register probe: host build, then native.
3. **S8.** The secondary EL2→EL1 drop from the loader's own sequence: host build, then native S9.
4. **G4.** The `e1s_gpu` power-on/ID-read object: host, then native G5.
