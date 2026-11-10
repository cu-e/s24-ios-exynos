# VM-051 — a minimal KVM guest runs on the S24

Measured 2026-11-10 on the owner's SM-S921B (S921BXXS9BYH3, kernel 6.1.93-android14-11) through `su`, from tmpfs, under decision 0002 (bounded KVM experiments including a test VM). Report: `artifacts/vm-051/session-002/report.json` (local). Helper: `docs/procedures/vm-051/kvm_guest.c` + `guest.S`, static NDK r28c build `artifacts/vm-051/build-002/kvm_guest`.

The helper created a VM (IPA 40 bits), an in-kernel vGICv3 (distributor 0x08000000, redistributor 0x080a0000), one vCPU with PSCI 0.2 and a 2 MiB memslot at 0x80000000, ran the guest code at EL1 with the MMU off and got a PSCI SYSTEM_OFF exit (`KVM_EXIT_SYSTEM_EVENT`, type 1 = shutdown). An in-process 5 s alarm never fired. Three runs, one per CPU type, the vCPU thread pinned:

| Host CPU | Guest MIDR_EL1 | MMIO exit round trip | Guest loop, 1e8 iterations | Same loop natively (best of 4) |
|---|---|---|---|---|
| 0 (Cortex-A520) | 0x410fd801 | 10.0 µs | 83.4 ms | 77.4 ms (runs 77-106) |
| 4 (Cortex-A720) | 0x410fd811 | 4.0 µs | 38.7 ms | 38.8 ms |
| 9 (Cortex-X4) | 0x410fd821 | 3.0 µs | 34.9 ms | 31.4 ms (runs 31-57) |

All three: console bytes "Hi" via MMIO, PSCI_VERSION = 0x10001 (PSCI 1.1), CurrentEL = EL1, MPIDR 0x80000000, CNTFRQ_EL0 = 25.6 MHz, no unexpected MMIO address. Uptime grew across the session (no reboot) and `/dev/s24-vm051` was removed and confirmed absent.

Session 001 is retained as a failed measurement of my own guest code: KVM's PSCI handler returns SMCCC results in x0-x3, which zeroed my base register x1 after the first `hvc`, so later reports went to address 0+offset. Session 002 keeps the base in x19.

## What this establishes

- Root-run KVM on this phone creates VMs with an in-kernel GICv3, runs guest code at EL1 and implements PSCI 1.1 including SYSTEM_OFF, on all three core types.
- Guest compute speed matches native speed for a register-only loop; the native spread comes from frequency scaling, not virtualization.
- A trap to the userspace VMM costs about 3-10 µs, so a VMM should keep hot device paths (console, virtio notifications) cheap or use ioeventfd/irqfd.

## What it does not establish

- Anything about XNU as a guest, stage-2 behaviour with large memory, interrupts delivered to a guest, multiple vCPUs, or the stability of long runs.
- That an Android app can open /dev/kvm: the helper ran as root (Magisk context); VM-001 found the shell user cannot.
