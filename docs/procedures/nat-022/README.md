# NAT-022: framebuffer-marker canary and instrumented loader (host work only)

Evidence kind: **host-test** for the build and the tests; **native-device** for the three
owner-attended runs recorded below (`native-attempt-001-evidence.json`, inconclusive;
`native-attempt-002-evidence.json`, the first decoded on-device markers;
`native-attempt-003-evidence.json`, the exception path decoded from the screen). Sections written
before a run describe the plan, not the outcome; read the dated result sections for what the
phone did.

## Why

NAT-021 ended inconclusive: the owner saw only the Samsung/Knox logo and a
restart. `start.S` silently `halt`s before any logging or watchdog when
SCTLR_EL1.M or .C is set (or CurrentEL is not 1/2). Nothing proves the phone got
there; equally nothing excludes it. The loader's RAM log is lost across reset and
the NAT-016 archive has no producer. The smallest independent signal is the
framebuffer S-Boot leaves behind, recorded by a camera.

## What is built (`build.py`, reproducible; hashes in `artifacts/nat-022/build-001/build.json`)

| Image | Purpose |
| --- | --- |
| `canary-plain` | XNU-free. Draws an ENTRY marker (EL, SCTLR M/C/I of the current EL and of EL1), a counter-derived boot id, a stack round-trip check, then repeats. No MMIO except framebuffer stores. |
| `canary-fault` | Same, then `BRK #0x1234` after three rounds to prove the vectors, exception stack and ESR/ELR/FAR/slot report (expect EC 0x3c, ISS 0x1234). |
| `loader-diag` | The NAT-020 build-003 loader with `patch_loader.py`: entry marker before any decision; the M/C/EL halts become `mk_gate_halt` (marker, then halt); stage markers `loader_main`, FB selected, window chosen, RAM zeroed, segments copied, ADT built, pre-jump; loader exceptions report ESR/ELR/FAR. Marker drawing is skipped unless the loader's validated framebuffer equals the marker region. |

`loader-diag` is the unmodified payload path plus markers; it is **not** an
authorised run. Packaging into a RECOVERY image would use the NAT-006 builder and
needs the decision below; it was not done.

## Marker encoding (`src/marker.h`, `decode.py`)

A 32-bit frame `kind|idx|data16|crc8` is drawn as 34 contiguous 256 KiB bands from
the bootargs framebuffer address `0xFA200000` (NAT-005): band 0 all-ones, band 1
zero, bands 2..33 the bits. Contiguous bands do not depend on the unknown pixel
format (one-bits are `0xFFFFFFFF`, zero-bits `0`) or row stride; the decoder only
needs a stride hypothesis to map photographed rows to bands and tries several,
accepting a hypothesis only when sync contrast and CRC validate. Frames change
every 1.2 s. Kinds: ENTRY, BOOTID (CNTVCT[31:0], nonce-like, not guaranteed
unique), STAGE, ESR/ELR/FAR (4 frames each), SLOT, CHECK. A STAGE "pre-jump" frame
is explicitly **not** evidence of kernel entry; `MK_ST_XNU_ENTRY` is reserved for
a marker executed inside XNU's first instructions (follow-up, see below).

## Host tests (`test_nat022.py`, 12)

They run the real `markerlib.c` against a RAM buffer and check it with the
independent Python decoder: CRC agreement, buffer-to-frame decoding for every
scenario, incremental redraw correctness, entry-field decoding, the gate being
non-silent, exception record round trip, pre-jump labelling, three row strides with
noise, corrupt-CRC and low-contrast rejection, and the DTB/image overlap guard.
They show the encoder and decoder agree. They do not show the display will scan
out this memory, show colours as assumed, or that the AArch64 assembly start path
behaves as intended on silicon: no AArch64 emulator is available on this host.

## Unknowns the canary exists to resolve

1. Whether the panel still scans `0xFA200000` at loader entry (Knox logo may come
   from a different buffer; command-mode panels may need an explicit refresh).
