# VM-052 — s24vmm boots avfboot on the S24

`src/vmm/` is a small KVM VMM for the S24, written for this project because the phone has /dev/kvm but no AVF service or crosvm (VM-001, VM-049). It runs as root through `su` from tmpfs (decision 0002) and reproduces the crosvm arm64 layout that avfboot (scion-avf `avf/shim`, pinned a6f4bc3) was written for:

| | Address |
|---|---|
| RAM | 0x80000000 + `--mem` MiB |
| Image (avfboot, PIE) | start of RAM, entered at EL1, MMU off, x0 = FDT |
| initrd (XNUP payload) | 16 MiB-aligned behind the Image |
| FDT | top of RAM minus 2 MiB |
| GICv3 (in-kernel vGIC) | GICD 0x3fff0000, GICR 0x20000 per vCPU below it |
| Console | ns16550a at 0x3f8, emulated, polled transmit |
| RTC | PL031 at 0x2000, emulated, host time |
| PSCI | KVM in-kernel, `hvc`; secondary vCPUs start powered off |

Every run is bounded by `--timeout` (the main thread kicks every vCPU out of KVM_RUN with `immediate_exit` + SIGUSR1 and joins them) and by an outer `timeout` in `docs/procedures/vm-052/run.py`, which also removes `/dev/s24-vm052` and checks uptime.

## Measured on the S24, 2026-11-10 (reports in `artifacts/vm-052/session-00N/`, local)

| Session | Guest | Result |
|---|---|---|
| 001 | avfboot, no initrd, 512 MiB, 1 vCPU (build-001) | avfboot banner, FDT parsed (RAM, RTC, GICD/GICR, vtimer INTID 27, PSCI hvc, UART), `FATAL: no initrd`, PSCI SYSTEM_OFF, VMM exit 0 |
| 002 | `b .` spin image, 2 vCPUs, 5 s timeout (build-001) | timeout fired at 5.1 s, then the VMM aborted (exit 134): bionic aborts `pthread_kill` on an exited thread. Kept as a failed run |
| 003 | as 001 with build-002 | same console as 001; VMM 0.02 s, exit 0 |
| 004 | spin, 2 vCPUs, 5 s (build-002) | `cause: timeout` at 5.16 s, exit 1 as designed, process gone |
| 005 | spin, 10 vCPUs, 5 s (build-002) | `cause: timeout` at 5.22 s, process gone |

avfboot's console, session 003:

```
avfboot: HakiOS XNU boot for crosvm/AVF and QEMU virt
avfboot: image 0x80000000-0x8001c000 fdt 0x9fe00000+0x488 EL0x1 MIDR 0x410fd801 CNTFRQ 0x186a000
avfboot: RAM 0x80000000-0xa0000000 initrd 0x0-0x0 RTC 0x2000
avfboot: GICD 0x3fff0000 GICR 0x3ffd0000+0x20000 vtimer INTID 0x1b PSCI hvc cpus 1 UART 0x3f8 ns16550a
avfboot: FATAL: no initrd: give the VM the XNUP payload (xnuloader/mkpayload.py) as its initrd
avfboot: powering off
```

avfboot was compiled from the pinned source with `src/vmm/avfboot/identity.h`, an authored placeholder of the same shape as `mkidentity.py --placeholder` (no Apple data); the upstream generator script was not executed. `src/vmm/check.py --run check-001` rebuilt a byte-identical VMM binary.

## Not established

- An XNU boot: no kernel payload was given. That needs VM-002's guest kernel.
- Interrupt-driven console input, virtio devices (block, input, GPU), a display path, or SMP with a guest that starts secondary CPUs.
