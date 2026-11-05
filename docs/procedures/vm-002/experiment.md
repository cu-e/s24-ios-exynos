# VMHOST-001: selected XNU guest prerequisites and owned PID 1

Task: VM-002. Owner: codex-team-vm-20261105-am. Date: 2026-11-05.

Before running any build or guest, review the selected donor at
`a6f4bc38aa244359cd365c976244a88c9d6b3304` in the read-only primary
`references/scion-avf` checkout. Read its AVF README, launch scripts,
`xnuloader/mkpayload.py`, `userland/src/hello.c` and open-core Makefile targets.

1. Record the current checkout, donor commit and reviewed-file hashes.
2. Record host architecture and available emulator, compiler and linker paths.
   Read the existing kernel preflight without downloading SDKs or binaries.
3. Compile and link the owned raw-syscall PID 1 with existing host tools,
   one compiler job, with a 30-second timeout and 512 MiB address-space bound.
   Inspect the resulting arm64 Mach-O header and load commands. Compilation and
   linking do not establish that this program executed.
4. Prepare a host-only QEMU launch command that explicitly selects TCG on this
   x86_64 host, one vCPU, no devices/network/disks outside the required virtual
   machine, serial capture, and a process-owned finite timeout. Do not launch a
   guest without the coordinator's concrete resource lease and a qualified
   complete kernel, shim and payload.
5. Record missing inputs and their exact reasons. A missing emulator or complete
   kernel is a failed prerequisite, never evidence of an XNU guest reaching PID 1.

Resource ceiling for the preparation experiment: one compiler/linker at a time,
512 MiB address space, 30 seconds per command. No VM or heavy build is included.
No phone, ADB, root, MMIO, flash, reboot, global install or unrelated process
termination is part of this procedure. The unrelated Android emulator is excluded.

Acceptance remains an actual XNU guest reaching the owned program, with
`getpid() == 1`, `kern.ostype == Darwin`, captured console, and measured bounded
termination. Source review, generated commands, Mach-O files and host controls
are preparation only.
