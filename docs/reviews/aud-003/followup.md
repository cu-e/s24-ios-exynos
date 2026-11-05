# AUD-003 P2 constructor contract closure, 2026-11-05

**The P2 finding is resolved by explicit lifetime-contract clarification and a legal reconstruction regression. No remaining concrete finding was identified in this bounded followup.** The original report, counterexample and measurements in commit `98ee3cf887bbb1f331b0ca278d0a5f73c7c733b2` remain preserved; the initial finding is not relabeled as a passing live-reset guarantee.

Same REV-013 owner: `codex-team-review-audio-20261105-bo`.
Reviewed fix `08ec46d92ae3e4b95ecf9d56d2ac180b53183208` and evidence followup `fff8f269d5dd6f38472b0fa6e77e1f33a2eb32a4`. Main integrated them as `ad671a3` and `220d003`. The reviewer worktree remained based on its original snapshot; exact new files were read from Git into reviewer-local artifacts. Only `docs/reviews/aud-003` changes.

The public header and README now explicitly define `pcm_host_init` as a constructor for fresh or fully retired storage, never Stop/drain/reset. Existing storage requires all lease retirement, Stop/CLOSED/provider fence/release, backend and callback drain and retirement of borrowed views before reconstruction. Live struct copying/cloning/restore/relocation is prohibited; diagnostic snapshots are not owners. The caller must retain a never-reused, increasing epoch high-water mark outside host storage for the same token/backend association domain, including reconstruction and counter exhaustion. The contract states that construction clears local counters and cannot enforce those cross-construction facts. This directly addresses the initial documentation gap.

`pcm_host.c` is byte-identical to the original reviewed implementation. No guard was added that reads an uninitialized host, and no unchecked live-reset behavior was converted into an accepted recovery API. The original adverse sequence remains outside the now-explicit contract; caller misuse can still discard its own state. This closure establishes the supported lifetime boundary, not runtime enforcement of physical quiescence or external epoch authority.

The actual owner regression fully Stop/retires/CLOSED/fences/releases epoch 41, reconstructs with caller-held epoch 42, claims the same slot 0/serial 1, rejects the old lease as PCM_STALE, verifies byte-identical new host state and continued busy ownership, then completes teardown. The fixture main() invokes it and adds 21 assertions to the prior fixture. All 59 entries in the new artifact index matched actual sizes/hashes; the capsule SHA256 matched the supplied exact value `43bbe3ee50e2d93c0f25ff7fe33b07a845197502b73f29751163c07bb959c9d4`. Every reported owned source hash matched the exact fix commit. The prior evidence hash and original reviewer capsule/wrapper hash link remain valid.

A separate tiny [lifetime.c](lifetime.c) check independently exercised only the legal transition with the complete pinned IPC header and unchanged core C. It passed ASan+UBSan: epochs 41/42, repeated slot 0/serial 1, old token stale, new host bytes unchanged and slot still busy, followed by full teardown. No broad plan/pointer/mutation suite or ARM target build was repeated. One small compile/run had maximum RSS 58,248/5,956KiB and exited 0. The focused test has no backend, borrowed DMA view or hardware callback; its provider fence is the same explicit host premise, not a hardware measurement.

REVAUD-002 was registered in MAIN before execution. Actual command:

```sh
GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 python3 docs/reviews/aud-003/verify_lifetime.py
```

Actual followup evidence: `worktrees/rev-audio-20261105/artifacts/rev-audio/20261105-lifetime1/evidence.json`. All 18 recorded commands exited 0; source/tool/artifact hashes, exact executed verifier, source/regression snapshots and real diagnostics are retained. The runner rejects an existing output directory; use fresh `S24_REVAUD_LIFETIME_RUN` for any justified reproduction. Shared sources/artifacts remained read-only and Git guards stayed enabled.

The acceptance boundary remains unchanged: host/source qualification only; no DSP/firmware execution, real PCM playback/capture, DMA/MMIO, CS35L43/fitted BYH3 qualification, native AUD-001 link/runtime, or private Apple ABI result. Keep REV-013 in progress until coordinator acceptance and common integration checks. No implementation task was completed under another owner.
