# REV-012 independent review result

No P0/P1/P2 finding was identified within the documented copied-input host contract of candidate `df53b342c7c2c64580c9ad84ecf54849786fff1a`, integrated at `fe60c3d461e4c0534af680fdca7911354f95790a`. This result qualifies neither actual thermal readings nor measured clocks, firmware calibration, hardware power protection, safe limits, actuation, controller Stop or native operation.

Reviewer owner: `codex-team-review-power-20261105-bn`. Branch/worktree: `team/rev-power-20261105`, `worktrees/rev-power-20261105`. Production files and shared references/artifacts were read only; only `docs/reviews/pwr-003` is committed. KRN026 remains blocked under its existing owner and reservations.

## Exact source and evidence basis

Six candidate files (observe.c/.h, fixture.c, check.py, source-profile.json and README.md) were read through `git show` at the frozen commit and compared byte-for-byte with the integrated worktree. Integration is a cherry-pick, so original-candidate ancestry is not asserted. Twenty Samsung input snapshots were independently checked against SHA256 and exact Git tree blob IDs at `417484173abc2c4fa93e738ea82ad9f2e84911b1`; donor E1S patch0007 was checked against `c8860decc62c6d6180e609036d027a2997972420` and its digest. Git used `GIT_NO_LAZY_FETCH=1` and `GIT_OPTIONAL_LOCKS=0`; no network or lazy fetch occurred.

Both corrected input capsules passed hash review:

- `worktrees/pwr-003-20261105/artifacts/power-host/signed-final-session1/evidence.json`
- `worktrees/pwr-003-20261105/artifacts/power-host/commit-session1/evidence.json`

Their140 unique referenced artifact digests were reread and matched. Earlier `initial-session1` and `final-session1` numeric PASS bytes remain historical results. The separate `signed-review-session1/evidence.json` outcome is inconclusive because the original unsigned target capture could not qualify s32/default semantics; those numeric passes are not the accepted final qualification. The signed-final runtime and its exact commit-binding capsule supply the reviewed result.

## Independent executable challenges

REVPOWER-002 passed317 provenance/check assertions and50 recorded commands. A reviewer-authored C test, independent of production fixture.c and check.py, performed16460 assertions under native ASan/UBSan. It compiled the actual unchanged TMU read helper and actual unchanged active MIF/INT callback with fresh synthetic transport/capture support, exact source declarations, the genuine signed QoS prototype, original domain enum and FVMAP structures. Original source copies/notices and all generated oracle/test code remain local artifacts; no real IPC or QoS actuator was linked.

| Boundary | Independent challenge and result |
| --- | --- |
| TMU units and firmware result | All256 temperatures across8 source zones agreed with the genuine helper and MCELSIUS1000. All255 nonzero signed-return encodings reject as firmware errors and zero output. Opaque status was preserved without treating it as healthy/safe. |
| Signed QoS requests | Both actual callback domains0/1 were checked at zero, unit boundaries, INT32_MAX and adjacent negative/default encodings. The genuine s32 capture agrees: -1/default is unavailable, other negative encodings unsupported, and accepted values are request Hz after kHz multiplication. Unknown domains produced no genuine callback action and were rejected. |
| Domain IDs and FVMAP metadata | All33 domain IDs agree with the original enum.1320 index/count/offset combinations covered empty levels, dense-header overlap, offset1716, unaligned metadata-only extents, maximal count255, exact end and overflow past8192. Reported domain remains separate from selected index. No rate/voltage codes or physical association were inferred. |
| Memory extents | All record prefixes0..15 were exercised against a protected page. All8192 truncated FVMAP lengths were rejected before data reads, with the selected header at domain32. Source-shaped records and test data were owned copies. |
| Time, tickets and state | Wrong epoch/generation and busy calls left pending state byte-identical, even with an invalid supplied time. Expiration was checked at the exact deadline; future sample times rejected, invalidated observations became unavailable, and deadline arithmetic was checked at UINT64_MAX. |
| Stop and availability | Stop was idempotent for both supported kinds, invalidated pending input, and preserved stopped state through later begin/accept/read calls. Missing, failed and unknown transport states could not produce valid observations. Measured-clock/voltage kinds remain unavailable. Stop's result is host invalidation only. |

One compiler ran at a time. Compiler RSS62976KiB and runtime RSS7172KiB were measured using `/usr/bin/time`, below256MiB. The final local review capsule contains126 existing artifacts whose hashes were independently reread and matched. No expensive common-main check was repeated by the reviewer.

## Explicit trust boundaries observed

The genuine TMU sender logs transport errors through a void helper, while `exynos_acpm_tmu_set_read_temp` returns0 and copies response fields without propagating response.ret. An independent failed-sender adapter left the request unmodified: the genuine helper returned0 and temperature0, and the pure decoder accepted the source-shaped buffer as zero degrees. Reporting `POWER_TRANSPORT_FAILED` to the observer rejected that input; falsely reporting transport success admitted it. This is the documented input-provenance gate, not proof of a measured zero temperature. A real backend must propagate actual delivery and firmware errors rather than wrapping the original helper's return0 as success.

Host tickets also do not authenticate a firmware delivery. Reinitializing fresh/retired observer storage using the same caller epoch resets the generation, so an earlier host tag can equal the new instance's tag. The review demonstrated that such a tag with fresh caller timestamps can be admitted. The current component explicitly delegates real response correlation and backend ownership and requires fresh/retired storage; it never claims firmware freshness from the host ticket alone. Future backend integration must retire old deliveries before reuse or use a distinct lifecycle epoch, and route callbacks to the correct observer. This boundary must remain visible when an actual backend is designed; it is not upgraded to a native stale-response guarantee by this review.

The active ACPM callback describes requested MIF/INT QoS kHz. The genuine `exynos_acpm_get_rate` implementation is enclosed in `#if 0`, independently checked. No observed request is a measured frequency. The signedness correction models the real s32 target and -1 default sentinel, not safe frequency bounds.

FVMAP metadata checks cannot establish actual firmware tables, cross-table ownership, fitted sensors, calibration, ECT/ASV silicon binning, voltages or hardware limits. A header count/extent fitting the copy is only a representational result. The E1S ACPM donor and TMU's ESCA sender do not become interchangeable live services because their message shapes are16 bytes.

## Evidence, retained failure and handoff

Final review evidence: `worktrees/rev-power-20261105/artifacts/rev-power/session2/evidence.json`; detailed `report.json` is adjacent. `assessment.json` binds both digests and criteria. The independent test source and generated genuine oracle are in that capsule. The runner is `worktrees/rev-power-20261105/artifacts/rev-power/review_runner.py`; replay requires a new session name and preregistered experiment, for example `python3 artifacts/rev-power/review_runner.py new-review-session` from the reviewer worktree. It never executes the production runner or uses production fixture assertions.

REVPOWER-001 failed before source/test execution because the review harness initially assumed the original candidate commit was an ancestor of the cherry-picked integration. Its failure capsule and original runner copy are retained under session1. REVPOWER-002 corrected that review-only assumption to frozen byte identity; no production code changed to obtain the result.

All three REV012 review criteria are assessed satisfied within the stated host/source boundary, pending coordinator acceptance. Keep REV012 in progress under the original review owner until the coordinator approves completion. Root should inspect the review and preserve the callback/epoch/physical-safety limitations when deciding PWR003's host acceptance. No PWR001/native prerequisite is removed, and no phone/MMIO/power operation is proposed.
