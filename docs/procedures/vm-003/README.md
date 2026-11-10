# VM-003 — isolated XNU guest on the S24: review of the measured VM-054 sessions (2026-11-10)

Evidence category: **android-userland**. This is an XNU guest under Android's KVM on the S24, not native XNU and not Exynos hardware access. Reviewer: `claude-takeover-20261110-6c8f`. Nothing was rerun on the phone for this review. The measurements were made on 2026-11-10 by `claude-xnu-s24-20261110-v54` (VM-054 sessions 001–004).

## The interface

VM-001 found no unprivileged VM interface on this firmware: no AVF feature or service, no `vm` tool, and `/dev/kvm` not accessible to the shell. The only available interface is `/dev/kvm` through the existing Magisk `su`, as qualified by VM-049–VM-052. That is root use under decision 0002 item 5. It involves no SELinux policy change, no new root installation and no settings change: every session runs from a task-owned RAM directory (`/dev/s24-vm054`), which is removed afterwards (`cleanup.absent: true`).

## What was measured (session 001, the plain run; 002–004 add debug features)

| Item | Observation |
|---|---|
| Guest | avfboot (35 176 B, SHA-256 `7b731000…90f9`), with an initrd payload of 16 557 208 B carrying the source-built HakiOS XNU kernel (payload kernel size 0xfc6338), ramdisk and cmdline. 1 vCPU pinned to CPU 9, 1 GiB RAM. |
| Guest output | 804 console bytes, captured verbatim in `stdout.txt`. avfboot reports its image/FDT/GIC/UART layout, the boot-args and `jumping to XNU at 0x834a3510`. **XNU itself printed nothing.** VM-054 found the first exception: EC=0x07 (FP access trap) at `_cpu_data_init`, before the console starts. |
| VMM events | Start, then end with cause `timeout` after 93.3 s. 1613 exits, all MMIO. Unknown MMIO 0. |
| Termination | Ended by the VMM's own 90 s timeout under an outer `timeout 105`. `vmm_gone: true`, the RAM directory was removed, and uptime went from 417 647.41 s to 417 743.39 s, so there was no reboot. Sessions 002–004 also ended by their own timeout or breakpoint, and none rebooted. |

## Assessment against VM-003

- **"Use an already accessible interface without policy or root changes."** Met, with the caveat above: the interface is root-only, and no policy or root configuration was changed.
- **"Capture actual guest output and verify termination."** Met. The guest's console output and the VMM's exit state are retained, and termination and the absence of a reboot were verified for each session.

## Not shown

XNU reaching its console, PID 1 or any user space (VM-054 is still open). Guest performance. Any Exynos device access by the guest.
