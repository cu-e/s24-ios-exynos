# VM-049 — KVM capabilities on the S24 as root

Measured 2026-11-10 on the owner's SM-S921B (S921BXXS9BYH3, kernel 6.1.93-android14-11) through `su` (Magisk), from a tmpfs directory that was removed afterwards. Authorized by decision 0002. Only the system file descriptor of /dev/kvm was used: KVM_GET_API_VERSION, KVM_GET_VCPU_MMAP_SIZE and KVM_CHECK_EXTENSION. No VM or vCPU was created. Report: `artifacts/vm-049/session-001/report.json` (local, not in Git).

| Query | Answer |
|---|---|
| API version | 12 |
| vCPU mmap size | 8192 bytes |
| NR_VCPUS / MAX_VCPUS / MAX_VCPU_ID | 10 / 512 / 512 |
| ARM_VM_IPA_SIZE | 40 bits |
| ARM_PSCI / ARM_PSCI_0_2 | 1 / 1 |
| ARM_PMU_V3, ARM_SVE, ARM_PTRAUTH_ADDRESS, ARM_PTRAUTH_GENERIC | 1, 1, 1, 1 |
| ARM_MTE, ARM_EL1_32BIT, PMU_CAPABILITY | 0, 0, 0 |
| IRQCHIP, DEVICE_CTRL, ONE_REG, IRQFD, IOEVENTFD, SIGNAL_MSI, READONLY_MEM, IMMEDIATE_EXIT | all 1 |
| IRQ_ROUTING | 4096 |
| NR_MEMSLOTS | 32767 |
| ARM_NISV_TO_USER, ARM_INJECT_SERROR_ESR, ARM_INJECT_EXT_DABT, ARM_SYSTEM_SUSPEND | all 1 |
| MSI_DEVID on the system fd | EINVAL (it is a per-VM capability on arm64; not answered here) |
| Android KVM_CAP_ARM_PROTECTED_VM (0xffbadab1) | 0 |

## What this establishes

- The kernel runs non-protected KVM with the features a VMM such as kvmtool or crosvm expects: in-kernel irqchip (device control for vGIC), PSCI 0.2, a 40-bit IPA space, PMU, SVE and pointer authentication.
- Protected VMs are not offered. This matches VM-001: no AVF service, no `vm` binary, and empty `ro.boot.hypervisor.*` properties. A guest therefore needs a VMM run as root, not AVF.

## What it does not establish

- Whether KVM_CREATE_VM, vGICv3 creation and KVM_RUN work on this kernel. Capability answers are static. VM-051 measures that.
- Anything about an XNU guest.
