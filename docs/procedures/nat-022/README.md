# NAT-022: framebuffer-marker canary and instrumented loader (host work only)

Evidence kind: **host-test**. Nothing here was flashed or run on the phone. No
marker has been seen on hardware, so every statement about the phone's behaviour
below is an open question, not a result.

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

## canary-trig: DECON0 kick variant (host-tested only; NOT run)

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

Decision request: put to the owner in the session with the exact SHA-256. The record
`docs/decisions/0010-nat022-canary-trig-single-run-2026-11-10.md` exists only if the
owner accepts; `session_trig.py` refuses to run without it (and writes its own
one-shot marker `artifacts/nat-022/native-attempt-trig-used.json`).
