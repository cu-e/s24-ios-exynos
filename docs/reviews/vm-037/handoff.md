# REV-035 shared project budget review

Original owner: codex-review-project-budget-20261106-eg. Task REV-035; isolated branch/worktree team/rev-vm037-eg-20261106 / worktrees/rev-vm037-eg-20261106, base f22951619f2869adeea329f0ae1a7c3d8fdfc8a4. Scope is docs/reviews/vm-037 only. Previous reviewer tasks REV-023 and REV-030 remain done and unchanged.

## Verdict and exact source

Accept the corrected prospective governor through producer final4d8d24db7d370b92ccbb8936eceb08ca95556a19. No actionable P0/P1/P2 finding remains within the documented shared-caller contract. Final helper SHA256: efe908ff5b6321ea1e456306a3094f9188cc501d066bcc78b435b500d56783e6.

Original ordered stack is308d868bc6e9dc1cfa4749f69590403503b5e0b9, b712f8e139ae51098d27b2514c649f3b31bc207b,42d0eadbbf03307b96185baf73e00456185287a7,39f68b5fc7772c3bb8d78591f0b43e8410fd5be9,bede1af5b98a4331c59a9c025c1e2dead945f3a4 and5b92f328559a02d30a42e739584f700f1f6aa223. Its physical helper42f84aff5febfe4800cb0f84f4052bc98ac539766f8d4ecd7739a63d2fb7dd0d and47-control capsule remain unchanged in vm-037-ea-20261106.

First correction:478d47372e04f9953c9b32e9cee9edde30a5be2d,22afd3d5ece62eb1ab119e363a0e68a417c7308c,f663af60c7e272af45053c1b930591b5bfe4c473. Physical helper6caa0872750874937c1343b26a168c0d016fa4c98677f54303546e7d194f915a and64-control capsule remain unchanged in separate vm-037-ea-fix1-20261106.

Final narrow correction:a0d32422bd98a0b949137094200b48b8e0daf9f0,ecbd6dd3174279435a3728b6ae99614cd9cd9d63,4d8d24db7d370b92ccbb8936eceb08ca95556a19, in separate vm-037-ea-fix2-20261106. It changes exactly one production predicate beyond6caa: an active controller that is missing OR an unreaped zombie fails closed for root reconciliation. Producer004 narrow capsule passed8 controls. Source and metadata phases are separately bound; no passing or failed measurement was relabeled under later code.

## Governance assessment

Root's canonical resource queue must name the exact allocation path/SHA/id and slots; an alternate queue or copied grant cannot split the broker. The helper policy SHA and actual reviewed component caller SHA are separate bindings. Every current slot pins task, original owner, experiment, shard/component, source-plan SHA, one serial job and one canonical output. Unique slot totals are bounded globally, including declared work: six jobs initially,6GiB total RSS, at most512MiB per executor, plus a2GiB aggregate light/auxiliary reservation. Default legacy approval/job/RSS behavior remains separate.

A shared stable flock serializes reservation transactions. The corrected implementation uses bounded nonblocking acquisition, limited further by remaining command time. Root revocation, malformed state, known unreadable roots, stale PID/start identity and changed canonical paths reject or defer. Reservations retain every observed owned session and PID/start identity. Release refuses live retained processes; prelaunch refuses a new child while prior owned work survives, preserving one serial slot. Missing/zombie declared roots or active controllers require root reconciliation. Known dynamically discovered light-process identities survive reparenting and cwd changes.

RSS is deduplicated by PID and includes controllers, descendants, declared outside-project roots and discovered light work. Unknown project compilers defer. Every compiler admission uses three stable >=4GiB observations spaced one second apart; own/global RSS, memory floor, lost grant and deadlines stop only the caller's owned child. Landlock, finite owned cleanup, namespace/source/recipe/output validation and genuine command vectors remain. Per-process VmSwap, host pswpin/pswpout and deltas are separate observations; host swap is not attributed causally to this project.