2. Pixel order/alpha: if a zero word shows as non-black, the sync contrast check
   fails and the frame is rejected rather than misread.
3. Row stride (NAT-005: not determinable from the DT).
4. Whether entry is with MMU/caches on; with M=1 all stores are best effort.
5. Whether the image or DTB really sits clear of the marker region (guarded).
6. How a run terminates: the canary arms **no** watchdog and touches no PMU. If
   S-Boot's own supervision does not reset the phone, recovery needs the
   hardware key combination. NAT-011 (PMU SWRESET) is blocked and not used.

## Staged XNU attach plan (not authorised, not built)

1. Canary plain, then canary fault: entry state, privilege, stack, vectors, one
   independent marker. Decide from what is seen; no retry loops.
2. `loader-diag` with the existing payload: markers up to *pre-jump*. A last
   marker proves only that the loader finished.
3. Separate host task (NAT-023 proposal): a position-independent marker stub at
   the Mach-O entry of the kernel copy, preserving the displaced instructions, so
   a `MK_ST_XNU_ENTRY` frame can only be drawn by code inside XNU. Needs the
   entry symbol/offset from the existing kernel and a patch with a base hash.
4. On exception, the frames above give ESR, ELR and FAR to map to an
   instruction/address through the kernel symbols.

## Decision request for the owner (NAT-017/NAT-021 gate)

Required before any phone action; this document is not that decision.

* **Exact images:** the three SHA-256 values in `build.json` (to be packaged
  into a RECOVERY image with the same NAT-006 builder, hash recorded then).
* **Sequence:** one native session per image, canary-plain first, one RECOVERY
  write with full readback, one `adb reboot recovery`, bounded observation with a
  camera, then stock restore as in NAT-021 (fixed-stock `session.py --restore`
  or NAT-013 in Download Mode). No retry of an inconclusive image.
* **Mandatory boundary:** Android, apps, settings, accounts and user data stay
  intact; only RECOVERY is written; no data/reset prompt is answered.
* **Risks:** wrong-mapping stores if M=1; a hang that needs the hardware key
  combination (unverified); display flicker; markers that never appear
  (inconclusive, not a failure of the phone).
* **Recovery:** NAT-021 showed physical Download Mode plus NAT-013 restored stock
  RECOVERY and Android on 2026-11-10; this is a precedent, not a guarantee.

## Native result, 2026-11-10 (decision 0009): inconclusive

`canary-plain` was written to RECOVERY (readback matched) and booted once
(request 12:11:16Z). The owner, filming the screen, reported seeing no stripes
and moved the phone to Download Mode because it kept restarting. The host saw
USB vanish at +4 s and `SEC_UPLOAD` at +95 s (12:12:51); no command was sent to it.
It left at 12:13:37 and Download Mode appeared at 12:13:42 (owner action). Stock
RECOVERY was restored with one NAT-013 session; the full hash equals stock and
Android booted (`sys.boot_completed=1`; user state `RUNNING_LOCKED` until unlock).
Full record: `native-attempt-001-evidence.json`.

Established: the framebuffer markers were **not seen**; the same reset/upload
pattern as NAT-021 occurred even though this image arms no watchdog (so the ~95-110 s
reset is not ours). Not established: whether our first instruction ran. Untested
explanations: image not executed; M=1 entry with a failed best-effort draw; panel
not scanning `0xFA200000` or needing an explicit DECON trigger (command-mode
panel); contrast invisible. No further native run is authorised. The next
information must come from host/Android-read-only work (e.g. how S-Boot's own
splash is scanned out) or from a new owner decision for a different channel
(UART, early USB, or a DECON-triggering variant).

## Post-run source review: the channel was probably unable to show anything

