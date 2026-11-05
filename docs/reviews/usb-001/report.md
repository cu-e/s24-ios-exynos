# USB-001 independent review

2026-11-05 · reviewer `codex-team-review-usb-20261105-ao` · REV-001.

Reviewed implementation: **`e1785878045751213cb1e8e49e42a364333ed496`**.
Result: **one P2 source-profile completeness finding; no P0/P1 or protocol
correctness defect reproduced within the documented host contract.** Correct
USBREV-F01 before accepting the task's exact-board-input completeness claim.
This is a bounded source/host review, not native USB qualification.

## USBREV-F01 — P2: include the second enabled repeater in exact-source inputs

Affected implementation locations:

- `src/platform/usb/profile.json:70` (singular TUSB-only repeater profile).
- `docs/procedures/usb-001/README.md:38` (TUSB-only retail-source description).
- `src/platform/usb/check.py:76` (source check only requires TUSB tokens).

The exact pinned retail file
`arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r17.dts` at
`f85e53cfa5497ead5d78821efbac84e51f37a4e1` declares **both**
`tusb2e11-repeater@3E` and `ptn3222-repeater@4F` under `hsi2c_34`, each with
`status = "okay"`. The second declaration is at donor lines 3418–3425;
neither declaration is inside a preprocessor conditional. The comparison pin
has identical bytes. This does not establish which alternative is fitted or
selected on the owner's phone or newer BYH3 firmware.

The profile records only TUSB2E11 at `0x3e`. A future native implementation
using this advertised exact-source profile can omit the PTN3222 alternative
and its distinct tuning/identification requirements. The runner still reports
pass because it tests only TUSB's presence. This is a completeness defect in
the first USB-001 acceptance criterion; it does not invalidate the C block
protocol or demonstrate a physical USB failure.

Reproduction, using already hash-verified pinned source bytes:

```sh
cd /home/egor/dev/pet/s24-ios-exynos/worktrees/rev-usb-20261105
python3 docs/reviews/usb-001/check_repeater.py
```

The command exits 0 and emits both unconditional enabled source nodes, the
source SHA256 `7bf8fc934d2336d6610d7cf31261b26cb9bfa47da0f8a1bd36fcfafc50171fbf`,
and the profile omission. The complete source can also be reproduced with
`git show f85e53cfa5497ead5d78821efbac84e51f37a4e1:arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r17.dts`
in `references/s24-bsp-reference`.

Requested correction: represent both source-declared repeater alternatives
and their addresses in the profile/procedure, explicitly retain unknown
fitted/live selection, and strengthen completeness validation so omission of
either alternative fails. Do not infer that both physical parts are present.
Original implementation remains untouched by this reviewer.

## Reviewed boundaries and evidence

`readonly.c:13` validates geometry before later division/modulo; `:19` checks
extents using subtraction after offset admission. `:57` bounds complete
request frames and `:61` bounds output before calling the trusted reader.
Client multiplication is admitted before evaluation at `:94`. Wire integers
are decoded bytewise, avoiding alignment-dependent struct reads.

At `:62`, a request id is consumed before backend execution; capacity failure
does not consume it. The in-flight flag survives callback disconnect until
the callback returns. Failed, short, overreported or disconnected reads scrub
the bounded response and emit zero outgoing bytes. Client disconnect clears
pending state; mismatched replies close the session before exposing a borrowed
view (`:102`). Increasing reconnect sessions and exhausted request ids prevent
reuse within one state lifetime. These guarantees require the documented
single owner, independent state storage, truthful buffer extents and bounded
synchronous callback. The code has no concurrent native Stop/cancel mechanism.

The arithmetic helper at `:119` admits an entire CPU/bus window and its slice;
it creates no DMA mapping and proves neither cache coherency nor DMA stop.
No out-of-bounds or wraparound counterexample was reproduced under that API.

Independent verification, performed after registering USBREV-001:

| Check | Actual result |
|---|---|
| Original host-session5 artifacts | All 107 recorded hashes match; three committed summary links also match |
| Exact executable/source configuration snapshot | Seven committed files match original witness byte-for-byte; original evidence's `ca68d2b...` is its baseline, not the final implementation commit |
| Donor provenance | Both full source pins and 18 extracted file hashes/lengths verified |
| Existing fixture rebuilt from reviewed commit | 63,482 assertions and 20,000 mutation inputs pass under actual ASan+UBSan; owned read-only image hash unchanged |
| Sanitizer negative controls | Both execute, exit 1, and emit expected heap-overflow/signed-overflow diagnostics |
| Independent Python interval oracle against compiled C | 63,865 DMA cases: 5,800 admitted, 58,065 rejected, zero mismatches; rejection leaves output unchanged |
| Resources | Sequential compilers; peak child RSS 81,548 KiB; each command bounded to 45 seconds |

Host compiler: existing NDK27 Clang 18.0.2, upstream LLVM revision
`d8003a456d14a3deb8054cdaa529ffbf02d9b262`, x86_64 Linux target. Full actual
commands, exits, versions, snapshots, logs and hashes are in
[evidence.json](evidence.json); local artifacts remain ignored. Existing ARM
ELF/Mach-O objects and logs were hash-audited, not recompiled or executed by
this review. Test counts and sanitizer success establish bounded host evidence.

Source attribution is explicit and pinned. Selected DTS/driver files retain
GPL-2.0 notices; the older generic binding carries GPL-2.0-only OR BSD-2-Clause.
The small owned C boundary imports no vendor driver code, vendor headers or
symbols. This review found no incorporation requiring a missing vendor notice;
it is not a legal opinion or a grant for future donor reuse.

## Remaining scope and disposition

No phone, ADB, root, MMIO, flash, emulator or installation was used. USB
enumeration, endpoint streaming/MSC/UASP, PHY/clocks/interrupts, actual DMA,
native kernel/framework integration, private Apple USB ABI, root mount and
automatic return to Android remain unqualified. Session freshness across
process restart, authentication, receive assembly, deadlines and hardware
watchdog/cancellation are explicitly external future requirements. A valid
S24R reply alone provides no cryptographic payload integrity.

The coordinator owns shared repository checks and integration acceptance.
REV-001 remains in progress pending correction review and coordinator
acceptance; the reviewer does not complete USB-001 or REV-001.
