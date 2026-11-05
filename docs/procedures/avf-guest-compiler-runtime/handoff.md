# VM-023 handoff

Owner `codex-guest-exec-20261106-de`; branch `team/vm-023-20261106`;
worktree `/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-023-20261106`.

Implementation commit: `0e44b04` (full ID in evidence.json).

The scoped tool validates genuine accepted cc_kext bytes/provenance and the
actual guest-target driver resource lookup without rebuilding the runtime.
It reuses the pinned `xnu_cc_kext.py` Mach-O/archive parser. The common VM-009
executor is not duplicated or edited.

The final run passed: all 287 members and recipe/source witnesses match;
47 external imports remain explicit; all 1080 immutable guest templates retain
the guest target and exclude the runtime resource root from compile headers.
Two actual compiler `-###` commands select the exact accepted archive with the
positive resource root and omit it with an absent resource root. Both exit zero.
No cc1/assembler/linker/build/QEMU output is executed or produced. Each final
driver group has no remaining process.

Existing evidence is under this worktree's
`artifacts/avf-guest-compiler-runtime/{prepare-1,prepare-2,driver-1,driver-2,final-0e44b04}`;
the indexed English evidence retains exact commands, exit codes, timestamps,
source/tool/output hashes, failed attempts and current-image `/proc` HWM.
See README.md for reproduction, admission, measured memory and limitations.

Next: an independent reviewer inspects the scoped implementation and measured
positive/negative outputs. The kernel integrator may then publish the scoped
commits and run common checks under MAIN/state/.integration.lock. The original
owner keeps VM-023 open until independent review and integrator acceptance.
Actual full guest link/archive member selection/closure remains separate.
Do not substitute this tiny lookup recipe for the genuine DEVELOPMENT link.
