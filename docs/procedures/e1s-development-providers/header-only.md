# STR018 separately admitted native header phase

Original SR18 owner and worktree remain unchanged. Experiment
`E1SPROVIDERHEADERS-001` covers only the 30 genuine native Make install groups
and one Firehose header export from the corrected provider plan003. All first 31
vectors are identical to independently source-backed plan002; only the later
Firehose compile has the narrow two-token warning correction. The original
f298410 commit, plan002 and prior header-only drafts remain retained.
Independent review found an alarm ownership/cleanup defect in adapter
`90e31681…` (commit `b35a666`); plan002 and that source revision remain
unchanged. This source-only correction removes only the custom alarm and adds
monotonic work-boundary checks; no target operation ran.

The exact header plan is
`artifacts/e1s-development-providers/header-plan-004/execution-plan.json`, SHA256
`2e673a4abb9e9aa0acab322fd369e33623edef090f9a3a37ce0d5931e53570a3`.
Adapter `fixtures/public/e1s-development-providers/header_only.py` has SHA256
`dfab7c3daf099d0da07af84c42a983fb57dd41de2ae061d96921516292b447a7`.
This is a source freeze: no header tool was executed, and `execute-001` is absent.

The adapter uses existing 9929 `project_approval`, ProjectBudget, run_child and
the accepted qemu_host supervisor, plus existing 9f80 `owned_cancellation` and
`run_owned_child`. It implements no process launcher, monitor, signal cleanup
engine or budget broker. Root approval must bind this exact adapter/header
plan, original owner, task, experiment, `providers-headers` slot and fresh output.
One serial slot with 512MiB ceiling and the existing 4GiB memory floor remain
unchanged. The adapter's `whole_seconds=600` is a dispatch/work-boundary budget,
not a hard whole-process limit. Monotonic checks run at each hash, copy,
directory, product and command boundary. Each shared child receives a timeout
of `min(120s, remaining work budget)`. The pinned common helper first performs
stable-memory admission for up to 45s, before starting that child timeout clock.
A final admitted command may therefore finish up to 45s after the 600s work
boundary (645s admitted work), followed by finite owned reservation release and
evidence cleanup. No subsequent work is dispatched after the boundary.

Root must supply the external GNU `timeout` watchdog at 690s before admission,
with root-owned cleanup verification. The adapter does not install or enforce
that outer watchdog, and its declaration is not a grant. The adapter installs
no alarm or timer; existing shared bounded locks retain their own alarm
ownership. Existing cancellation handlers remain installed through finite
owned cleanup. Header-plan003/82b3 and adapter dfab receipts remain retained;
this revision changes only source deadline documentation and plan metadata.
No grant, allocation or permission is inferred from these declarations.

Setup is restricted to canonical owned header directories and exactly four
hash-identical actual003 export-header prerequisites from final MIGfe67, copied
read-only into genuine Make generated prerequisite cwd paths. No native BSD
projection, object directory, SDK directory, compiler, archive or layout setup
is part of this phase. Children have the existing run_child Landlock write
boundary covering the owned output; native Make source/host inputs remain read
only. All 653 frozen provider-plan inputs and the exact helper files are checked
before target tools and after the header phase.

Each actual Make exit and combined child/resource/cleanup record is preserved.
Genuine Firehose unifdef accepts 0 or 1, with its raw exit retained. The adapter
requires 315 real nonempty regular0444 installed headers, physical hashes and
source/mode provenance, then checks 32 actual .UNIFDEF_FLAGS files against the
current public/private native filter argv. The Firehose export receives its own
actual path/hash. Native filtering and empty seed remain unchanged.

Missing output is recorded as `absent-filtering-unproven` and fails closed. Make
exit 0 alone never labels an absence genuinely filtered-empty, and no empty stub,
old header or raw fallback is inserted. A failed or inconclusive run retains
its partial files and diagnostics; there is no automatic retry. Actual filtered
bytes and any new missing/empty boundary must be reviewed before four compiles.

Existing cancellation and budget release validate owned child cleanup. The
adapter releases only its own reservation; root owns the allocation/global
lease. The dated raw evidence is `execute-001/evidence.json`. A passing header
result qualifies only the observed header phase, never provider objects,
archive contents, ABI, full link/image, runtime or hardware. Original task
completion remains gated on later actual provider results and independent/root
integration acceptance.

Future invocation requires the root-owned external GNU `timeout` 690s watchdog
and explicit root-supplied approval path and digest. The adapter argv below is
the inner invocation; root supplies and owns the outer watchdog:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/e1s-development-providers/header_only.py \
  --source-plan /home/egor/dev/pet/s24-ios-exynos/worktrees/str-018-e1s-development-providers-20261106/artifacts/e1s-development-providers/header-plan-004/execution-plan.json \
  --source-plan-sha256 2e673a4abb9e9aa0acab322fd369e33623edef090f9a3a37ce0d5931e53570a3 \
  --approval ROOT_APPROVAL_PATH --approval-sha256 ROOT_APPROVAL_SHA256
```
