# REV-030 independent historical-path gate review

Owner: codex-review-history-gate-20261106-dx. Actual atomic claim REV-030; branch/worktree team/rev-history-gate-20261106 / worktrees/rev-history-gate-20261106, based on fd20170. Reservation: docs/reviews/integration-historical. Existing REV-023 remains done and unchanged.

## Verdict and frozen implementation

Accept the historical-path extension plus its schema correction. No actionable P0/P1/P2 finding remains. INT002 alone implemented the shared gate. Exact source sequence:

- 008171aeacd3d1cdf557888c811691a920a79825: historical-path audit extension.
- e297d42e97e0589c83bb1d9e3dffd7fbc3196fc1: original measured evidence.
- e59ef0eb679e2f23c34287e7ddd103d15bc61704: reject malformed new field before set conversion.
- f9b2a61188e0f9801ec36f017b3d5b997120d322: supplemental evidence and preserved witness handling.

Original source/evidence is physically frozen in worktrees/int-history-gate-20261106 at e297d42. Its gate SHA256 is 59c3712982483d2e1f5f33437978844605d86dd942bcf2fde1a42b00ac976688; original capsule SHA256 is 4cfffde860dbc4d6e14dd36d93094a2781b4383ac01bc671892a9f92146f5bae. Corrected source is in separate worktrees/int-history-schema-20261106, gate SHA256 a1e028140e0f1747306a4c2257c3a3f77976e03a83ae59c171991d750286b3c3; supplemental capsule SHA256 8cc05abc231313f40c905e4287c5967c2446fdff8070a63ebbfe108d8dc34ea3. The reviewer rehashed all 61 original and 49 supplemental bindings.

## Actual history and source analysis

The genuine VM013 history has eight commits, 13 net paths and 14 touched paths. The exact difference is fixtures/public/avf-object-shards/iokit/inspect.py. That file was genuinely added, modified and renamed to source_admission.py; it is absent from the net diff. history.py independently derives parent-to-commit no-rename diffs, rather than using the gate's diff-tree implementation. vm013-history.json records the eight exact SHAs and all path sets.

The corrected gate retains a nonempty unique net paths list and requires optional historical_paths to be a JSON array of strings. Both lists must be unique and disjoint. The actual net diff must equal paths, and the union of every commit's touched paths must equal paths plus historical_paths exactly. This enforces completeness and rejects unused declarations. Omitting historical_paths defaults to an empty list, preserving the old behavior for histories without transient names and the old rejection of undeclared transient names. An entirely empty net diff is still outside this protocol.

All canonical-literal, forbidden state/planning/generated-view/lock, dirty intersection, ignored new-file collision and symlink-parent checks apply to the full union. The extension does not weaken full source/candidate commit identity, raw binary/full-index/no-ext-diff/no-textconv/no-rename patch equality, ordered candidate ancestry, merge rejection, clean candidate, staged-index rejection, stale primary HEAD, capsule SHA256 checks, root plan approval, continuous integration-lock publication or the common-check supervisor. Publication permission remains separate from an audit pass.

## Independent controls

The baseline snapshot, controls and reports are retained in this directory. All temporary audits take the fixture's state/.integration.lock and preserve its HEAD and ledger bytes. No test calls the real publication path or project's common check.

- Four baseline cases pass in 0.345 seconds: old plans without history continue to pass, and both omitted and explicit transient histories fail under the old gate.
- The original extension passes 32 independent real-Git cases in 3.491 seconds. They cover genuine source-to-different-cherry-pick mappings; add/rename, add/delete and tracked modification/restore histories; omitted, unused, overlapping and duplicate paths; malformed literal names; forbidden registry/planning/lock/generated paths; dirty tracked/untracked and ignored data; ignored symlink ancestry; unrelated dirty ledger preservation; wrong mapping; stale HEAD; incomplete commit ordering; and staged index rejection.
- Final corrected source passes the same 32 cases in 2.761 seconds, with current-image VmHWM 23,695,360 bytes. Seven additional malformed-shape probes are all rejected.
- The real eight-commit VM013 history was cherry-picked, without squashing or edits, into a disposable shared-object clone of captured MAIN 12a43eef4a00da24bed6604655854ef533d2bbb2. Independent parent-to-commit binary patch digests match for all eight source/candidate pairs. The original gate rejects the actual history; the corrected gate accepts its exact 13 net plus one historical path. Final proof took 1.879 seconds, current-image VmHWM 24,055,808 bytes. Both temporary audits leave HEAD and ledger unchanged. This was never a candidate publication to MAIN.

## Finding and failures retained

The first frozen extension converted historical_paths with set/len without checking its JSON type. Two meaningful controls showed that it accepted an object keyed by the transient filename and a scalar string when the actual filename was one character. This violated the documented new-field schema; it did not escape the exact path scope. The P2 finding was reported immediately and fixed by e59ef0eb before acceptance. schema-control.json and schema-control-failed.py preserve the failing controls and their exact script. corrected-schema-controls.json records seven final rejection controls, including both original cases, null, integer, boolean, non-string and nested members.

One original-capsule binding read encountered the producer's schema-fix WIP in the old source path and stopped. No WIP control was run. The producer moved the fix to the separate schema worktree and restored the old worktree to e297d42; all 61 original bindings then passed. The source path observation is retained in producer-bindings-original.json. The producer's earlier symlink fixture output-path failure and both original/supplemental runs remain in the bound capsules. No measurement was relabeled under corrected source.

## Limits and handoff

The review ran only finite serial Git/filesystem audits and stdlib Python, with current-image /proc VmHWM recorded independently of raw rusage. It performed no MAIN Git write, publication, common make check, compiler, QEMU, phone or physical-device operation. Source inspection confirms lock, approval and common supervision are unchanged; this review does not newly qualify their resource/deadline behavior. Producer disposable publication callbacks are explicitly fixture evidence.

The corrected exact historical-path declaration can support the preserved VM013 history. It does not qualify a full kernel, link, genuine XNU console, PID1, stopping or hardware behavior, and it does not grant any build/guest lease. Root must approve the exact refreshed source candidate and plan after any MAIN advance.

Send scoped review commits and evidence.json to root and INT002. Keep REV-030 in progress until reviewed integration and a fresh serialized MAIN common check are accepted. Only original dx owner may record completion after explicit root authorization; do not take over other tasks or edit shared producer files.
