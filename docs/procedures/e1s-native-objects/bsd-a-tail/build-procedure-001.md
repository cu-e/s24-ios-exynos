# STR040BUILD-001: remaining 61 native BSD-a objects

Compiles original `bsd-a[109:170]`, `bsd/apfs_deflate.o` through
`bsd/content_filter.o`, using the STR-039 caller `d1ecbfc1`. The only functional
change from the caller used by STR024BUILD-005 is the APFS resource operand.

- Manifest `fixtures/public/e1s-native-objects/bsd-a-tail/build-manifest-001.json`
- Source plan `plan-001/plan.json`, produced by `native_compile.py plan`
- Dispatcher `fixtures/public/e1s-native-objects/bsd-a-tail/launch.py`
- Outputs `artifacts/e1s-native-compile/bsd-a-tail-001/` in this worktree

Limits are the existing ones: one serial compiler, 512MiB owned RSS, 120s per
child, 1800s whole run under a 1890s `timeout` watchdog, stable admission above
4.5GiB available, cancellation below 4GiB or on memory PSI pressure.

The heavy lease in `artifacts/team-coordination/20261106-team/resource-queue.json`
is issued by this Claude session acting as coordinator under the owner directive
of 2026-11-10. The Codex root coordinator took no part in it. The launcher
requires `heavy`, `qemu` and `light_compile` to be empty before granting.

A failure or cancellation stops the run and is preserved as a failed attempt.
