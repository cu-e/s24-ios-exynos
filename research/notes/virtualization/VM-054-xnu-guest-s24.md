# VM-054: the source-built XNU guest reaches PID 1 on the S24 under s24vmm

Date: 2026-11-10. Evidence: `docs/procedures/vm-054/evidence.json`.

What this is: xnu-8796.121.2 DEVELOPMENT (BCM2837 configuration, scion-avf a6f4bc3), built from source
in VM-002, boots under the avfboot shim as a guest of s24vmm. s24vmm runs as root from tmpfs on
Android KVM on the owner's SM-S921B (S921BXXS9BYH3). It reaches the project's own static PID 1
and powers off with PSCI SYSTEM_OFF.

What this is not:
- not native XNU on Exynos hardware: no Exynos device is touched, the guest sees a virtual GICv3,
  timer, 8250 UART and PL031;
- not Apple's launchd: PID 1 is the VM-002 test binary at `/sbin/launchd`.

## Result

| run | vCPU host core | `--fp-on` | end | VMM seconds | Darwin banner | PID 1 line |
|---|---|---|---|---|---|---|
| session-005-fpon | 9 (X4) | yes | PSCI SYSTEM_OFF | 0.288 | yes | yes |
| session-006-control | 9 (X4) | no | timeout (20 s) | 20.507 | no | no |
| session-007-fpon | 9 (X4) | yes | PSCI SYSTEM_OFF | 0.300 | yes | yes |
| session-008-fpon-cpu4 | 4 (A720) | yes | PSCI SYSTEM_OFF | 0.349 | yes | yes |
| session-009-fpon-cpu0 | 0 (A520) | yes | PSCI SYSTEM_OFF | 0.670 | yes | yes |

- Console lines: `Darwin Kernel Version 22.5.0 ... xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837`,
  then `VM002: pid=1 ostype=Darwin owned-entry=v2`, then `avf: halt (PSCI SYSTEM_OFF)`.
- About 15,030 VM exits per run, nearly all UART MMIO; no unknown MMIO.
- Every run:
  - removed `/dev/s24-vm054` (checked absent);
  - left no s24vmm process;
  - left device uptime increasing, so the phone did not reboot.

## The blocker and its cause

Sessions 002-004 stopped at XNU's first FP instruction: `fmov d0, xzr` in `_cpu_data_init`, ESR
0x1fe00000. This happened although the guest's CPACR_EL1 read 0x300000 (FPEN = 0b11). The later
SP1 recursion and translation faults are fallout of that first trap.

XNU enables FP in `common_start` with `msr CPACR_EL1, x0` and no ISB (xnu c54f35ca,
`osfmk/arm64/start.s:762-763`). Nothing synchronizes context before `arm_init` calls
`cpu_data_init` (`osfmk/arm/arm_init.c:357`). The architecture allows the old FPEN value to apply
until a context synchronization event.

`fp_sync_probe.S` measured this in a guest on each core type (`fp-sync-cpu{0,4,9}`):

- An `fmov` right after an unsynchronized FPEN 00→11 write traps on A520, A720 and X4.
- After about a million ALU instructions it still traps on A520 and X4.
- With an ISB after the write, it never traps.
- An intervening MDSCR_EL1 access, which KVM traps, synchronizes context and hides the effect.

Fix used here: VM-055's `s24vmm --fp-on` starts the boot vCPU with FPEN = 0b11, as firmware leaves
it. Control session-006 (same VMM, no `--fp-on`) still hangs.

## Open

- SMP: KVM resets PSCI CPU_ON secondaries, so their `common_start` would hit the same trap. A fix
  belongs in avfboot's CPU_ON entry (CPACR plus ISB) or in XNU (an ISB after the write).
- The SCFB display and virtio-input paths (VM-053) were not exercised; these runs had no `--scfb`
  or `--input`.
