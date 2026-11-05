# DRV-001 integration handoff

Date: 2026-11-05. Owner: `codex-team-touch-20261105-aj`.
Branch: `team/drv-001-20261105`.
Worktree: `worktrees/drv-001-20261105`.
Task stays `in_progress` until coordinator review, integration and main
`make check`. No device operation was issued by this task.

## Result and acceptance assessment

1. Protocol is independent of MMIO: project-authored `protocol.c/.h` parse
   exact STM records and adapt them to the existing shared UI-001 contract.
   There is no SPI, MMIO, IRQ, power or hardware callback in the implementation.
2. Actual compiled C parser and adapter pass 14 tests with no skips. Coverage
   includes 256 nibble pairs, all ten contacts, 1024 comparisons with the real
   corrected pinned donor decoder, malformed/truncated/oversize input,
   inclusive coordinate ranges, unsupported IDs/actions/types, 4096 seeded
   arbitrary records, initial cancellation, acknowledged delivery/retry/Stop,
   loss/desynchronization, monotonic time, sequence exhaustion, callback
   reentrancy, rotations and existing 40-byte UI event wire decoding.
3. Device power, IRQ, SPI integrity, firmware identity, calibration, real sensor
   behavior, suspend/wake and native Apple HID dispatch remain unverified.
   The source profile, README, procedure and evidence repeat these limits.

All three host-task criteria are assessed satisfied, subject to coordinator
review. This is not a native S24 touch driver qualification.

## Sources and reuse

Read-only Samsung source pin:
`417484173abc2c4fa93e738ea82ad9f2e84911b1`.
Read-only E1S donor pin:
`c8860decc62c6d6180e609036d027a2997972420`.
The existing RES-007 analysis, UI-001 contract and UI-006 nibble correction are
reused without changes. `source-profile.json` contains exact primary-file
hashes, direct pinned URLs, layout details and licensing qualifications.
No full donor/Samsung implementation is added to tracked code. The actual
donor pure-decoder extraction remains in ignored local evidence. Unmodified
primary source blobs retain their existing notices, including the Samsung
GNU GPL version 2 notice; source repository license context is retained. No blanket
license is inferred from the surrounding XNU source tree.

## Actual validation and retained failures

All evidence paths below are relative to the main laboratory checkout.

- `worktrees/drv-001-20261105/artifacts/stm-host/initial-session1/evidence.json`:
  STMHOST-001 failed with the real initial test exit1. A handwritten wet-type
  fixture used the wrong type bits, and two Python ctypes calls passed a
  bytearray rather than bytes. The original bytes/diagnostics are retained;
  the test harness/fixture was corrected.
- `worktrees/drv-001-20261105/artifacts/stm-host/qualified-session1/evidence.json`:
  STMHOST-002 passed all14 tests but failed to link NDK28 Clang19 ASan because
  native Linux runtime archives were absent. No sanitizer runtime is claimed
  for this capsule.
- `worktrees/drv-001-20261105/artifacts/stm-host/qualified-session2/evidence.json`:
  STMHOST-003 passed actual NDK27 Clang18 ASan+UBSan and ARM64 checks. USB worker
  identified the existing host compiler/runtime; no package was installed.
- `worktrees/drv-001-20261105/artifacts/stm-host/final-session1/evidence.json`:
  STMHOST-004 is the final exact-source capsule, exit0 and13 passing checks.
  The runner retains actual nested compiler commands/exits and the real
  corrected donor extraction. The C guard fixture passes18 edge lengths and
  100000 random records under ASan+UBSan. A deliberately faulty heap-overflow
  control exits1 with an ASan report; a signed-overflow control exits1 with a
  UBSan report. Both negative failures are required and expected. Two actual
  arm64-apple-ios16.5 Mach-O objects compile and are inspected successfully;
  neither is linked to XNU or executed on ARM.

Final run command, actual exit0:

```sh
python3 src/platform/input/stm/check.py --run final-session1 --lab-root /home/egor/dev/pet/s24-ios-exynos
```

The run records its base checkout commit and exact tested file hashes/copies.
A post-commit evidence capsule binds those tested bytes to the final owned
commit without repeating successful runtime tests.

## Integration and next work

Cherry-pick the owned commit, then run the coordinator's common `make check`.
The unit test normally skips only the differential donor comparison if local
references are absent; the recorded final run explicitly used main references
and required all14 tests without skips. `check.py` requires exact pinned
primary source blobs and a fresh artifact prefix.

There is no known host-test failure remaining. A native backend must serialize
calls, supply monotonic nanoseconds, retain input while the sink is busy,
report loss and guarantee that a declined sink publishes nothing. It must
fully dispatch cancellation before acknowledging it. Silent lost FIFO records
and partial native writes cannot be solved by this pure parser. UI-004/005
remain the gates for physical SPI/IRQ/power bring-up and native HID dispatch.
Any such phone action needs its separately authorized hardware task; this
handoff authorizes none.
