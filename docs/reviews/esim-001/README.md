# Independent ESIM-001 review

Reviewer: `codex-team-review-esim-20261105-aq`; task `REV-003`.
Implementation reviewed: `9daf884467c1fe0b816a53dafe86675587570605`,
including implementation commit `bc2b6ec260c3235f6be30fc5ea63a6eaccfef9b0`.

## Result — 2026-11-05

**No P0, P1 or P2 finding was identified within the reviewed host boundary.**
The two implementation commits are suitable for coordinator integration review,
subject to the coordinator's primary-checkout `make check`. This conclusion is
bounded by the documented owner-thread, valid-buffer and cooperative synchronous
backend contract. It does not qualify a physical eUICC, provisioning, an active
profile, a Samsung transport or the selected Apple iOS16.5 frontend.

No implementation files were edited. The review task remains in progress pending
coordinator acceptance.

## Scope and source assessment

Reviewed all of `src/platform/esim/session.c`, `session.h`, `check.py`, tests and
`provenance.json`, both ESIM-001 procedure documents and the original session5
capsule at the exact tip above. The tip contains the stated implementation commit;
the implementation worktree had no tracked changes during reproduction. Existing
session5 evidence correctly names the earlier implementation commit: the later
tip adds the handoff rather than changing those measured source bytes. All source
hashes in its report and all 66 capsule artifact hashes matched actual files.

Both local reference revisions and every file hash in `provenance.json` matched:

- lpac `a43e46aef6f8b5b1d144bf3b3fc5999d8fcefacc`: actual `euicc/interface.h`
  separates APDU and HTTP callbacks and has a `uint8_t` close parameter.
  `REUSE.toml` supports the stated library LGPL-2.1-only/commercial, driver
  AGPL-3.0-only and document MIT boundaries.
- QcomBaseband `dd0199cf3300764ed52b23f4a47761f91fab21a2`: the actual BSD-2-Clause
  LICENSE, donor header SPDX notice and pinned `UPSTREAM.json` agree with the
  provenance description. Its source inventory pins the original Trogdor donor
  at `58b5bc8bfc04482014ff403078435e581e58a5b0`. The reviewed owned module does
  not copy that donor's provisioning/state-machine implementation. No upstream
  license notices were replaced or removed.

## Correctness and lifecycle assessment

Line numbers below refer to the exact implementation tip, not this review tree.

| Boundary | Inspected source | Assessment and independent check |
| --- | --- | --- |
| APDU cases and integers | `session.c:3`, `session.c:8` | Length is bounded before packet reads. Short and extended case lengths must match exactly; 16-bit fields are read explicitly in big-endian order without unaligned integer loads. Zero Le expands to 256/65536. Data extents fit the chosen 32-bit metadata. Exhaustive 16-bit Lc/Le generation and malformed adjacent lengths passed. |
| CLA and channel meaning | `session.h:48`, `session.c:156`, `session.c:195` | Handles 1..255 are explicitly opaque local identifiers, not a claim that a card has 255 logical channels. No narrowing occurs before the range test. All 256 CLA bytes were passed through unchanged with local handle 255; the component promises no CLA encoding, privilege or command semantics. A real backend must qualify those separately. |
| Response extent/status | `session.c:181`, `session.c:193`, `session.c:199` | Reply metadata starts cleared; effective capacity is clamped before callback; reported length is checked before status-word indexing. A card error 6985 remains a successful transport exchange with that status, rather than fake provisioning success. Original short/oversized response, capacity, canary and guard-page tests were reproduced. |
| Partial ownership | `session.c:74`, `session.c:151`, `session.c:160` | Even failed connect receives one disconnect attempt. A valid partial open handle receives close then disconnect; failed open with -1 is the sole no-channel guarantee. Other invalid/ambiguous handles poison ownership. Independent controls covered INT32_MIN, -2, -1, 0, 1, 19, 20, 255, 256 and INT32_MAX with success/failure statuses. |
| Cleanup and primary errors | `session.c:74`, `session.c:99`, `session.c:211` | Ownership flags clear before callbacks, preventing recursive/double cleanup. Close failure still permits one disconnect attempt; uncertainty stays POISONED and repeated end does not retry. Primary exchange status and first cleanup status remain separate. The combined close/disconnect/exchange error matrix passed. |
| Cancellation and reentrancy | `session.c:55`, `session.c:66`, `session.c:197`, `session.c:223` | Cancel uses actual acquire/release atomics. Only the requester operation is concurrent; the original real-pthread cancellation case passed. Independent controls exercised cancellation and owner-operation BUSY responses during all five callback phases, including close/disconnect. A late cancelled response is not published as success. |
| Bounded execution | `session.c:123`, `session.c:191`, `session.h:48` | Bytes, exchanges and cleanup attempts are bounded. Wall-clock termination is explicitly a backend obligation; the wrapper cannot preempt a blocked callback or undo a backend write. There is no fabricated timeout/watchdog/recovery claim. |

