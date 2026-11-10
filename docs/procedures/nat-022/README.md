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


## loader-diag-trig-hold: the NAT-020 loader with visible stage markers, held before the jump (host-built, NAT-025; not run)

Goal step 4 asks for the staged path loader → memory preparation → handoff → a marker inside XNU.
Repeating a full XNU start is not useful until the loader's own progress is visible, so this image
only extends the stage that is already proven (a NAT-022 marker channel that run 002/003 decoded):
`build.py --loader-source` derives it from the NAT-020 build-003 loader source through
`patch_loader.py --trig-hold` and links the loader with `markerlib.c` (`-DMK_TRIG=1 -DMK_LOADER=1`).
The loader's own logic is otherwise unchanged. Plain `loader-diag` (no kick, no hold) is still built
and byte-identical to the earlier build; the four canary Images are byte-identical to
`build-003/build.json`. Two builds give identical hashes (`artifacts/nat-022/build-004`,
`build-004-repro`).

* `loader-diag-trig-hold` Image.payload SHA-256
  `7c6206bd06923a91524afe95ec03573ed6fa680978cc839c40991debf7702cb3` (21767776 bytes: the loader
  Image `901565b2…`, 212992 bytes, plus the 21 MB SWEETXNU payload), RECOVERY image
  `511b4833f0b6c24f5adffe762451bcbf937aa9a23b64bdd41d254885e006c475`
  (`artifacts/nat-022/package-004/package.json`, NAT-006 packaging, kernel at offset 2048).
* **It never jumps.** The patch replaces the final `BR` into the kernel copy by `mk_hold(PRE_JUMP)`,
  which loops its frames for ever. A `PRE_JUMP` frame is therefore a statement about the loader, not
  about XNU. XNU-entry evidence needs a later image that has code inside the kernel draw
  `MK_ST_XNU_ENTRY` (0x50, reserved).
* Sequence (each `mk_stage` redraws all bands, kicks DECON0 once, and dwells 1.2 s): ENTRY frame at
  `_start` (EL, MMU/cache bits; same as the canary), `LOADER_MAIN` (0x20), `LOADER_FB` (0x21),
  `LOADER_MEM` (0x30, window chosen), `ZERO` (0x31), `COPY` (0x32), `ADT` (0x33), `CLEAN` (0x34,
  before the full-window cache clean, which may take a long time), `PRE_JUMP` (0x40), then the hold
  loop. Each stage frame carries the mask of stages reached so far, so a missed frame cannot hide
  progress.
* Hold loop frames: STAGE idx 0 = the stage, STAGE idx 1 = reached-stage mask (bit 0 ENTRY, 1 MAIN,
  2 FB, 3 MEM, 4 ZERO, 5 COPY, 6 ADT, 7 CLEAN, 8 PRE_JUMP, 9 FAIL, 15 other), STAGE idx 2 = a stage
  code (the failure code below, otherwise 0), BOOTID, and the REG report with the kick status.
* Every `fail()` and the invalid-FDT return hold a `LOADER_FAIL` (0x3f) frame whose code is
  `fnv16` of the message (FNV-1a/32 of the string, `h ^ (h >> 16)`, low 16 bits; `decode.py` has the
  same function and the table). Invalid FDT is `0xfd7d`.
* A loader exception reports SLOT, ESR, ELR and FAR through the same exception loop as the canary,
  unconditionally (the original code only drew when the loader's framebuffer was the marker region).

| Code | `fail()` message |
| --- | --- |
| `0xa4c6` | not entered at EL1 |
| `0x9d89` | no appended SWEETXNU payload or initrd |
| `0xb215` | initrd is not a SWEETXNU payload |
| `0x2543` | bad payload header |
| `0xa6f2` | bad payload RAM size |
| `0x7f24` | invalid loader image exclusion |
| `0xe266` | incomplete or unusable DTB RAM map |
| `0xc6b7` | no usable RAM window |
| `0xd27d` | kernel larger than RAM window |
| `0xb0ca` | bad ADT offset/size |
| `0x07cf` | bad segment |
| `0x224e` | bad segment file range |
| `0x377c` | payload overlaps XNU RAM |
| `0x5313` | no room for ADT/boot_args |
| `0x2ce4` | ADT boot CPU MPIDR patch failed |
| `0xfb45` | ADT memory patch failed |
| `0x129a` | entry outside kernel |

Load address: run 003 showed that this S-Boot starts an Image at `0x801a0000`, not at the header's
`text_offset`. The loader is linked at 0, but `readelf -r` on its objects shows no absolute pointer
other than the header's `_payload_start` field; code and data are reached with `adr`/`adrp` (the
`ADD_ABS_LO12` entries are the low halves of `adrp` pairs, valid because `0x801a0000` is 4 KiB
aligned), and the `ui.c` label tables are two-dimensional `char` arrays, not pointer tables. So no
relocation is needed to run it where the canary ran. This is a static check of the objects; whether
the loader's later steps (window choice around the loader at `0x801a0000`, the 21 MB payload
placement) behave is what the run would measure.