Host source-review only, from existing project records; it does not explain the
run, it narrows hypothesis (c). `research/notes/native/UI-007-decon-boot-window.md`
records, from this phone's runtime FDT, `DECON0 op_mode = 1` (command mode), and
that the DPP DMA reaches memory through `/sysmmu@19840000` (bypass state unknown).
A command-mode panel keeps its last frame in its own GRAM and is refreshed only
when DECON issues a frame transfer. So even a canary that ran correctly could
not make a framebuffer-only marker visible without (1) a DECON frame trigger and
(2) the DMA address being the physical `0xFA200000` (SysMMU bypass). The NAT-022
design did not account for this; `canary-plain` never issued a trigger. The
same reasoning applies to the loader UI never being seen in NAT-021. This is
consistent with the no-stripes report but equally with the other untested causes;
it is not evidence that the canary executed.

The register that triggers a frame transfer was then pinned from the BSP:
`decon-trigger-facts.md` (source-review, SHA `f85e53cf…`). DECON0's DT says
**hardware** trigger (`trig_mode 0`, TE from DDI0), so the earlier "software
trigger" wording above was an assumption. Writing it from the canary is MMIO and
is outside decision 0009; see "canary-trig" below.

## canary-trig: DECON0 kick variant (host-tested; run once under decision 0010, result below)

`build.py` also builds `canary-trig` (`markerlib.c` with `-DMK_TRIG=1`). It is the
`canary-plain` loop plus, after every drawn frame, one DECON0 kick
(`mk_kick`, `src/markerlib.c`), following the vendor driver
(`decon-trigger-facts.md`): read `GLOBAL_CON`, `TRIG_CON`, `FRAME_COUNT`;
mask the trigger; set `SHD_REG_UP_REQ` bit 31 (read-modify-write); unmask. Odd
kicks use the HW-trigger form, even kicks the SW-trigger form, because the DT is
not register truth.

Properties asserted by host tests (`test_nat022.py::Trigger`, fake register file):
the first framebuffer marker is drawn before any MMIO; the only registers touched
are `FRAME_COUNT`, `GLOBAL_CON`, `TRIG_CON`, `SHD_REG_UP_REQ`, and the only ones
written are `TRIG_CON` and `SHD_REG_UP_REQ`; nothing is written when DECON is not
enabled, is in video mode, when the MMU is on, or after an earlier kick faulted
(`mk_kick_state` stays 1, so an exception cannot loop on the same fault). The
registers read are drawn as `REG` frames (`MK_REG`, decoded by `decode.py` into
`decon`: kick status, `GLOBAL_CON`, `TRIG_CON` before/after, `FRAME_COUNT`
previous/now), so a visible run reports what S-Boot left behind. The
`canary-plain` and `canary-fault` Images are byte-identical to the ones built
before (`7bc1b01d…`, `38a4feba…`).

The generated code, read from `zig cc -S`, forms one base `0x19100030` and uses
offsets `-16`, `0`, `-44`, `+32` from it, i.e. `GLOBAL_CON`, `TRIG_CON`,
`FRAME_COUNT`, `SHD_REG_UP_REQ`; it stores only at offsets `0` and `+32`.

Not shown by any host test: that the image runs on the phone, that DECON0 is
powered and enabled when the recovery kernel is entered (a read of an unpowered
block can hang the bus), that the panel's TE is present, that the DPP window
points at `0xFA200000`, or that the SysMMU lets it scan that address. A visible
result would be the first independent marker; a blank result stays inconclusive
for the same reasons as run 001.

Decision: put to the owner with the exact SHA-256 and accepted as
`docs/decisions/0010-nat022-canary-trig-single-run-2026-11-10.md`; `session_trig.py` refuses to
run without it and wrote its own one-shot marker `artifacts/nat-022/native-attempt-trig-used.json`.
That decision is consumed; another run needs a new one.

## Native result 002, 2026-11-10 (decision 0010): markers decoded from the owner's recording

`canary-trig` (canary Image `572ebd0f…`, RECOVERY image `f2cc234a…`) was written to RECOVERY with a
matching readback and booted once (`adb reboot recovery` at 12:34:31Z). The owner filmed the screen
and reported seeing stripes. Stock RECOVERY was restored with one NAT-013 session; the hash equals
stock (`96620b8b…`) and Android booted (`check_android` pass). Record:
`native-attempt-002-evidence.json`.