Initialization is a fresh-lifetime operation: `session.c:114` resets the structure.
As documented, active or poisoned sessions must never be reinitialized to bypass
ownership; requesters must join before lifetime changes. The code is not a
defense against callers violating those preconditions, invalid C pointers,
concurrent owner operations or a backend writing beyond supplied capacity.

The parser needs complete caller framing: a truncated stream that happens to form
a valid 4-, 5- or 7-byte APDU cannot be distinguished from that complete command.
It validates shape and extents, not authorization, APDU command meaning, secure
messaging, a physical channel range or response length semantics for each INS.
These limits are already explicit in the implementation procedure and are not
reported as new findings.

## Actual independent reproduction

Experiment `ESIMREV-001` was registered in the primary registry before executing
verification. Actual invocation from the reviewer worktree:

```sh
python3 docs/reviews/esim-001/reproduce.py review1
```

Exit 0 on `2026-11-05T13:41:16.537649+00:00`; 27 commands and seven review checks.
Every command returned 0 except the two deliberately faulty sanitizer controls:
ASan heap overflow returned 1 with an actual `heap-buffer-overflow` diagnostic;
UBSan signed-overflow trap returned -4 (SIGILL). Compilation was sequential,
maximum measured child RSS was 71,996 KiB, and every subprocess had a 45-second
timeout. No packages, global libraries, references or implementation files changed.

- Rebuilt the original eleven synthetic scenario groups against exact source
  bytes with existing native NDK27 Clang 18, ASan, UBSan and leak detection.
- Independently authored [boundary_probe.c](boundary_probe.c) passed 263,165
  parser cases and 324 synthetic sessions, including all short lengths,
  exhaustive 16-bit extended Lc and Le fields, exact/adjacent framing, endian
  metadata, all CLA bytes, handle extremes and combined cleanup/cancel states.
- Rebuilt actual module and layout-probe objects for `aarch64-none-elf` and
  `arm64-apple-ios16.5`; an ELF section dump and separate bounded Mach-O reader
  agreed on session size/alignment 96/8, atomic offset/size 60/4, transport/limits
  sizes 48/12, lock-free macro 2 and limits 65544/65538/4096.

The independent runner [reproduce.py](reproduce.py) records exact commands,
stdout/stderr, exits, date, implementation and review-input hashes, compiler/tool
and native sanitizer archive hashes, measured peak RSS and layout values. It reads
implementation files and places every generated output in the reviewer worktree.
Use a fresh run name when reproducing. The original full checker was inspected
but not rerun because its output directory belongs to the implementer and its
NDK28 path is currently unavailable; existing NDK27 provided actual independent
host sanitizer and ARM object evidence.

Local evidence:
`worktrees/rev-esim-20261105/artifacts/rev-esim-001/review1/evidence.json`.
The adjacent `report.json` and stdout/stderr files contain the actual commands
and results. The original session5 hashes were verified rather than rewritten.
Host compilation of an iOS-targeted Mach-O object uses no selected Apple SDK or
private service, and matching data layouts establish neither a kernel link nor
Apple frontend compatibility. These tests use only synthetic callbacks, with no
phone, ADB, root, provisioning APDU, MMIO, flash or reboot operation.

## Review procedure

Read only the exact implementation worktree, its session5 evidence capsule and
the pinned local lpac/Qualcomm reference files. Inspect APDU case framing,
integer/extent/endian handling, opaque local handles versus physical channels,
CLA pass-through, cancellation/reentrancy, poisoning and cleanup ownership.
Verify reviewed source hashes, evidence hashes and actual ARM object constants.

After registering ESIMREV-001 in the primary registry, independently rebuild and
execute the original synthetic scenarios with existing native Clang ASan/UBSan,
then run a separately authored APDU grammar and cleanup/CLA matrix. Reproduce
sanitizer negative controls and ARM ELF/Mach-O compile/layout controls using the
existing NDK27 tools, sequential compiler invocations and no hardware access.
Save exact commands, exits, hashes and outputs in this review worktree. Do not
write implementation/reference bytes or run the implementation checker, whose
default outputs belong to the implementation worktree.

The final report and handoff will state findings, observed results and limits.
Host synthetic evidence cannot qualify provisioning, physical eUICC transport or
the selected Apple iOS16.5 frontend. Keep the review task in progress until the
coordinator accepts it.
