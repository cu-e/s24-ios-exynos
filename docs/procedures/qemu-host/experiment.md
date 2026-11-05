# QEMUHOST-001: pinned generic ARM64 host tool

Date: 2026-11-05. Owner: codex-team-qemu-host-20261105-au. Task: VM-004.

Acquire the official QEMU 10.2.0 source release from
`https://download.qemu.org/qemu-10.2.0.tar.xz`. The primary upstream annotated
tag `v10.2.0` resolves to commit `698104725efad4b29079d857dfdebbd804e34c99`
(tag object `75eb8d57c6b9577c8121e28169c3512cfe2d2544`). Record the archive's
actual SHA256 before extraction/reuse and retain full source/component licenses.
Do not use rolling install/setup scripts, shared references or global installs.

Review configure/build code, dependency manifests, license and ARM virt Kconfig.
Record existing GCC, Python, Meson, Ninja, GLib, pixman/zlib and required libfdt
provenance. Use bundled pinned source dependencies where the official archive
supplies them; disable automatic downloads. Select only aarch64-softmmu, virt,
TCG, PL011 serial, GICv3, PSCI and the minimum board-required devices. Disable
unneeded network, desktop, audio, display, guest agent, user emulation and tools.

The coordinator grants an exclusive heavy-build lease: maximum two compiler
jobs, approximately 2 GiB aggregate RSS, no other heavy builds. Record
MemAvailable, memory PSI and swap before/during each build command. Pause only
the owned build process group when MemAvailable falls below 4 GiB or sustained
memory pressure is detected. Resume only after the sampled resource condition
recovers. Enforce a finite build deadline with owned process-group termination;
never clear swap/drop caches or signal unrelated processes.

Inspect actual resulting ELF/binary hashes. Run the built executable's generic
machine/accelerator/device help: require virt, tcg and host-harness-compatible
serial/monitor/network options. Measure bounded termination using a stopped
empty machine (`-S`, no kernel, no disks/network) and owned timeout controls.
No guest OS, Linux substitute, XNU boot, phone/ADB, root, MMIO, flash or reboot
is part of this host-tool experiment. VM-002 remains blocked until separately
qualified actual XNU guest execution.

Record every command, exit, resource sample, source/tool/binary hash, failure,
local artifact path and tested commit. Hand off for coordinator review and main
checks; this task's source build is not evidence of a working native S24 port.