`decode_video.py` (host analysis of the recording, not a console) decodes the video: from 2.1 s to
61.8 s, 857 sampled frames are CRC-valid, no frame has two different values within a round, and
the order is exactly the canary-trig loop (CHECK, ENTRY, BOOTID 0/1, STAGE, REG 0..9; four rounds
of about 18.3 s). The screen goes dark at about 61.9 s. The decoder fits `y = y0 + u K/(1 + q K)`
with bloom to the sub-pixel transitions, so camera perspective and white-run bloom are handled and
the framebuffer stride is not assumed; a frame is accepted only on sync plus CRC-8.

| Field | Decoded | Meaning |
| --- | --- | --- |
| CHECK | `0xA5A5` | stack round trip in the canary succeeded |
| ENTRY | `0x8900` | entry at **EL2**; current-EL SCTLR M=0 C=0 I=1; EL1 SCTLR M=0 C=0 I=1 |
| BOOTID | `0x1AE1D195` | CNTVCT[31:0] when the loop started, constant across rounds |
| STAGE | `0x10` | canary stage C reached via a call |
| REG GLOBAL_CON | `0x113` (kick 6), `0x133` (kicks 21, 36) | bits 0, 1 (DECON enabled) and 8 (command mode) set, as in the DT; the other bits are not interpreted |
| REG TRIG_CON | `0x3063→0x3062` (SW-form kick), `0x3062→0x3063` (HW-form kick) | readback follows our writes; mask bit 4 clear, bit 8 not set in the readback; bits 5, 6, 12, 13 set before and after |
| REG FRAME_COUNT (low 16 bits) | 163→314, 1358→1358, 2407→2557 | interval before kick 6 / 21 / 36 (kicks 5→6, 20→21, 35→36) |
| REG kicks | 6, 21, 36 | matches the loop |

What this establishes (observation of the screen, decoded independently of the C encoder): our
XNU-free code ran on the phone, at EL2 with the MMU and D-cache off, with a working stack; DECON0
was enabled and in command mode at the reported kicks (6, 21 and 36, between about 7 s and 40 s after
entry; `GLOBAL_CON` bit 5 changed between kick 6 and kick 21, so the block is not static); reads and
writes to the four DECON0 registers completed without a fault (no exception record appeared); the display scans our buffer starting at `0xFA200000` with all-ones
shown as white and zero as black. It is the first independent on-device marker of the project and
satisfies step 3 of the diagnostic-loader plan except the exception-handler part, which only
`canary-fault` can show (not run).

Consistent with the counts but not proven: `FRAME_COUNT` grew by about 150 in each interval after a
HW-form kick (kicks 5→6: 151; kicks 6→20 over 7 such intervals: 1044; kicks 21→35: 1049; kicks
35→36: 150) and by 0 in the interval after the SW-form kick (20→21), i.e. the engine appears to be
frame-clocked at about 120 per second while `HW_TRIG_EN` is set. The value 163 at kick 5, with two
earlier HW-form kicks, is not explained.

Not established:

* That the DECON0 kick, not S-Boot's own refresh, made the markers visible. The `canary-plain`
  run (decision 0009) wrote the same bands without any DECON access and the owner reported only
  "seemingly no stripes", with no decoded recording; that is suggestive, not a controlled
  comparison. The registers at the first kick (what S-Boot left behind) were not captured.
* Why frames drawn before SW-form kicks were displayed although `FRAME_COUNT` did not move after
  them.
* Stride and pixel format. The band height on screen is about 59 ± 3 screen rows by an uncalibrated
  camera estimate, consistent with the hypothesised 4320 B/row (60.7 rows) but not a measurement.
* The exception path (ESR/ELR/FAR on hardware), the loader, memory preparation, the handoff and
  anything inside XNU. A pre-jump marker would still not prove kernel entry.
* The cause of the screen going dark at about 61.9 s. The host USB observer saw ADB vanish about
  10.6 s and `SEC_UPLOAD` about 95 s after the observer started, with no command sent, the same
  pattern as run 001; the recording's clock was not aligned with it, so no cause is claimed.

