# VM013BUILD: shared IOKit plan and gated actual compilation

Original task/owner/worktree remain VM-013 / codex-guest-exec-20261106-cv /
worktrees/vm-013-20261106. Register VM013BUILD in the sole MAIN ledger before
planning, and keep it planned for later authorized execution.

The accepted MAIN shared executor is tools/build/avf_kernel_objects.py, SHA256
13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47.
Use only its mode=plan with the frozen 1080 graph and selector=iokit (104 rows),
including all 17 original generated IIG implementations. Accepted VM008 qualifier
SHA256 is 058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7.
Frozen graph SHA256 remains
afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd;
selector SHA256 remains
855246471cd69fc7b0e482b5247b1e249adc1453018c922698435bbc88972853.

Use a fresh original-owned artifacts directory. The shared executor's reviewed
run_child/supervisor helpers guard the source-only runner process: three stable
>=4 GiB samples, finite 120 s command, <=256 MiB aggregate resident memory, actual
exit/log/sample hashes and verified owned-child cleanup. No new supervisor or
source checker is introduced. Keep execution-plan.json, input-bindings.json,
executor evidence and all failed/deferred attempts. Report exact selected IDs,
input keys, genuine recipe-template digests, plan and source-evidence hashes.

The subsequent execute phase is forbidden until root explicitly grants the heavy
group lease and exact approval descriptor. Then consume the same reviewed runner
and frozen inputs with mode=execute, one serial compiler per executor, <=2 total
compiler jobs and <2 GiB aggregate new owned RSS, existing in-process 600 s guard,
and a new output directory. Preserve real failures and partial outputs. No source
or profile weakening, private SDK, old E1S products, provider inventions, main
publication, common checks, QEMU or physical phone action. Actual compilation
may resolve historical generated-IIG compile uncertainty but never establishes
selected private Apple ABI merely from a plan or successful object compilation.