Not host-testable (no AArch64 emulator): the AArch64 start path, the loader's real use of the DTB,
the RAM zero/copy/clean timings, and the DECON0 behaviour while the loader moves large amounts of
memory. Host tests (`test_nat022.py`, 28 pass, `LoaderHold`) run the real `markerlib.c` against a
RAM buffer and a fake DECON0 register file and check, with the independent decoder: the stage
order and mask, the hold-loop frame set and exact frame count, no MMIO before the first marker, the
hash16 code of every `fail("…")` message in `loader.c` (C against Python, no two messages share a
hash), the loader exception loop, and behaviour with the MMU on and with a poisoned kick. The build
test additionally checks that every `patch_loader.py` anchor matches (it asserts once per anchor),
that every `build-003` image hash is unchanged, and that in the patched `loader.c` the
`mk_hold(MK_ST_PRE_JUMP, 0)` call (a `noreturn` function) stands before the only `return entry_pa;`,
so the `br` in `start.S` is not reached. That is a source-level check; the instruction stream of the
linked Image was not disassembled (no AArch64 disassembler on the host).

What each outcome would mean (one run, image-specific; any stage list is a minimum):
* Frames to `PRE_JUMP` with the hold loop: the loader reached its end on this phone from the
  S-Boot entry (EL2→EL1, PMU/watchdog guard, GIC, window, 21 MB copy, ADT, clean). The recovery
  guard armed the 83 s watchdog, so a hold longer than that ends in a reset whose effect on the
  phone is part of what is being measured.
* A `LOADER_FAIL` frame: the table above names the exact refusal.
* A loader exception frame: SLOT/ESR/ELR/FAR of the failing instruction (ELR minus `0x801a0000`
  maps into `loader.elf`).
* Markers stop part-way with no exception: unresolved; the last mask bit shows where, the cause may
  be a hang, a long clean, the watchdog, or the display going dark, and the run alone cannot
  distinguish them.
* No markers at all: the loader did not reach its first marker (`recovery_guard` runs before
  `loader_main`, so a guard-related refusal is possible), or nothing was visible.

Device access that differs from the canary (this is why a separate decision is needed): beyond the
DECON0 contract of decisions 0010/0011 the NAT-020 loader reads and may clear PMU INFORM `0xbc`
(`0x12860000`), arms the S5E9945 watchdog at `0x10040000` for 83 s, initialises the GIC
(`0x10200000`/`0x10240000`), zeroes and copies RAM, and cleans caches over the XNU window. It writes
no storage and no partition; the only storage write is the RECOVERY image the owner approves.

`session_loaderhold.py` refuses to run unless
`docs/decisions/0012-nat022-loader-diag-trig-hold-single-run-2026-11-10.md` exists (it does not exist
yet; checked: the driver exits before any device command). Recovery is the earlier path
(`--restore`, otherwise Download Mode and one NAT-013 session).

### Is the `start.S` M/C check the reason NAT-021 was inconclusive? (data from runs 002 and 003)

