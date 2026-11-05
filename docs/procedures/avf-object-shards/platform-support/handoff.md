# VM-018 handoff

Original owner: `codex-guest-exec-20261106-dc`. Worktree/branch:
`worktrees/vm-018-20261106` / `team/vm-018-20261106`. Source preparation commit:
`560493c11690d730104a166f706ea4647408a4eb`, based on MAIN
`aac27cfbc0d71b34eda33ddf366c72427507ae0b`.

The exact `platform-support` allocation has thirteen IDs: eleven pexpert C
sources, `libsa/bootstrap.cpo` (C++17 GNU dialect) and `san/ubsan_minimal.o`.
`selection.json` records all thirteen frozen row/source/configuration hashes and
references the original complete manifest; recipes are not duplicated. Its
manifest SHA256 is
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
The allocation SHA256 is
`855246471cd69fc7b0e482b5247b1e249adc1453018c922698435bbc88972853`.

Registered experiment `VM018PREP-001` passed on 2026-11-05 UTC, with actual
command and timestamps in `evidence.json` and `runs/preflight-1/report.json`.
The command exited 0 in 2.186 seconds. Thirteen direct sources, three component
Makefiles and the source-built compiler match their pins. All 107 direct literal
include directives have existing candidates; their paths/hashes and per-object
search order are retained. Forced meta_features hashes match the three selected
component configurations. Six controls reject duplicate/foreign IDs, altered
source hash, wrong board, disabled allocator builtins and redirected output.
Three memory samples exceed 4 GiB. Current executable image VmHWM is 72,876,032
bytes; raw historical ru_maxrss is 1,834,459,136 bytes and is not used as current
RSS. File hashes are streamed in 1 MiB blocks.

Three originally declared include roots are genuinely absent: EXPORT_HDRS/libsa,
public source context usr/local/include/kernel, and its Kernel.framework private
platform path. These are retained as absent search entries without inventing
headers or weakening flags. The literal inventory does not evaluate conditionals,
resolve macro includes, or establish actual transitive compiler dependencies.
A discovery `rg` command returned 2 after a guessed gen/pe_bootargs.c path; the
actual frozen row names arm/pe_bootargs.c. Evidence retains this distinction.

No compiler, preprocessor, generator, linker, QEMU or phone process was started.
No E1S object was consumed; no shared artifact, primary Git ref, registry copy,
common check or MAIN source publication was performed by this worker. The task
remains in progress because actual object/dependency closure acceptance remains
unmeasured.

Next: independent review by the permanent kernel integrator and root. After
VM008 namespace and VM009 common executor acceptance, use misc_worker’s common
runner `--mode plan --task VM-018 --shard platform-support` against the original
manifest, pinned qualification and allocation. Register a new actual compilation
experiment and obtain an explicit root heavy lease before any compiler. Preserve
failures, actual depfile/object hashes, resource evidence and the original recipe.
Only the original owner closes after independent review, integrator acceptance
and fresh MAIN common checks by the integrator under `state/.integration.lock`.
