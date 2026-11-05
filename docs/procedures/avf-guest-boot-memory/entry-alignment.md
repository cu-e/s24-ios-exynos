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

The frozen correction is `7554b14d13040521e7f5f05ea8b856f76473ccb2`.
VMBOOTMEM-002 was registered before the focused run. Ten parser processes and
five actual CLI processes produced their expected results. All five entries
remain accepted by the original read-only parser. The corrected parser and CLI
accept0x800/0x804 and reject0x801/0x802/0x803 with the explicit alignment error
before any layout acceptance. Maximum measured case-process VmHWM was23444KiB;
the runner measured20408KiB. No source/tool witness changed during the run.

The scoped matrix is
`artifacts/avf-guest-boot-memory/entry-alignment-7554b14/matrix.json`, SHA256
`24e64d77be38f81a91a01edfa1c455a76c4e8cc3b19eeed99287a162415177e1`.
Maintained `entry-alignment-evidence.json` binds commands, exits, input/output
hashes and the original independent failing review capsule. The frozen
REV-031 finding is review-only commit `6d8a037`; its capsule SHA256 is
`aa1f3b0601d49318e326cd9225b6fe5b9b9762f65898c2d3490cafcda99daa86`.
Those failed/accepted historical reports are retained in their original paths.