The NAT-020 loader's `el1_entry` (`start.S`, after the EL2→EL1 `eret`) halts silently when
`SCTLR_EL1.M` or `SCTLR_EL1.C` is set (`tbnz x1, #0` / `tbnz x1, #2`), before the log and the
watchdog. The canary reads the same register (`canary.S`: `mrs x21, sctlr_el1`, taken at EL2 before
any change) and draws it in the ENTRY frame. In two separate boots (runs 002 and 003, same S-Boot, same
RECOVERY boot path) the frame decodes as `0x8900`: entry at EL2, current-EL SCTLR M=0 C=0 I=1 and
`SCTLR_EL1` M=0 C=0 I=1. So on those boots that check would not have halted the loader; the NAT-021
silence is not explained by it. Limits: the NAT-021 boot itself was not observed, and the canary shows
the state at its first instruction only, not that the loader's later accesses are safe. The
loader-diag variants additionally replace that silent halt by a marker-then-halt (`GATE_MC`, 0x02),
so a run that did stop there would now say so.

## Native result 004, 2026-11-10 (decision 0012): the loader stopped at its payload header check

`loader-diag-trig-hold` (loader `Image.payload` `7c6206bd…`, RECOVERY image `511b4833…`, source commit
`82f636e`) was written to RECOVERY with a matching full readback and booted once (`adb reboot recovery`
at 14:52:43Z). The owner filmed the screen (84.0 s recording). Stock RECOVERY was restored with one
NAT-013 session in Download Mode (`04e8:685d` seen by the host observer at 14:54:39Z, restore
14:55:22Z–14:55:25Z, ADB back at 14:56:22Z); the full hash equals stock (`96620b8b…`),
`check_android` passed and Android booted. Record: `native-attempt-004-evidence.json` (outcome `fail`:
the goal's "loader reaches memory preparation, handoff and pre-jump" criterion was not met).

`decode_video.py` (unchanged) decoded 567 CRC-valid frames between 0.0 s and 82.6 s (238 frames failed
sync/CRC, 16 had a poor grid, 12 no contrast, 4 no grid, 1 too few edges). A second pass over 4–26 s
with a wider top margin (`--y0 10`) gave 192 valid frames with the same values.

| Time (s) | Frame | Decoded | Meaning |
| --- | --- | --- | --- |
| 0.0–2.1 | STAGE idx0 | `0x20` | `LOADER_MAIN`: `loader_main` was entered |
| 2.2–3.3 | STAGE idx0 | `0x21` | `LOADER_FB`: framebuffer selection done |
| 3.5– | STAGE idx0 | `0x3f` | `LOADER_FAIL` |
| hold loop | STAGE idx1 | `0x0207` | reached-stage mask: ENTRY, MAIN, FB, FAIL; MEM, ZERO, COPY, ADT, CLEAN, PRE_JUMP not reached |
| hold loop | STAGE idx2 | `0x2543` | fnv16 of the message `bad payload header` |
| hold loop | BOOTID | `0x0a10`, `0x0fae` | boot identifier words |
| hold loop | REG 0..9 | status 1/2 (alternating between cycles), GLOBAL_CON `0x133`/`0x113`, TRIG_CON `0x3062`↔`0x3063`, FRAME_COUNT advancing, kick count `0x18`, `0x27`, `0x36` | DECON0 register report; the values are listed as seen and not interpreted further |

The loop repeats about every 18.7 s. The loader's own `ENTRY` frame was not captured (the recording
starts when the owner started the camera; one CRC-valid candidate at 8.4 s decodes to `0xfb0b`, which
is not a plausible ENTRY word and is treated as a false positive). The owner reports a text line at
the bottom of the screen, roughly "els loader boot ealy test image not off firemaire"; the project did
not decode that text, so it is only the owner's reading of the loader's own UI footer. The screen
stayed lit until about 82.7 s of the recording, longer than the 60–65 s seen with the canary images
(a hypothesis, not measured: the loader arms its 83 s watchdog).

### Why `bad payload header`: a deterministic payload/loader mismatch

`check_payload.py LOADER_C PAYLOAD` cuts the `struct payload` definition and the header-check
`if (...) { return fail(...) }` text out of the real `loader.c`, compiles them unchanged for the host
and evaluates each `||` clause on the payload bytes. On the flashed payload (`artifacts/nat-020/build-003/payload.bin`)
exactly one clause fires:

```
FIRES [bad payload header] (p->adt_size & 7)
```

