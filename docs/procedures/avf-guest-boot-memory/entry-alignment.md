# VM-026 ARM64 entry alignment correction

Original owner: `codex-guest-exec-20261106-dh`. Correction worktree:
`worktrees/vm-026-alignment-20261106`, branch
`team/vm-026-alignment-20261106`, starting at original tip
`a47a378dac38a0e86f6e7abd66c12f28390fa245`.

Independent REV-031 review found that the original Mach-O boundary accepted
LC_UNIXTHREAD program counters at text+0x801, +0x802 and +0x803. AArch64
instruction entry requires four-byte alignment. The correction rejects such
entries after the thread command is parsed and before executable-segment and
layout acceptance. It preserves the original physical tool, inputs, evidence
and procedure paths; the change exists only in this separate worktree.

Experiment VMBOOTMEM-002 exercises independently packed owned XNUP/Mach-O bytes
at offsets0x800 through0x804. Read-only baseline parser calls preserve the actual
historical acceptance. Corrected parser calls and actual corrected CLI processes
must accept aligned0x800/0x804 and reject0x801/0x802/0x803. Rejected CLI reports
must carry the alignment error and no layout acceptance. No compiler, QEMU,
header/source generation or common checks run. These are synthetic format
controls; no genuine kernel, runtime MMU or RAM qualification is claimed.

The focused runner is
`fixtures/public/avf-guest-boot-memory/entry-alignment-controls.py`. It writes a
fresh child of this worktree's task artifacts directory, records exact input,
code/tool/output hashes, actual commands/exits/time and current-process /proc
VmHWM for each controlled process. It leaves both baseline and correction
source witnesses unchanged. Independent reviewer recheck and integrator
acceptance remain required before task completion.
