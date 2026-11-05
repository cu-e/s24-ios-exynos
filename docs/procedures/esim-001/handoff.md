# ESIM-001 handoff — 2026-11-05

Owner: `codex-team-esim-20261105-ak`.
Branch: `team/esim-001-20261105`.
Worktree: `worktrees/esim-001-20261105`.
Implementation commit: `bc2b6ec260c3235f6be30fc5ea63a6eaccfef9b0`.
Status: ready for coordinator review/integration; task remains in progress.

## Result and acceptance assessment

The separate active-profile, APDU transport and provisioning capabilities are
specified in README.md. Source pins and per-file hashes are recorded in
src/platform/esim/provenance.json; lpac and Qualcomm donor code were reviewed but
not copied. lpac APDU/HTTP separation informed the project-owned transport boundary.
Qualcomm iOS17 donor interfaces do not establish Samsung or iOS16.5 compatibility.

The real C component provides allocation-free bounded APDU parsing, explicit
injected transport, channel ownership, response/status separation, exchange
budget, at-most-once close/disconnect cleanup, sticky uncertain-ownership poisoning,
concurrent atomic cancellation requests and owner-thread operations. No backend
or activation is fabricated. Failed open with invalid handle poisons ownership,
even if the backend reports an error; only -1 explicitly guarantees no channel.
Cleanup failure does not silently reset ownership or trigger automatic reconnect.

Acceptance 1 is met at the host design/implementation boundary. Acceptance 2 is
met by exact source pins and executed synthetic-peer session/error/cleanup tests,
subject to coordinator review and main checks. This is not qualification of
physical transport, profile use/provisioning, Android RIL availability, Samsung
modem commands, selected iOS16.5 private services or native device execution.
All such report flags are false. ESIM-004 and CELL-009/010 paths were not edited.

## Executed evidence

Primary successful capsule:
`worktrees/esim-001-20261105/artifacts/esim-001/session5/evidence.json`.
SHA256: `80c28f663d0059731e9a032640a0268420e96e9423c49392b7baec02015e075e`.
Experiment ESIMHOST-005, planned before execution, uses the implementation commit
above and hashes all implementation/test/provenance/checker files and tools.
The adjacent report.json has detailed commands, qualifications and data layouts.

Actual invocation:

```sh
python3 src/platform/esim/check.py --run session5 --lab-root /home/egor/dev/pet/s24-ios-exynos
```

Exit 0; eight checks passed across 27 recorded commands. All commands returned 0
except two deliberately faulty standalone executables: signed-overflow UBSan trap
returned -4 (SIGILL), and ASan heap-overflow control returned 1 with an actual
AddressSanitizer heap-buffer-overflow diagnostic. The negative tests are isolated
from the module and do not use the phone. The UBSan control's LLVM IR contains
actual llvm.ubsantrap instrumentation.

GCC strict, NDK28 Clang UBSan trap and NDK27 native Linux ASan+UBSan each executed
all 11 scenario groups. ASan execution enabled leak detection and halt-on-error;
UBSan enabled halt-on-error. Native runtime archives came from the existing
NDK27 resource directory lib/x86_64-unknown-linux-gnu and are hashed in report.json.
No Android runtime was linked into glibc, package installed or global library fixed.
Actual PROT_NONE pages and synthetic peer canaries supplement sanitizer execution.
The concurrent cancellation test uses a real pthread and bounded synchronization.

Both actual aarch64-none-elf and arm64-apple-ios16.5 module objects compiled with
strict warnings. ELF section extraction and independent bounded Mach-O reading
agree on these values:

| Property | ELF / Mach-O |
| --- | --- |
| Session size / alignment | 96 / 8 |
| Cancel offset / atomic unsigned size | 60 / 4 |
| Transport / limits size | 48 / 12 |
| Compiler atomic-int lock-free macro | 2 |
| Maximum command / response / exchange count | 65544 / 65538 / 4096 |

Object compilation and matching layout do not establish a complete kernel link,
Apple SDK availability or any iOS service implementation. Source pin verification
checks actual clean tracked reference files and reviewed SHA256 values before
build. Source mismatch is a hard failure; the successful run does not inject
mutations into shared reference checkouts.

Preserved prior failures, all recorded in the main ledger:

- ESIMHOST-001 / session1: GCC sanitizer linker scripts reference missing lib64
  libasan.so.8.0.0 and libubsan.so.1.0.0.
- ESIMHOST-002 / session2: GCC strict passes; NDK28 lacks native Linux ASan archives.
- ESIMHOST-003 / session3: GCC/UBSan trap and intentional overflow pass; target
  compile fails on Android stdatomic.h requiring unavailable sys/cdefs.h.
- ESIMHOST-004 / session4: GCC, UBSan trap, native ASan+UBSan and intentional
  overflow controls pass; target compile finds signed channel-range comparison.
  The fix uses explicit int32_t comparison. C11 atomic unsigned is retained with
  actual compiler intrinsics, avoiding fabricated sysroot headers.

`git diff --check` and Python checker compilation returned 0 before the code
commit. Coordinator owns main integration and `make check`; this executor did
not claim that common check was performed or mark the task done.

## Limits and next steps

Callbacks must independently implement timeouts and quiescence. No C wrapper can
preempt a blocked synchronous callback or contain a backend buffer overrun.
Session initialization/lifetime must remain stable until cancellation requesters
join; reinitializing an active/poisoned session discards ownership and is forbidden.
An APDU primitive is not a provisioning permission filter. Caller framing is
required because valid short prefixes can also represent complete APDUs.

Coordinator: review/cherry-pick implementation plus handoff commit, inspect the
capsule, run main checks, then decide task completion. Next hardware-facing work
needs exact authorized Samsung transport discovery and timeout/reset/slot/channel
semantics, followed by explicit iOS16.5 frontend qualification. Do not wire this
primitive to production profiles or perform phone operations under this host task.
