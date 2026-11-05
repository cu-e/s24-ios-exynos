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

## Accepted common runner source plan

On 2026-11-05 UTC, root resumed this original owner for the first real guest
object shard. VM008 is accepted and MAIN contains the reviewed VM009 runner at
`6518a04f6a7eca5500d3e61b1d082dbb264ac94a`. Its exact SHA256 is
`13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47`.
The VM008 qualification descriptor SHA256 is
`058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7`.
No maintained checker or runner source was changed.

`VM018BUILD-001` is registered in MAIN and deliberately remains **planned**.
It covers this source plan plus future explicitly authorized actual compilation.
Do not record the experiment from the successful source-only plan. Its procedure
is `build-001.md` and its separate plan evidence is
`build-001-plan-evidence.json`; the earlier recorded VM018PREP evidence is intact.

The accepted MAIN runner's `--mode plan` passed under its existing `run_child`
resource helper, which started only a Python planner. The command exited 0 in
75.907 seconds, selected exactly thirteen rows, bound 6,721 source/config/tool/
header files and retained 32 existing roots plus four genuine absent roots for
the complete 1,080-row graph. The aggregate controller plus child peak was
123,338,752 bytes, planner VmHWM was 101,793,792 bytes, and the outer controller
VmHWM was 21,549,056 bytes. Three samples at one second intervals exceeded 4 GiB;
the command had a 120 second deadline and left zero owned processes.
`compiler_started` is false and the object list is empty.

Fresh local artifacts are under
`artifacts/avf-object-shards/platform-support/plan-001` in this worktree:

- `plan/execution-plan.json`: SHA256
  `8d9678fa01bb8c8b3240878ed8dccf60ce93bfcb282303963d95f9e60813a742`.
- `plan/input-bindings.json`: SHA256
  `60f7b4774bcec32ff83093629d5f1fa00ade24ecddbd4c64a2d6e96c8d75221e`.
- `plan/evidence.json`: SHA256
  `4f599b41cfb47366a1fec7f9f09ae3df462450d51fcf8b19e5c7bd9badb75bac`.
- `supervised-plan.json`: SHA256
  `cb84e87e01171b5f89d9b01788f981e698763f6cb66e2bcfdceecacf28b506ca`.
- `build-ready-argv-template.json`: SHA256
  `f60aed20cdd5d8449ee9e39b63c26f491e83b16fcbbd91f0d1bb0ce69ed77f1d`.

The bound namespace identity is
`a2410326ba3560948edb9923b8dd8382d0557060ceaaf031735feef1bfbaa70a`.
All thirteen source/configuration/recipe/input-key hashes and exact executed
plan argv are retained. The future argv targets fresh `execute-001` output and
has explicit root approval file/SHA placeholders; those placeholders confer no
authority. No execution output exists yet.

Next action requires root's explicit heavy lease after VM009 common PASS and
original VM009 owner acceptance. Resolve only the actual root approval inputs,
retain all other frozen arguments and use the accepted shared runner directly.
Preserve the first real compiler, missing-root, dependency and resource outcomes.
No compiler, main publication, common check, linker, QEMU or phone operation is
authorized by this source plan.
