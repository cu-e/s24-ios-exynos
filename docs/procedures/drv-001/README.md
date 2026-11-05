# STM protocol and acknowledged host adapter

DRV-001, owner `codex-team-touch-20261105-aj`. Host-only; no device command,
MMIO, SPI transfer, IRQ handling, firmware download or power operation.

The source boundary is `src/platform/input/stm`. Its parser consumes an exact
16-byte STM FIFO record. Its adapter emits the existing project UI-001 event
boundary and uses the existing display/input contract for normalization and
contact transitions. It does not duplicate or replace a native SPI backend.

Primary inputs are Samsung s24-linux `417484173abc2c4fa93e738ea82ad9f2e84911b1`
(`stm_dev.h`, `stm_core.c`, `stm_reg.h`), E1S s24-port
`c8860decc62c6d6180e609036d027a2997972420`, and the already qualified project
coordinate correction in `patches/display-input`. Protocol fixtures are
project-authored synthetic bytes, never phone captures. Preserve source
licenses; protocol facts do not establish a blanket redistribution grant for
the E1S source additions. Generated upstream test extracts stay in artifacts.

The parser rejects truncated records, unsupported coordinate types/actions,
invalid contact IDs and coordinates outside a selected inclusive range.
The adapter requires an acknowledged cancellation on attachment, refuses
MOVE/UP without DOWN, retains rejected output for retry, and invalidates its
stream on loss/malformed input or known controller error/reset status.
Cancellation must be acknowledged before contacts clear or Stop completes.
Callback failure means no output was published; native partial-I/O handling
must provide that transaction guarantee before using this boundary.

Register experiments before tests. Check real parser vectors and malformed
inputs, all ten contacts, loss/retry/cancellation/reentrancy, monotonic time
and sequence exhaustion. A differential control compiles only the corrected
donor pure decoder through the existing UI-006 extraction helper. Compare
coordinate interpretation, not the donor's implicit MOVE-to-DOWN policy.
Bounded sanitizer and ARM64 compile checks use owned code and fixtures.

Device power, IRQ delivery, controller firmware identity, SPI timing and
transfer integrity, sensor behavior, calibration, wake/suspend and native
iOS16.5 HID dispatch remain unverified. The API is an owned host boundary,
not Apple HID wire ABI and not a working native S24 touch driver.

Reproduce the bounded evidence capsule from the integration checkout:

```sh
python3 src/platform/input/stm/check.py --run fresh-name --lab-root /home/egor/dev/pet/s24-ios-exynos
```

Use a fresh run name; artifacts are never overwritten. The runner reads pinned
references from the main laboratory and stores tested source copies, hashes,
compiler identities, commands, exit codes and diagnostics. It performs no
reference checkout mutation. `--clang` selects an existing host compiler; the
current default `/home/egor/.local/bin/clang` resolves to NDK27 Clang18 with
native Linux ASan/UBSan runtime archives. NDK28 Clang19 on this host lacks the
host ASan archives and is a retained failed experiment, not a successful
sanitizer execution. Android runtime archives are not substituted on Linux.
The intentionally faulty ASan and UBSan control programs must exit nonzero
with their expected diagnostics; those expected failures validate detection.
ARM64 objects are compile-only, unlinked Mach-O files using Clang resource
headers rather than an Apple SDK or proprietary binary.
