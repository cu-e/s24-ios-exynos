# STR-004 coherent E1S source preparation

Owner codex-e1s-profile-20261106-sr4; source-only host work in the separate
str-004-e1s-profile worktree. STR-003 depends on accepted STR-002. Both are done.
The existing tools/build/prepare_xnu.py now emits e1s-profile.json after its
normal source copy and patch application. There is no alternate build system.
The optional --root selects MAIN's pinned references; output stays in this
worktree's artifacts/xnu-prepare/RUN. Local patches and profile pins come from
this worktree. No shared references or old artifact tree may be changed.

Register E1SPROFILE-001 before verification. First run the bounded actual-source
controls from controls.py against the accepted source preparation. Then run the
existing preparer once with --root MAIN --run e1s-profile-001. Capture exact
commands/exit codes, fresh process peak RSS, actual profile/report/source/patch
hashes. This is Python/Git/source copying only: no compiler, target, packer,
SDK generation, common check or phone operation. Use finite timeout and one
source process at a time; stop on failure and preserve the new output directory.

Controls must reject a wrong machine revision, missing/wrong E1S header,
changed source topology, altered STM or loader-memory patch and ordered patch
provenance changes. They use copied actual pinned source bodies and positive
coherence across the donor ADT table, loader GIC declarations and prepared
E1S header. The source profile deliberately records configuration as unselected
and physical RAM/live CPU/CNTFRQ as unknown. Later consumer code must select a
real configuration and regenerate coherent E1S headers/types/archives.

The compatible current57d0 witness covers selected loader/FDT bytes only.
New UART/watchdog patches are not selected automatically. The original selected
c886 patch series, Apple c54 base, local STM correction and accepted23b31 loader
memory correction are hash-bound. No ABI/export deletion or native provider
qualification follows from successful source preparation.
