# VM015BUILD-001: shared plan and future object compilation

Original owner `codex-guest-exec-20261106-cz` resumes VM-015 in the original
registered `worktrees/vm-015-20261106` worktree. Preserve all source-preparation
commits and artifacts. This experiment covers the shared runner's source-only
plan now and its future explicitly authorized execution. Keep the experiment
planned until actual compilation has run; a passing plan is not object evidence.

Use the accepted MAIN `tools/build/avf_kernel_objects.py`, implementation SHA256
`13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47`.
Invoke its existing `run_child` and `supervisor` helpers around the exact
`--mode plan` CLI, with a 120-second command deadline, stable three-sample
MemAvailable >=4GiB admission and aggregate controller/child RSS <=256MiB.
No new executor, checker, source edit or recipe reconstruction is authorized.
The planner must report `compiler_started=false`, no objects and exactly the
77 IDs assigned to `osfmk-machine` in the complete disjoint allocation.

Use the complete frozen VM-008 graph, SHA256
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`,
the accepted qualifier SHA256
`058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7`,
and coordinator allocation SHA256
`855246471cd69fc7b0e482b5247b1e249adc1453018c922698435bbc88972853`.
Select `--shard osfmk-machine` through the accepted runner without truncating
the qualification graph. Save exact argv, source/input keys, namespace bindings,
plan and output hashes, resource samples, command exits and owned-process cleanup
under a new original-worktree artifact directory. Retain failed attempts.

The coordinator has accepted VM-008 and VM-009. Compilation still requires an
explicit root heavy-group lease and its root-published approval descriptor.
Platform integration currently owns the heavy queue, so this phase starts no
compiler. Later execute must use the accepted same-process 600-second launcher,
one serial compiler for this shard, at most two compiler jobs project-wide and
at most 2GiB new owned aggregate RSS, with the 4GiB admission floor. Do not create
an approval descriptor or infer a lease from task/namespace acceptance.

No E1S objects, shared-input writes, profile weakening, linker, QEMU, physical
phone operation, MAIN publication or common check is authorized here. A later
object pass still does not establish a complete kernel/link, genuine console,
PID1/stop, private Apple ABI, native E1S or S24 hardware support.
