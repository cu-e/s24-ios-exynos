# NAT-145: scE, scD with all ten CPUs (host-test)

Purpose: frame rate. NAT-144 measured the software display path at about 16–17 frames per second during continuous activity. The
best steady 5 s window reached 21.7 frames per second, and half of the frame intervals were under 57 ms. All of this ran on a
single Cortex-A520: the image boots with `cpus=1` and the ADT publishes only `cpu0`. MiniIOMobileFramebuffer's copy/scale, backboardd,
SpringBoard's render server and every other process share that core (NAT-115 H2, NAT-120). scE gives XNU the other nine cores.

## What changes against scD (NAT-143)

| Part | scD | scE |
| --- | --- | --- |
| ADT `/cpus` | `cpu0` (reg 0) | `cpu0`–`cpu9`, made by `make_adt145.add_cpus` on the NAT-117 derived ADT; `cpu0`–`cpu3` carry `small-core` |
| cmdline | `... cpus=1 ...` | the same tokens without `cpus=1` (239 bytes); the build refuses `cpus=`/`cpumask=` |
| kernel, loader, root, md0, engine, window | NAT-143's | unchanged (same kernel `6aa8b6eb…d078`, loader_return_after 270, deadline 595, rec_secs 270) |

The CPU map comes from the donor's `tools/e1s/xnu/mkadt.py build(smp=True)` (`docs/e1s-smp.md`, "code ready, not device-tested"),
checked against the pinned Samsung DT (`references/s24-linux` 417484173abc, `s5e9945-cpu.dtsi:175-268`):
- `0x000`–`0x300`: Cortex-A520, cluster 0;
- `0x400`–`0x600`: Cortex-A720 low frequency, cluster 1;
- `0x700`–`0x800`: Cortex-A720 high frequency, cluster 2;
- `0x900`: Cortex-X4, cluster 3.

All cores use enable-method psci, and `/chosen/psci-method` is `smc`.

The test compares the cpu nodes with the donor's own output; phandles are fresh and unique. The loader passes `MPIDR_EL1 & 0xffff`
(NAT-036 patch) to `adt_set_boot_cpu_mpidr`, which leaves the table alone when a child already has that `reg`. NAT-144's kernel
reported `GenericARMCPU: cpu 0 (phys id 0x0) registered`, so cpu0's reg 0 matches.

Kernel side (HackiOS, already in the NAT-143 kernel; the strings were checked in `kernel.no-storage`):
- `iokit/Kernel/GenericARMPE.cpp` registers one GenericARMCPU per `/cpus` child. It runs the boot CPU and the big cores at once,
  then the `small-core` ones `small_cores_after` = 28 s later, and logs `N of M processors are running`.
- `osfmk/arm64/psci_smp.c` sends PSCI `CPU_ON` (SMC 0xC4000003) per core. It logs a refusal, a core that faults on entry or a core
  that never joins, and the system continues on the cores it has.
- Before the return to the loader, `psci_smp_stop_others()` sends every other core to `CPU_OFF` and waits for `AFFINITY_INFO` OFF.

## Build (host)

```sh
python3 -B docs/procedures/nat-145/build.py --out artifacts/nat-145/build-001 --loader-source artifacts/nat-020/build-003/source \
        --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-145/build-001 --out artifacts/nat-145/package-001
python3 -B docs/procedures/nat-145/derive146.py            # session_nat146.py, counted from session_nat144.py
python3 -B docs/procedures/nat-145/test_nat145.py
```

| Item | SHA-256 |
| --- | --- |
| RECOVERY image (100663296 B) | `ffa91748d09482c3f34de61ff0c6e2538001624cf963652157cbcb8cf71ec80f` |
| payload (26206640 B) | `4384cf08fc876a03f6ef5ff0b4224a7e4942fe7d8437819678e9171a4a054bb8` |
| loader Image | `c65dc2776032df714747bd554d384e020ad9f460bfbc4d2e29e9d3a9fa6c558b` |
| payload ADT | `0c109c99f586cdb74cf504b6d4f64b4f011bcbc970b6b4e6730f07b1135d9bb6` |
| session_nat146.py | `59a8002ffebe3f985450f9072701589589755548d7632f3ec682019d787ebb24` |

## Analyser (`analyze146.py`, rule fixed before the run)

It reports every NAT-144 verdict (`nat-143/analyze144.py`) plus the following:
- **cpus:** distinct `GenericARMCPU ... registered` and `cpu_start() cpu: N` lines, psci failure lines, init's `K cpu(s)` banner,
  and the last GenericARMPE running count.
- **verdict:** C2-all-ten (10 started, no failure, banner 10, running 10), C1-some (more than one started), or C0-one.
- **fps:** frames per window between consecutive MiniIOMobileFramebuffer statistics lines. `fps_best_window` is the best window with
  0 pauses and at least 20 frames; `fps_median_interval_ms` is the median of "half under N ms" over those windows. This is the rate
  at which frames reached the panel memory, as counted by the kernel, not a camera measurement.

On NAT-144's real text it gives C0-one, 1 cpu, running count 1 (the 28 s "slower cores" line also appears on one CPU), 8 steady
windows, best 21.72 frames/s (others 13.2–17.2), and a median "half under" of 57 ms. This is the baseline for NAT-146.

## Not established

- Whether the retail secure monitor accepts `CPU_ON` from this EL1 kernel, the power domains of the nine cores, the GIC doorbell,
  and whether the frame rate rises. The first boot with ten CPUs is the measurement (NAT-146).
- The native run needs an **owner decision**: PSCI `CPU_ON`/`CPU_OFF` are secure firmware calls that power CPU cores on and off.
  Android itself makes them at every boot and CPU hotplug, but decision 0052 names only PMIC/ACPM LDO9/LDO18.
