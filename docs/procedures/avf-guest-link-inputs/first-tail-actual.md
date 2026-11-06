# First actual guest tail products

On 2026-11-06, original VM-022 owner `codex-guest-exec-20261106-cu` executed the first four-tail run once under root lease `guest-link-tails-20261106-25`. The immutable v2 launcher ran the reviewed helper in the same process. All four genuine DEVELOPMENT/BCM2837 compile commands and the source-built constructor segment transform passed. No retry occurred.

The run used accepted source `468cc06064085b1f75721b590cd871b57a7c0443`, helper SHA256 `99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060`, source plan `6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569`, and unchanged AF193 policy. Publication `b000b0af2e67212e4c75a217f2b38467e820268a`, its actual common capsule, and root acceptance were bound by the launcher. The exact invocation, admission specification, and source controls remain in [first-tail-run.md](first-tail-run.md). The root approval SHA256 was `b7dd7c4bff7b414073bbe58177c5acd9151bb96ca9c4111fec45f6ace2f3259b`; allocation SHA256 was `86d45b6350cc270ce251749308dcca81f549367a7377accc233691728f580f56`.

Actual output root is `worktrees/vm-022-tail-cancellation-20261106/artifacts/avf-guest-link-inputs/tails-execute-1` relative to MAIN. Consumers must use its literal paths and byte bindings:

| Object | SHA256 | Bytes |
| --- | --- | ---: |
| `objects/nonlto.o` | `ed2fcecf5af6ab310eda69246e0ca9e7358166ca2036e291c79e0abe186bbb23` | 2072 |
| `objects/version.o` | `157fe8b6d489672e589e31bb935a028692c2e5b262ee4acae4bf0dc43b1e0414` | 4024 |
| `objects/lastkerneldataconst.o` | `60e3dca667a08fa8588bc61b8fd0e1581efd8a18c114c4e6cf9759994a0a6cd0` | 19704 |
| `objects/lastkernelconstructor.o` | `fa8b7f2aa3750851d0f2becb7fced985f89590b3047525d2a7d30d3f29370370` | 2568 |

All four are ARM64 Mach-O objects. The original constructor remains at `raw/lastkernelconstructor.o`, SHA256 `812cf5471c7840c7ae41c890e35de16bc64f91ce74a18c5bab88fa19ab08bb82`. The exact bounded byte comparison verified the `__mod_init_func` section's rename from `__DATA` to `__LASTDATA_CONST`. Actual MD files, dependency content hashes, source hashes, ordered argv, working directories, command logs, runtime samples and input namespace bindings are retained in the raw output directory.

Raw `evidence.json` SHA256 is `3abed3cb6de1cbe0c9e493340ef9b8af4fa00330d89254b5bb3dadfb87f4a0f1`. Launcher evidence at `worktrees/vm-022-tail-admission-20261106/artifacts/avf-guest-link-inputs/tail-run-launch-1/launcher-evidence.json` has SHA256 `6ab18cfe512cdd883f7f744148c3326eed9f73db20e15954bfb6271631ebac55`. Elapsed time was 12.390497567 seconds. The whole-run deadline did not fire, no stop signals arrived, and every child exited zero. The maximum sampled owned RSS was 95,657,984 bytes against the 256 MiB cap. Current-image `/proc` VmHWM was 43,040,768 bytes; inherited `ru_maxrss` of 1,380,720,640 bytes is historical process accounting.

Controller PID/start was `3636867/59480851`. Five recorded session/start identities were `3636940/59481133`, `3636980/59481369`, `3637057/59481609`, `3637101/59481847`, and `3637134/59482072`. Each command recorded empty owned-process cleanup. The persisted reservation became `complete` with `owned={}`; the raw `budget_release: null` is the shared release API's return value. Read-only owner verification found all six PID paths absent. Root separately scanned the complete process table against the recorded identities and sessions, found zero survivors, and atomically released the global lease. Its actual receipt is `artifacts/team-coordination/20261106-team/tail-first25-release.json`.

The [actual product descriptor](../../../fixtures/public/avf-guest-link-inputs/built-tails.json) binds all four objects and MD dependencies. [Owner evidence](first-tail-actual-evidence.json) binds the raw result, launcher, descriptor and all 29 output files, plus immutable snapshots of approval, allocation, grant, completed reservation and root release. Artifact snapshots live in `worktrees/vm-022-tail-admission-20261106/artifacts/avf-guest-link-inputs/actual-tail-handoff-1`. Its `capture.py` performed content verification and handoff capture only.

Independent actual-product review is pending. The run produced no archive, linked kernel, XNUP payload or guest result, and does not close whole VM-022. The separate `dc7f669a` / `6061ab87` main-link source freeze remains unchanged and under independent review. Future VM046 policy/profile adoption requires explicit review; the preserved AF193 snapshot is inspectable historical source identity only. Old canonical MAIN-path receipts must never be silently repointed, and no cross-profile object adoption is implied.