`adt_size` is `0x3684` = 13956, the unpadded length of `e1s.adt`; `mkpayload.py` records
`len(adt_blob)` although it pads the blob to 16 bytes, and the loader requires a multiple of 8. All
other header clauses pass (`version`, `nsegs`, `adt_off & 7`, `entry_va`/`kernel_end` against `virt_base`,
the RAM-size clauses). This matches the decoded code `0x2543`, so the stop is explained by the payload
bytes themselves and not by the hardware. It is inferred statically; only a re-run with a corrected
payload would show that no other condition follows (the later stages have not run on the device).

The earlier suspicion that `start.S`'s `SCTLR_EL1` M/C halt stops the loader is not what happened here:
the loader code after `el1_entry` ran (its stage markers were drawn).

Established (observation of this S24, one run): the NAT-020 loader code, started from the RECOVERY slot,
runs on this S-Boot, reaches `loader_main` and its framebuffer selection, and shows its own CRC-valid
stage markers and failure code on the same display channel as the canary.

Not established: any stage after the payload header check (window choice, RAM zeroing, copy, ADT and
`boot_args` patching, cache clean, the pre-jump marker); anything about XNU; the cause of the dark
screen; who entered Download Mode (the USB observer started 84 s after the reboot because its first
invocation used an out-of-range duration and exited; the first host USB event is at +116 s); stride and
pixel format; whether the kick or S-Boot's refresh makes the markers visible (still no no-kick control).

