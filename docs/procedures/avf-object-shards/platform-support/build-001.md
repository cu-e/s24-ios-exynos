# VM018BUILD-001 planned guest object experiment

Original owner: `codex-guest-exec-20261106-dc`; original registered worktree:
`worktrees/vm-018-20261106`. This experiment covers source-only plan admission
followed by future explicitly authorized compilation of the thirteen frozen
`platform-support` rows. Keep the MAIN experiment planned until that actual
compilation has run. A successful plan is not compiled-object evidence.

Use the shared runner published in MAIN at
`6518a04f6a7eca5500d3e61b1d082dbb264ac94a`, reviewed implementation SHA256
`13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47`.
Do not edit, copy into a second maintained checker, or reconstruct its recipes.
Invoke its existing `run_child` helper around the exact `--mode plan` CLI so
the plan receives the same finite resource supervision: three stable samples
at least 4 GiB one second apart, 120 second command deadline, and aggregate
controller plus child RSS at most 256 MiB. The outer helper starts only the
Python planner; `compiler_started` must remain false and `objects` empty.

The immutable graph SHA256 is
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`;
the full ten-shard allocation SHA256 is
`855246471cd69fc7b0e482b5247b1e249adc1453018c922698435bbc88972853`;
the accepted VM008 descriptor SHA256 is
`058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7`.
Retain the entire 1,080-row manifest and select `platform-support` through the
shared runner; do not truncate the qualification graph to thirteen rows.

Create fresh plan and execution outputs under the registered worktree's
`artifacts` directory. Preserve helper stdout/stderr, memory samples, exact
argv, source/config/tool/header bindings, selected plan and all hashes. Failed
and resource-deferred attempts remain separate immutable attempts.

Compilation remains prohibited until root explicitly grants this original owner
a heavy lease after VM009 common checks pass and its original owner accepts the
task. The runner also requires the root approval descriptor and exact SHA256.
Do not manufacture an approval descriptor or treat booleans as permission.
One executor and one compiler at a time for this shard; the project-wide cap is
two compiler jobs total. Actual compiler commands retain the reviewed helper's
120 second deadline and 256 MiB aggregate RSS budget. No E1S objects, main
publication, common checks, physical phone operations, linker or QEMU launch.

After actual authorized execution, retain all thirteen object sidecars,
compiler exits, exact source and dependency hashes, Mach-O validation, failures,
memory samples and final namespace validation. Only then record the experiment's
real outcome. Compiled objects still do not establish a complete kernel, link,
console, PID1, stopping behavior, private Apple ABI or native S24 operation.
