# VM-014 Firehose profile v1 preparation

Original owner `codex-guest-exec-20261106-cw` continues VM-014 without a new
claim. Fresh worktree `worktrees/vm-014-profile-v1-20261106`, branch
`team/vm-014-profile-v1-20261106`, starts at actual MAIN
`951679e13034b4d7f339edf99058020a028b2353`. The literal reserved paths remain
`fixtures/public/avf-object-shards/libkern` and
`docs/procedures/avf-object-shards/libkern`. MAIN is the sole registry; only
this task's owner/worktree/handoff metadata is updated through MAIN `lab.py`.

The previous `worktrees/vm-014-20261106` worktree and its source/plan/build
artifacts remain immutable. Its real old-profile attempt has 75 passing objects
and two genuine compiler failures for the missing Firehose header. Those bytes,
source flags and evidence retain their old profile identity. No old object,
sidecar, successful record or resume capsule is credited to this new profile.

The request fixture pins only the accepted VM-038 profile:

| Input | SHA256 |
| --- | --- |
| Full 1,080-row manifest | `be02fbfc38a73831d3570e69b24277917e69efc09cd696cc853521c393edc298` |
| Qualification | `3343a382452d05c382a15ea54e3835c3125c67c451cb586a1c3ed5a939b37174` |
| Full namespace identity | `25f22291e314445a01a4030e7db74f8cebd9a935b604eefc7b1ad9f5ee033461` |
| Derived selectors | `408720d8bbdbc982079f778ce662f20051dc1d761b9ca216346896a5dabf0744` |

Use the exact descriptor-referenced original VM-038 paths in `request.json`.
The selector contains exactly 77 ordered libkern IDs. The future shared plan
must validate the complete 1,080-row/55-generated-source graph and 6,722-file
namespace before selecting this shard; metadata preparation is not that plan.
The accepted derivation replaces only the already-declared include-root token
at the same position. Do not add flags, install content into the old absent
root, or change source/configuration/compiler/index/current-tool bytes.

This preparation streams only the manifest, descriptor and selector file hashes
and writes the request/procedure. It does not rerun any lexical checker,
namespace walk, source/header matrix, preprocessor, compiler or old-profile
experiment. No compile or namespace success is inferred from metadata matches.

Do not run the shared full-namespace source-only plan until INT002 supplies the
exact independently reviewed VM-039 helper freeze and final CLI. Do not guess
the profile flag, override a manifest PIN, create a duplicate executor or make
a compatibility sidecar. Once frozen, record its path/hash/review receipt in
a new immutable request version, pin the exact reviewed 1,200-second whole
deadline launcher, then register proposed experiment `VMLIBPROFILE1-001` under
the original cw owner before the first source-only plan. No experiment is
registered by this metadata-only preparation. Source-only planning must use
the shared engine and its accepted `project-budget-v1` resource contract.

Keep both owned output directories absent until the admitted shared engine
creates them:

- `artifacts/avf-object-shards/libkern/profile-v1/plan-001`.
- `artifacts/avf-object-shards/libkern/profile-v1/build-001`.

Preserve failed attempts; never reuse or overwrite an output directory. The
new profile requires fresh compilation of all 77 selected IDs, with no old
resume credit. The future proposed budget is a 1,200-second whole pipeline,
120 seconds per compiler command, one serial compiler and 512 MiB combined
controller plus descendants for this executor. The prospective **global**
ceiling is six compiler jobs and 6 GiB total new project RSS, with a separate
2 GiB global light/auxiliary reservation. Those global values are not a
per-worker allowance. Stable admission still requires three observations at
least one second apart with at least 4 GiB MemAvailable, and root must establish
its stricter recovery admission before granting the actual allocation.

Actual compilation additionally requires accepted VM-039 publication/common
checks, the new reviewed source-only plan, and root's exact allocation and
hash-bound approval. Preparation does not grant a slot or change the canonical
resource queue. No QEMU, MAIN publication/common checks, physical phone action,
cache/swap manipulation or unrelated-process cleanup is authorized here. Keep
VM-014 in progress; original-owner closure requires actual complete acceptance.