The recording and decoded frames stay local under `artifacts/nat-022/video-attempt-004/` (the video
shows the owner's room and is not committed).

## loader-diag-trig-hold-adt8: the run-004 image with a corrected payload header (NAT-026; run once under decision 0013, result below)

Run 004 stopped at `fail("bad payload header")` because the payload header's `adt_size` is 13956, not a
multiple of 8. `fix_payload.py` rounds that one u64 up to 13960 in a copy of the payload (the 12 bytes
`mkpayload.py` leaves after the ADT are zero; it refuses if they are not, if no padding exists, if a
segment's file range touches it, or if the field is already a multiple of 8). `build.py` adds the
variant `loader-diag-trig-hold-adt8`; the loader code is not changed.

| | run-004 image | adt8 image |
| --- | --- | --- |
| loader `Image` (`loader-diag-trig-hold`) | `901565b2…` | `901565b2…` (same bytes) |
| `Image.payload` | `7c6206bd…` | `766218b2…` (differs in one byte, offset `0x34028`: `0x84` → `0x88`) |
| RECOVERY image (NAT-006 packaging) | `511b4833…` | `38411cd8…` (21 bytes differ: that byte and the 20-byte boot-header id) |

`build.py` reproduces the run-004 image bit-for-bit (`7c6206bd…`), so the comparison is not against a
rebuilt approximation. All earlier canary images and `loader-diag` keep their hashes (checked by the test).

Host checks (`check_payload.py LOADER_C PAYLOAD --offset 212992`; host-test evidence only):

* the loader's own header clauses, cut from `loader.c` and compiled unchanged: run-004 image: only
  `adt_size & 7` fires; adt8 image: no clause fires;
* the RAM/segment checks, the ADT/boot_args room check and the entry check (text cut from `loader.c`), for
  window sizes 256 and 512 MiB: `ok`; the kernel needs 0x4978000 bytes before `boot_args` and 0x497c000
  in all, far below 256 MiB;
* the real `adt_patch.c`, compiled for the host, on the 13960-byte ADT in a guarded buffer with the
  argument expressions of `loader.c`: the MPIDR, DRAM, pram and ramdisk calls return 0 for window sizes
  256/512 MiB and for MPIDR values 0, 0x80000000, 0x80000100, 0x80000400, 0xffffffff; no guard byte is
  overwritten; 2–6 ADT bytes change per run.

Tests: `test_nat022.py` (31): the synthetic-header test violates each of the loader's nine header clauses
once and requires exactly that clause to fire; the fixer refuses the four unsafe inputs; the build test
requires the adt8 `Image.payload` to differ from the run-004 one in exactly that byte.

Not evaluated on the host, and what would first show on the phone: which RAM window `choose_window()` picks
from the S-Boot DTB (the DTB is not available here); the framebuffer selection; the time that zeroing a
256–512 MiB window and copying 21 MiB take with the MMU off (the loader's 83 s watchdog is armed; if the
copy does not finish in time the screen goes dark on the last stage marker); whether anything in the
window is in use by firmware that is not listed as reserved in the DTB. The image still halts at PRE_JUMP
and never branches to the kernel copy (`mk_hold` is `noreturn` and sits before the only `return entry_pa;`).

What each outcome would mean (same encoding as run 004; reached-stage mask bits ENTRY 0, MAIN 1, FB 2,
MEM 3, ZERO 4, COPY 5, ADT 6, CLEAN 7, PRE_JUMP 8, FAIL 9):

* PRE_JUMP held, mask `0x01ff`: the loader's window choice, zeroing, copy, ADT patching and cache
  clean ran on this S24 and the image would have been ready to jump. This is still not XNU entry.
* A FAIL frame with another code: the fnv16 table above names the condition that stopped it.
* The screen going dark on a stage marker without FAIL: that stage did not finish (hang, reset or the
  watchdog); the stage named by the last marker is where to look.
* The same `0x2543`: the clause analysis above was incomplete.

Session driver: `session_adt8.py` (default is read-only preflight; `--execute` writes and reboots once;
`--restore` writes only stock). It asserts the stock and candidate hashes, `package.json`, the loader
`Image.payload` hash at its offset, and that `docs/decisions/0013-nat022-loader-diag-trig-hold-adt8-single-run-2026-11-10.md`
exists. Without that file it stops before any device command (tested on 2026-11-10; the report is
`artifacts/nat-022/preflight-gate-005/report.json`). Decision 0013 was then made and the image was run once
(next section).

## Native result 005, 2026-11-10 (decision 0013): the loader reached COPY, then took an alignment fault in the ADT patch stage

`loader-diag-trig-hold-adt8` (loader `Image.payload` `766218b2…`, RECOVERY image `38411cd8…`, source commit
`1092fab`) was written to RECOVERY with a matching full readback and booted once (`adb reboot recovery`
at 15:28:40.9Z). The owner filmed the screen (84.7 s recording). Stock RECOVERY was restored with one
NAT-013 session in Download Mode (`04e8:685d` seen by the host observer at 15:30:36Z, restore
15:33:10Z–15:33:14Z, Android back at 15:33:59Z); the full hash equals stock (`96620b8b…`),
`check_android` passed and Android booted. Record: `native-attempt-005-evidence.json` (outcome `fail`: the
criterion "reaches memory preparation, ADT/boot_args and pre-jump stages" was met only up to COPY).

`decode_video.py` (unchanged) decoded 781 CRC-valid frames with `--y0 10` (the default `--y0 60` cuts the
top sync band for t ≈ 22–60 s and decodes only 277 rows); the sources are three windows, 0–20 s, 20–62 s,
62–85 s, merged in `decoded-timeline.json`.

| Time (s) | Frame | Decoded | Meaning |
| --- | --- | --- | --- |
| 0.2–0.4 | STAGE idx0 | `0x20` | `LOADER_MAIN` (the recording starts at about this point) |
| 2.5–3.9 | STAGE idx0 | `0x21` | `LOADER_FB` |
| 4.2–12.5 | STAGE idx0 | `0x30` | `LOADER_MEM`: window chosen; RAM zeroing runs after the 1.2 s dwell (≈ 7 s) |
| 12.6–13.7 | STAGE idx0 | `0x31` | `LOADER_ZERO`: zeroing done |
| 14.8–16.1 | STAGE idx0 | `0x32` | `LOADER_COPY`: all 10 segments copied (21.5 MB), ≈ 1 s after the ZERO dwell |
| 16.1–17.3 | STAGE idx0 | `0x1f` | `EXC`: exception report from inside the loader |
| 17.35 | STAGE idx1 | `0x003f` | reached-stage mask ENTRY, MAIN, FB, MEM, ZERO, COPY (ADT, CLEAN, PRE_JUMP not reached) |
| 18.65 | SLOT | `0x0004` | vector slot 4: synchronous exception from the current EL with SPx |
| 19.9–24.6 | ESR 0..3 | `0x0000 0x0000 0x9600 0x0061` | ESR `0x96000061`: EC `0x25` (data abort, same EL), IL, DFSC `0x21` = alignment fault, WnR = 1 (a store) |
| 24.8–29.6 | ELR 0..3 | `0x0000 0x0000 0x800a 0x9954` | ELR `0x800a9954` |
| 29.7–34.6 | FAR 0..3 | `0x0000 0x0009 0xe2d7 0x43fc` | FAR `0x00000009e2d743fc` |
| 34.7–46.9 | REG 0..9 | status 1, GLOBAL_CON `0x0133`, TRIG_CON `0x3062`→`0x3063`, FRAME_COUNT `0x0686`→`0x0687`, kick count `0x0f` | DECON0 report |

The report repeats about every 29.8 s with the same ESR/ELR/FAR (three STAGE idx1 frames at 17.35, 47.13 and
76.91 s; kick count `0x0f` → `0x27` in the second REG block; FRAME_COUNT advances ~60 Hz in between). The last
CRC-valid frame is at 82.9 s; the screen state after the end of the recording is not known.

The owner wrote (Russian, as typed) that the loader's own on-screen UI showed more than the markers:
"там еще была загрузка сегментов ядра или типа того и ok gicv3 и ok payload header и >> RAM windows может еще
чгео о я пропустил". This is the owner's reading of the loader's UI text; it matches the stage sequence above
(one still near t = 14 s reads "Copying kernel segments 2/10 segments 2.6/21.5 MB"; that reading is by eye).

### Which instruction faulted, and why (host analysis of the flashed loader; two independent routes)

* **Base and instruction.** The S-Boot RECOVERY base for this image is `0x800a0000` (for the canary of run 003 it was
  `0x801a0000`: the base varies with the image). `ELR − 0x800a0000 = 0x9954`; the flashed loader `Image` holds
  `stur x19, [x11, #0x24]` there, which is `adt_set_dram+0x268`: the store of the 64-bit `dram-size` property
  value in `adt_patch.c`. (`scan_unaligned.py` lists exactly this instruction at file offset `0x9954`, and three more.)
* **Address.** `FAR − 1020 = 0x9e2d74000`, 16 KiB aligned, the ADT copy in the RAM window; offset 1020 is the value of
  `dram-size` in the real `e1s.adt` (`dram-base`, at offset 976, is 8-aligned and had been written without a fault).
* **Cause.** ADT property values start at node offset + 36 and are rounded to 4 bytes, so a value is only 4-byte
  aligned. The loader runs at EL1 with the MMU off: all data accesses are Device memory and must be naturally
  aligned, so a 64-bit store to a 4-byte-aligned address is an alignment fault. The NAT-026 host pre-check ran
  `adt_patch.c` on x86-64, which accepts misaligned accesses, and could not see this.

Established (observation of this S24, one run): the loader, built from the pinned NAT-020 source with the NAT-022
instrumentation, ran from RECOVERY and completed FDT parsing, window choice, zeroing (≈ 7 s) and the copy of all 10
segments before the ADT patch stage; the payload-header failure of run 004 is gone; the exception reporter works
from inside the loader (stage, ESR, ELR, FAR decoded from an independent recording, goal step 5 for the loader).

Not established: boot_args, the full-window cache clean and the PRE_JUMP hold; whether the loader has other
Device-memory alignment hazards (see NAT-027 below: only scanned/sanitized, not run); any XNU entry (none was
attempted: the image never branches to the kernel copy); the exact RAM window (implied only); who put the phone
into Download Mode and why the screen went dark; stride/pixel format; kick vs S-Boot refresh (no no-kick control).

The recording and decoded frames stay local under `artifacts/nat-022/video-attempt-005/` (the video shows the
owner's room and is not committed).

## loader-diag-trig-hold-adt8-aln: the run-005 image with aligned ADT accesses (NAT-027; run once under decision 0014, result below)

`patch_loader.py --adt-aligned` (hash-anchored on the base `adt_patch.c`, SHA-256 `415bf5c0…`) adds
`adt_ld64`/`adt_st64`, two aligned 32-bit accesses (low word first; the ADT is little-endian here), and uses
them for the five 64-bit ADT property accesses in the source (`adt_set_dram`, `adt_set_pram` twice,
`adt_rebase_ramdisk` read and write). Every property offset is a multiple of 4, so each 32-bit access is aligned.
`build.py` adds the variant `loader-diag-trig-hold-adt8-aln` (`build-006`); it uses the same adt8 payload fix.

| | run-005 image | aln image |
| --- | --- | --- |
| loader `Image` | `901565b2…` | `f0e61342…` |
| `Image.payload` | `766218b2…` | `2fb39687…` |
| RECOVERY image (NAT-006 packaging, `package-006`) | `38411cd8…` | `cdf4f3a1…` |

Host checks (host-test evidence only; logs in `artifacts/nat-022/nat027-logs/`, summary `evidence-nat027.json`):

* `build.py` reproduces `build-006` bit-for-bit (`build-006-repro`); all seven earlier images and payloads
  (the run-005 image included) keep their hashes.
* `scan_unaligned.py` (decodes every general-register LDUR/STUR/LDURS* in `.text`, skipping `$d` data, and reports an
  unscaled immediate that is not a multiple of the access size): 4 findings on the run-005 loader
  (`adt_set_dram+0x178`, `adt_set_dram+0x268` = the faulting one, `adt_set_pram+0x13c`, `adt_set_pram+0x140`), 0 on the
  aln loader. It does not see addresses built at run time; the loader may still have such hazards.
* `check_payload.py` now rebuilds the ADT harness with `gcc -fsanitize=alignment -fsanitize-undefined-trap-on-error`
  and runs it: the run-005 source `FIRES adt_patch.c: MISALIGNED ACCESS in adt_set_dram`; the aln source `ok`. All
  earlier checks still pass for the aln image (header clauses, RAM/segment, boot_args room, ADT return codes 0,
  guard bytes intact for MPIDR 0, 0x80000000, 0x80000100, 0x80000400, 0xffffffff).
* The aligned accessors write byte-identical ADT output to the original accessors for window bases below and above
  4 GiB, and the written values are parsed back from the ADT layout (`test_nat022.py`).
* `test_nat022.py`: 35 tests pass; `make check` passes (214 tests).

Not evaluated on the host: every other data access of the loader with the MMU off; the real RAM window; later stages
(boot_args, cache clean over the full window, PRE_JUMP hold); whether the 83 s watchdog the loader arms is enough for
the stages after COPY (zeroing ≈ 7 s and the copy ≈ 1 s were measured in run 005; the full-window clean is unmeasured).
The image still halts at PRE_JUMP and never branches to the kernel copy.

What each outcome would mean (same encoding as before): PRE_JUMP held with mask `0x01ff`: ADT patch, `boot_args`, the
full-window cache clean and the hold ran on this S24 (this is still not XNU entry); another EXC record: its
stage/ESR/ELR/FAR name the next fault; FAIL with another code: the fnv16 of the message names the condition.

Session driver: `session_aln.py` (default is read-only preflight; `--execute` writes and reboots once; `--restore`
writes only stock), gated on `docs/decisions/0014-nat022-loader-diag-trig-hold-adt8-aln-single-run-2026-11-10.md` and its own
one-shot marker `artifacts/nat-022/native-attempt-loaderhold-aln-used.json`. Without the decision file it stops before
any device command (`artifacts/nat-022/preflight-gate-006/report.json`: 0 commands, no write, no reboot). Decision
0014 was then made and the image was run once (next section).

## Native result 006, 2026-11-10 (decision 0014): the loader ran through every stage up to the held PRE_JUMP

`loader-diag-trig-hold-adt8-aln` (loader `Image.payload` `2fb39687…`, RECOVERY image `cdf4f3a1…`, source commit
`c5b942a`) was written to RECOVERY with a matching full readback and booted once (`adb reboot recovery` at
16:23:31.6Z). The owner filmed the screen (85.8 s recording) and, in their own words (Russian, as typed: "хз я его
сразу в довнлоад режим перевл не стад ждать перезагрузки"), put the phone into Download Mode without waiting for it to
reboot (host observer: `04e8:685d` at 16:25:25Z). Stock RECOVERY was restored with one NAT-013 session (16:30:33Z–16:30:36Z);
Android was back at 16:31:31Z; the full hash equals stock (`96620b8b…`), `check_android` and `assess` pass. Record:
`native-attempt-006-evidence.json` (outcome `pass` for the loader-reaches-PRE_JUMP criterion; this is not XNU entry).

`decode_video.py` (unchanged, `--y0 10`, four windows) decoded 754 CRC-valid frames (STAGE 333, REG 344, BOOTID 77),
merged in `decoded-timeline.json`:

| Time (s) | Frame | Decoded | Meaning |
| --- | --- | --- | --- |
| 0.0–2.3 | STAGE idx0 | `0x20` | `LOADER_MAIN` |
| 2.4–3.8 | STAGE idx0 | `0x21` | `LOADER_FB` |
| 4.0–12.3 | STAGE idx0 | `0x30` | `LOADER_MEM` (window chosen; zeroing after the dwell) |
| 12.4–13.5 | STAGE idx0 | `0x31` | `LOADER_ZERO` |
| 14.6–15.9 | STAGE idx0 | `0x32` | `LOADER_COPY` (10 segments, 21.5 MB) |
| 16.0–17.1 | STAGE idx0 | `0x33` | `LOADER_ADT`: ADT patched (MPIDR, DRAM, pram, ramdisk rebase), boot_args built, ADT range cleaned |
| 17.3–18.7 | STAGE idx0 | `0x34` | `LOADER_CLEAN`: start of the full-window cache clean |
| 18.8– | STAGE idx0 | `0x40` | `PRE_JUMP`, held (the image never jumps) |
| 21.3 | STAGE idx1 | `0x01ff` | reached-stage mask: ENTRY, MAIN, FB, MEM, ZERO, COPY, ADT, CLEAN, PRE_JUMP (no FAIL bit) |
| 22.6 | STAGE idx2 | `0x0000` | no failure code |
| 23.8–26.2 | BOOTID idx0/1 | `0xb835`, `0x26af` | boot identifier words |
| 27.5–39.8 | REG 0..9 | status 1, GLOBAL_CON `0x0133`, TRIG_CON `0x3062`→`0x3063`, FRAME_COUNT `0x04db`→`0x04dc`, kick count `0x0f` | DECON0 report (later blocks: status 2/1, kick count `0x1e`, `0x2d`) |

The hold loop repeats every ~18.65 s (STAGE idx1 frames at 21.27, 39.92, 58.58 and 77.24 s). No EXC (`0x1f`), FAIL
(`0x3f`), SLOT, ESR, ELR or FAR frame occurs among the 754 CRC-valid frames; the only n < 3 CRC-valid frame is one
BOOTID candidate. The last CRC-valid frame is at 82.9 s, the recording ends at 85.8 s. A still shows the loader's UI
footer "e1s loader | experimental BOOT-only test image … not official firmware" (read by eye at reduced resolution, as the
owner read it after run 004).

Established (observation of this S24, one run): the loader, built from the pinned NAT-020 source with the NAT-022
instrumentation and the NAT-027 aligned ADT accesses, ran from RECOVERY through window choice, zeroing, the copy of all
segments, the ADT patch, `boot_args`, the full-window cache clean and reached the held pre-jump state; the run-005
alignment fault is gone (this is the first on-device confirmation of the NAT-027 fix). The loader never branched to the
kernel copy; no XNU code ran.

Not established: that the patched ADT and `boot_args` contents are right for XNU (only that the code that builds them
ran); that the cache clean makes the copied segments fetchable after a jump; the RAM window (implied only); the display
and watchdog behaviour after 83 s (the owner put the phone into Download Mode); any jump, XNU entry or marker inside
XNU; stride/pixel format; kick vs S-Boot refresh (no no-kick control). The REG block at 64.8–77.1 s shows FRAME_COUNT
idx7 = idx8 = `0x0da0` and no decoded TRIG_CON-after; it is listed as seen and not interpreted.

The recording and decoded frames stay local under `artifacts/nat-022/video-attempt-006/` (the video shows the owner's
room and is not committed).
