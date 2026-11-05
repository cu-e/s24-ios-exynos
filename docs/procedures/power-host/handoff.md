# PWR-003 integration handoff

Date: 2026-11-05. Owner: `codex-team-power-host-20261105-bj`.
Branch: `team/pwr-003-20261105`; worktree: `worktrees/pwr-003-20261105`.
Retain `in_progress` pending coordinator review/integration/common checks.
Parent PWR-001 remains separate, with its original dependencies and reservation.
No phone/ADB/MMIO, thermal probe, native IPC/QoS, clock/voltage/reset/power or
charging/suspend action was issued.

## Deliverable and acceptance assessment

`observe.c/.h` is bounded project-authored C11 admission for exact 16-byte TMU
replies, MIF/INT QoS request notifications and metadata extents in 8 KiB copied
FVMAP input. It preserves source units and table selection, rejects unavailable
and malformed/stale/error/unit-mismatched inputs, checks deadline overflow,
keeps host epochs/generations distinct from firmware correlation, and invalidates
pending/accepted observations on idempotent Stop. It emits no request and
contains no safe physical temperature/voltage/frequency limit.

Criterion 1: exact 20 Samsung inputs and E1S 0007 patch are pinned with hashes,
genuine declarations/units/selection qualified, and firmware/calibration/BYH3
unknowns explicit. Criterion 2: actual C and independent genuine source oracles
pass the final checks below, including signed QoS semantics. Criterion 3: scoped
implementation/docs, actual source/tool/command/artifact hashes, acquisition
failures, negative controls and this handoff are retained. All three host
criteria are assessed satisfied subject to coordinator review. No native
PWR-001 criterion or physical safety qualification is completed by this task.

## Exact source and test boundary

Samsung 417484173abc2c4fa93e738ea82ad9f2e84911b1 and E1S
c8860decc62c6d6180e609036d027a2997972420. Main references/artifacts remained
read-only; every reference Git call used no-lazy-fetch/optional-lock guards.
Missing public text was fetched into owned cache and checked against pinned
Git tree blob IDs and SHA256. Source-session2 has a real retained interrupted
HTTP read: IncompleteRead 15433 bytes, 790 more expected. Its two completed
verified inputs were retained; missing inputs were fetched separately into
source-session3, and source-session4 adds the genuine signed QoS header.
Full original notices stay in copied source/oracles. No blanket grant is inferred
for added E1S code and no full vendor implementation is committed.

The oracle compiles actual TMU/channel/FVMAP declarations, actual TMU read helper
and Linux unit statement, actual CMUCAL domain enumeration/list, and the actual
MIF/INT callback under synthetic transport/capture adapters. Its QoS capture
uses the exact s32 target prototype from the genuine public header. It never
links a real IPC sender, hardware function or QoS actuator. Genuine layouts and
prototype also compile independently as an ARM64 object.

## Actual evidence and retained qualification correction

Main-relative final runtime capsule:
`worktrees/pwr-003-20261105/artifacts/power-host/signed-final-session1/evidence.json`.
Actual runner exit 0, 70 checks, 207376 C assertions:

- 2048 TMU cases cover all 256 wire temperature values across all 8 source zones,
  checked against the genuine read helper and unit conversion.
- 14 clock cases use the actual callback and genuine signed target prototype:
  positive representation boundaries normalize to Hz; negative/default values
  never become fake frequency requests.
- 33 genuine source table selections and FVMAP extent groups exercise header
  prefix overlap, end-of-copy boundary, truncation and unavailable levels.
- 32 guard-page length controls and 100000 seeded arbitrary records execute
  under real native ASan+UBSan. Missing/failed transport remains distinct from
  an explicitly delivered zero-degree value. Ticket/time/unit/error/overflow/
  expiration and both pending/accepted Stop behavior are exercised.
- Deliberate heap-overflow and signed-overflow controls each exit 1 with the
  required ASan/UBSan diagnostics; linking alone is not runtime proof.
- Two inspected arm64-apple-ios16.5 Mach-O objects contain owned input code and
  genuine source layout/prototype checks. No XNU link, SDK or ARM execution.

Command, actual exit 0:

```sh
python3 src/platform/power/host/check.py --run signed-final-session1 --lab-root /home/egor/dev/pet/s24-ios-exynos
```

Final measured resident peaks: fixture compiler 69864 KiB, fixture 6496 KiB,
negative-control compiler 55316 KiB, owned ARM compiler 57232 KiB, genuine-layout
ARM compiler 48184 KiB. Only one compiler ran at a time; no heavy build lease.

POWERHOST-001 is a historical numeric baseline. Before committing, additional
primary-header review found its unsigned QoS capture did not model the genuine
s32 target; 0xffffffff is the DEFAULT_VALUE=-1 sentinel. POWERHOST-002 was
recorded inconclusive using `signed-review-session1/evidence.json`, retaining
its unmodified numeric PASS runtime and the header proof. The implementation
and oracle were corrected; POWERHOST-003 final evidence above supersedes those
acceptance assumptions. The source acquisition failure remains separate from
host runtime outcomes. Nothing was overwritten or relabeled as a device result.

A post-commit capsule binds the final tested source/profile bytes to the scoped
commit without repeating successful runtime checks.

## Integration and next concrete gate

Cherry-pick the owned commit, independently run the explicit component runner
with a fresh name and the cache path in README, then run primary `make check`.
Main unittest discovery does not automatically execute this source-local fixture.
No tests/fixtures or parent reserved files were modified. Retain original owner
until coordinator approval and completion through the primary ledger.

A real backend must qualify firmware/service/channel ownership and actual
sequence correlation, propagate real transport errors, bind fitted calibration,
obtain/match DT/ECT/FVMAP/ASV data, and verify native time/liveness and Stop.
Safe thermal/DVFS limits, charging and suspend policies must then have their
own measured/provenance-backed acceptance. Host input checks cannot authorize
hardware control or establish safe Android continuation.