Next steps and the decisions they need (none authorised): `canary-fault` for the exception path
(BRK #0x1234, expected EC 0x3c, ISS 0x1234) is the smallest remaining step; `loader-diag`
with the existing payload would show stages up to pre-jump; both need an image-specific decision
like 0010. The recording and decoded frames stay local under `artifacts/nat-022/video-attempt-002/`
(the video contains the owner's room and is not committed).

## canary-trig-fault: the exception path on the proven display channel (host-built; run once under decision 0011, result in the next section)

`canary-trig` (run 002) showed the display channel works with the DECON0 kick, so the smallest
remaining step of the diagnostic plan is the exception path: does the vector table, the exception
stack and the ESR/ELR/FAR report work on this phone, and can the report be read from the screen.
`build.py` builds `canary-trig-fault` = `canary-trig` plus `BRK #0x1234` after the first full report
round (`-DMK_TRIG=1 -DCANARY_FAULT=1 -DMK_FAULT_ROUND=0`). The plain, fault, trig and loader-diag
Images are byte-identical to the earlier builds (`build-003/build.json`; `MK_FAULT_ROUND` defaults to
the old value 2). Two builds give identical hashes.

* Canary Image SHA-256 `f839ba305fae5e89c48642b422a827bc4993d491681560b2b20fd1a46b560a1b`
  (49152 bytes), RECOVERY image `e7ab288fdd689dcb15c58cf92e19a96586b30ec3b85a6df09695d3b41772a735`
  (`artifacts/nat-022/package-003/package.json`, same NAT-006 packaging as run 002).
* Why round 0: in run 002 the display ended about 60 s after the first marker; three rounds
  (~55 s) would leave a couple of seconds for ESR/ELR/FAR. With the BRK at about 19 s one exception
  cycle (SLOT, 4 ESR, 4 ELR, 4 FAR, then the DECON report; about 28 s) completes before that point and
  repeats. The 60 s figure is two observations of one effect, not a measured timeout.
* Expected on a working handler (entry was EL2, so VBAR_EL2/ESR_EL2 are used): slot 4 (current EL,
  SPx, synchronous), ESR `0xf2001234` (EC 0x3c, ISS 0x1234), ELR the address of the BRK in the image
  (image base `0x80000` + offset, to be matched against `build-003/canary-trig-fault/canary.elf`),
  FAR not meaningful for BRK. Anything else is a result to explain, not to adjust.
* Host tests (`test_nat022.py::Trigger`, 21 pass in total): the exception loop with kicks draws its
  marker before any MMIO, touches only the contract registers, reads ESR/ELR/FAR back with the
  independent decoder, and with a poisoned kick or the MMU on reports without any MMIO. The AArch64
  vector entry (`exc_common`) and the BRK itself are not host-testable (no AArch64 emulator): the
  hardware run is what would test them, as it also was for the first start path.
* MMIO and sequence are those of decision 0010 (reads of four DECON0 registers, writes of `TRIG_CON`
  and `SHD_REG_UP_REQ`, only after the first marker, MMU off); nothing new is touched. Recovery is
  the run-002 path (`session_trigfault.py --restore`, otherwise Download Mode and one NAT-013 session).
* `session_trigfault.py` refuses to run unless
  `docs/decisions/0011-nat022-canary-trig-fault-single-run-2026-11-10.md` exists; the owner accepted
  the image-specific request and the record was written. The decision is consumed (marker
  `artifacts/nat-022/native-attempt-trigfault-used.json`); the "image base `0x80000`" in the
  expectation above was wrong, see the correction in the next section.

## Native result 003, 2026-11-10 (decision 0011): the exception path decoded from the owner's recording

`canary-trig-fault` (canary Image `f839ba30…`, RECOVERY image `e7ab288f…`) was written to RECOVERY with
a matching readback and booted once (`adb reboot recovery` at 13:43:48Z). The owner filmed the
screen. Stock RECOVERY was restored with one NAT-013 session in Download Mode (bus 5 dev 51,
entered 13:46:31Z, restore 13:47:46Z); the full hash equals stock (`96620b8b…`), `check_android`
passed and `assess` reports Android booted. Record: `native-attempt-003-evidence.json`.

`decode_video.py` (unchanged) decoded 581 CRC-valid frames between 4.2 s and 63.9 s of the 66 s
recording; the screen is dark from about 64.9 s. No (kind, idx) pair has a second value except the
ones that are expected to change (STAGE 0x10 -> 0x11, the FRAME_COUNT and kick-count words).

| Frame(s) | Decoded | Meaning |
| --- | --- | --- |
| CHECK | `0xa5a5` | stack check passed (as in run 002) |
| ENTRY | `0x8900` | EL2, MMU off, D-cache off, I-cache on (same as run 002) |
| BOOTID | `0x4fee1585` | a different boot from run 002 (`0x1ae1d195`) |
| STAGE | `0x10`, later `0x11` | canary C reached; then "about to BRK" drawn by the code just before the BRK |
| REG, canary loop (kick 6) | status 2, GLOBAL_CON `0x113`, TRIG_CON `0x3063` -> `0x3062`, FRAME_COUNT 165 -> 315 | same values as run 002 (163 -> 314) within the counter's spread |
| SLOT | 4 | synchronous exception at the current EL (EL2) with SP_ELx |
| ESR | `0x00000000f2001234` | EC 0x3c (BRK, AArch64), ISS 0x1234, exactly what the instruction raises |
| ELR | `0x00000000801a2fb8` | see below |
| FAR | `0x5efe5e5c70ff25fc` | not an address: FAR is architecturally UNKNOWN for BRK |
| REG, exception loop (kick 14) | status 2, GLOBAL_CON `0x113`, TRIG_CON `0x3063` -> `0x3062`, FRAME_COUNT 1967 -> 2117 | DECON0 kicks continue from the exception handler |

ELR: the Image contains exactly one `BRK #0x1234` word (`0xd4224680`), at file offset `0x2fb8`. The
decoded ELR ends in exactly `2fb8`, so the image was executing at `0x801a0000` (64 KiB aligned). This
base is inferred from that one match; it is not the `0x80000 + offset` the expectation above assumed
(that came from the Image header's `text_offset` and is not where this S-Boot placed the image).
The Android boot header (v2) names `0x10008000` as kernel address, which is not used either. A
loader that must run from this entry has to be position-independent or relocate itself. The NAT-020
loader links at 0 and its `start.S` addresses its stack and vectors with `adr`, so its first
instructions do not depend on the load address; where it places the kernel segments is a separate
question that the `loader-diag` markers are meant to answer.

Established (observation of this S24, one run): our code received a synchronous exception at EL2 through
the vector table in our image, on an exception stack, read ESR_EL2, ELR_EL2 and FAR_EL2, and drew them
(plus the slot) as CRC-valid markers that an independent camera recording decodes. Together with run
002 this meets the goal's third step (entry into our code, privilege level, MMU/cache state, stack,
exception handler, one independently observable marker), for a no-XNU image.

Not established:
* Stride, pixel format and the real band height (the ~59 rows per band remains an estimate).
* Whether the DECON0 kick, or S-Boot's own refresh, makes the markers visible: still no no-kick
  control.
* Anything about the loader, memory preparation, handoff or XNU (no such image was run).
* The cause of the dark screen at about 64.9 s and of the USB sequence (ADB gone at +7 s,
  `SEC_UPLOAD` at +95 s, gone at +118 s, no command sent; the recording clock was not aligned with
  host time, the same limit as run 002). This image arms no watchdog.
* The exception-entry `STAGE 0x1f` frame is drawn and replaced at once (no dwell), so it was not
  visible; the next image should hold it for one dwell.

The recording and decoded frames stay local under `artifacts/nat-022/video-attempt-003/` (the video
shows the owner's room and is not committed).

