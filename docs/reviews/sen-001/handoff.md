# REV-004 handoff

2026-11-05. Owner `codex-team-review-sensors-20261105-ar`.
Branch `team/rev-sensors-20261105`; worktree `worktrees/rev-sensors-20261105`, based on main `f18eba2` when created. Owned path only `docs/reviews/sen-001`. Prior REV-002 has its distinct original owner; do not conflate task identities.

Exact candidate `f6b20723b1b3c3e1acb39c68af90924956d0d147`, follow-up `82c8e9482611ce42f89f2bc923bb9dfa9327609b`. No actionable P0/P1/P2 host finding. Review report explains extent/arithmetic, timestamps, atomic error output, service-unavailable handling, provenance and native limits. GNSS structure disagrees with explicit offsets; actual writer agrees with the candidate. No implementation/reference edit occurred.

REVSEN-001 was registered through MAIN before verification. Actual invocation, exit0:

```sh
python3 docs/reviews/sen-001/verify.py
```

Evidence relative to main: `worktrees/rev-sensors-20261105/artifacts/rev-sensors/20261105-session1/evidence.json`. All 34 logged commands exited 0. Existing failed/final capsule output hashes, exact final owned-input hashes, 18 newly read pinned Git blobs and seven original HAL identities matched. Independent single small ASan+UBSan compile/run passed 61 SHUB prefixes, seven atomic invalid cases, max 4680 batch, clock extremes, protected zero-extent unavailable cases and 54 actual GNSS-writer cases including maximum 65535 length. Runtime RSS 6,224KiB. The actual writer and genuine source header remain ignored local artifacts with original source snapshots. No native execution or device command occurred.

The runner saves its exact executed bytes and rejects an existing output directory. Use a fresh canonical `S24_REVSEN_RUN` environment value for any justified reproduction. Source pin, compiler hash, commands/exits and actual artifact hashes are retained in evidence. `git diff --check` is the review whitespace check; main common `make check` belongs to coordinator integration. No heavy build or repeated suite was run here.

Next: coordinator inspect report/evidence, cherry-pick only the review commit and assess acceptance alongside main integration checks. Keep REV-004 in progress until coordinator accepts; do not complete SEN-001 under the implementation owner's identity. If candidate code changes, review the new exact commit before reusing this conclusion.