These are sampled limits, not cgroups or a proof of absent between-sample peaks. Cwd discovery is not an ownership oracle for work rooted outside MAIN; root must declare that work. A reviewed shared caller must supply canonical args and validate its ledger ownership, literal scope, exact new plan, output and command vectors, then call the governor serially. The governor is resource policy, not an authorization substitute for those caller checks.

Eight-job admission only validates the bound six-job receipt schema inside a root-granted allocation. Measurement truth requires an actual prior six-job trial, independent/root review and a separate root grant. No authored JSON receipt, synthetic control or this review proves such a trial. The actual first-six measurement is still pending and this review grants no actual six/eight execution.

## Independent evidence and resolved findings

Six genuine findings were reproduced and reported immediately. findings.md and all original scripts/receipts preserve their details:

- P1: a new session erased an earlier outside-cwd orphan and allowed release while it lived.
- P2: live queue/allocation symlinks were accepted after initial canonical checks.
- P1: blocking broker flock stalled a live child's deadline/RSS watchdog.
- P2: checksum and separately parsed plan opens could consume different JSON bytes after an actual atomic replacement.
- P1: a vanished declared external root silently lost its outside-cwd orphan.
- P1: the first correction still admitted an unreaped active zombie controller and omitted its not-yet-sampled orphan.

All are fixed. Failed receipts remain byte-identical and no unrelated process was signalled. The original helper, first correction and legacy5c byte snapshots are retained in this directory; producer original/first-correction worktrees remain physically unchanged.

The first corrective helper passed47 independent focused controls across six reports: corrected-focused-controls.json(3), corrected-lock-control.json(1), corrected-existing-root-control.json(1), extended-controls.json(28), prelaunch-control.json(1), admission-controls.json(13). They include real orphan/session lifetimes, new-command deferral, outside-cwd roots, a real detached lock holder with live-child deadline stopping, all five live canonical paths, root queue changes, copied grants, six distinct512MiB slots versus seven/eight without prerequisites, separate caller/policy pins, controlled known-owned read error, real same-FD atomic replacement and deduplication/swap records. Tiny actors had finite deadlines and finally cleanup.

The immutable genuine1080-row graph/PIN was read once for identity comparison. Every recipe expansion/digest matches accepted legacy5c; complete provenance/recipe/input-key operand ASTs and legacy validation/output/Landlock functions are unchanged. No namespace sweep, compiler matrix or historical benchmark timing was repeated. This check used1.350s with actual current-image VmHWM85,893,120 bytes; that is a new bounded verifier timing, not a build/performance comparison.

Final narrow regression: the same real active-zombie/orphan setup now rejects with stale-reservation/root-reconciliation,1.780s, current-image VmHWM21,614,592 bytes. A live observer positive and18 exact source/capsule/original-failure/legacy lineage bindings pass. The full final helper bytes equal6caa except the one stated predicate, so the earlier47 PASS controls are retained rather than repeated. Producer original47, corrective64 and final8 phases remain separate.

## Acceptance limits and next dependency

No compiler, archive/linker, QEMU, full common check, MAIN publication, phone or device operation ran in this review. No existing job, old plan, old private path, physical legacy tool or historical failure was changed. This qualifies future host process governance only, not a complete kernel, XNU image/serial/PID1, device operation or the full roadmap.

Root/INT002 must integrate the exact reviewed source/review commits at a completed-wave boundary and accept fresh serialized MAIN common checks. VM036's reviewed caller and original shard owners can then prepare new plans pinned to final helperEFE, with caller SHA separately bound, and request a distinct root allocation for the actual six-job measurement. Eight stays prohibited until actual measured-six acceptance and a new root grant. The original eg reviewer closes REV-035 only after explicit root acceptance; original ea alone closes VM-037. No further broad test or benchmark rerun is needed absent a new concern.
