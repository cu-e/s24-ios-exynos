# 0015: One native run of the NAT-022 `loader-diag-xnu-entry` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code session, in answer to a
question (asked in Russian) that named the reason for the new image (native run 006 of decision 0014
reached the loader's `PRE_JUMP` hold with reached-mask `0x01ff` and no exception, so the loader built the
RAM window, the kernel copy, the patched ADT and `boot_args` and the full-window cache clean and stopped
before the jump), what the new image does (the same loader, but instead of holding at `PRE_JUMP` it jumps,
through start.S's existing `br x16`, to the entry point of the kernel copy; the first ten words there, the
kernel's own first instruction `b #0xfffffff00743e05c` plus nine NOP words, were overwritten by the loader
with a 40-byte position-independent stub that draws marker `STAGE 0x50` with its own PC, the incoming `x0`
and EL/SCTLR M/C/I and then holds), what it does not do (no XNU instruction executes: the kernel's first word
is replaced and not replayed, so a `0x50` frame is evidence that control reached the kernel copy's entry
address and ran only our stub, not that XNU booted), the expected on-screen result, the loader `Image`,
`Image.payload` and RECOVERY SHA-256s, the host checks (NAT-028), the device access (as decision 0014), the
new hazard (the first instruction fetch from the window and the handoff's `ic iallu` and `SCTLR_EL1` write
actually being followed by a branch), what the host does not cover, the recovery path and the
"Not granted" list, with the choice "Да, один запуск loader-diag-xnu-entry".

## Scope

Exactly one image: NAT-022 `loader-diag-xnu-entry`
(`artifacts/nat-022/build-008/loader-diag-xnu-entry/Image.payload`, SHA-256
`d4c391624ad8d50ce4c629d905a7a8fa88da142118ec2ff6a548bbeef9658f27`, 21771872 bytes; the loader `Image`
is `6cb6b1a03a008a40de6ebe5e823e773000b0a3e4899f9263f06adf4a41b2bcc3`, 217088 bytes), packaged with the
NAT-006 builder into the RECOVERY image SHA-256
`4353546c4494c2aad12eaf3b0188478f4157ee5e4e3658fd253387b80416d06a`
(`artifacts/nat-022/package-008/package.json`, payload verbatim at offset 2048). Source commit `606528b`,
evidence record `docs/procedures/nat-022/evidence-nat028.json` (commit `7dcb480`). Compared with the
decision-0014 image the loader differs by one `#include`, the replacement of the `PRE_JUMP` hold by a
comment, the stub installer block before the CLEAN marker (it refuses and holds a FAIL marker unless it
overwrites only NOP padding of a 8-byte aligned entry with at least 40 file-backed bytes), one exported
symbol in start.S, the stub template and the marker routine `mk_xnu_report`/`mk_xnu_entry_hold` (new marker
kind `XNU` = 10, reached-mask bit 10); every earlier image is byte-identical. Sequence: full-hash write to
RECOVERY (`/dev/block/sda18`) only, full readback, one `adb reboot recovery`, owner-operated camera recording
(~2 minutes), then restore of the pinned stock RECOVERY (`session_xnu.py --restore` if Android returns,
otherwise Download Mode and one NAT-013 session; stock SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`, backup
`devices/recovery/backups/2026-11-10/recovery.img`). Driver: `docs/procedures/nat-022/session_xnu.py` with its
own one-shot marker `artifacts/nat-022/native-attempt-xnuentry-used.json`.

Expected on screen if the jump reaches the stub: the stage markers up to `PRE_JUMP` (`0x40`, which is not
proof of anything beyond the loader), then `STAGE 0x50` with reached-mask `0x05ff`, EL1, M/C/I = 0, XNU frames
carrying the stub PC (`window base + 0x343b4a8`, 8-byte aligned) and `x0` (the `boot_args` PA), with
`x0 - PC = 0x153cb58`. An exception record (slot, ESR, ELR, FAR) or a screen that stays on `PRE_JUMP` or goes
dark are the other outcomes; none is a failure of the phone and none is retried.

## Device access granted (and nothing else)

Identical to decision 0014: DECON0 main block `0x19100000` (reads `GLOBAL_CON`, `TRIG_CON`,
`FRAME_COUNT`, `SHD_REG_UP_REQ`; writes `TRIG_CON` and `SHD_REG_UP_REQ` in the vendor driver's order; only
with the MMU off, only after the first marker, never after an earlier kick faulted), the framebuffer at
`0xFA200000`, the PMU INFORM register `0xbc` (`0x12860000`), the S5E9945 watchdog at `0x10040000` armed for
83 s, GIC initialisation (`0x10200000`, `0x10240000`), and the loader's RAM work: zero the chosen window,
copy the payload segments and the ADT/`boot_args` into it, patch the ADT copy, write the 40-byte stub over
the kernel copy's entry words, clean data caches over the window. New in this decision, and nothing else new:
after the clean the loader's handoff clears `SCTLR_EL1` M/C/I, runs `ic iallu` and branches (`br x16`) to the
kernel copy's entry address, where the stub runs on the loader's own stack and calls the loader's marker
routine. No storage device and no partition other than RECOVERY is written.

## Not granted

Replaying the displaced kernel instruction, returning into XNU or continuing the kernel in any way, execution
of any XNU instruction, retries, any other image, any other partition, any reset/data prompt answer, any other
MMIO. Each needs a new decision. The mandatory boundary of decision 0002 is unchanged: Android, apps,
settings, accounts and user data stay intact.

## Known limits disclosed

* Host evidence only for this image (NAT-028): stub bytes checked by an independent decoder, a decoder-driven
  interpreter run of the installed stub on the real kernel entry bytes and capstone; the real installer compiled
  with the gcc alignment trap changes only the 40 stub bytes and refuses in every unsafe case; the loader diff
  is whitelisted; the alignment scan finds 0 unaligned accesses; the build is reproducible. Not covered by any
  host check: whether the S24 fetches and runs code at the kernel copy's entry address, instruction-fetch and
  I-cache coherence after the loader's cache clean and `ic iallu`, the actual RAM window (implied
  ≈ `0x9dd3fc000` by run 006, never read directly), whether anything in the window is firmware memory not
  listed as reserved, behaviour after the 83 s watchdog, whether the ADT and `boot_args` are correct for XNU
  (only the `x0` pointer is shown).
* A `0x50` frame says control reached the kernel copy's entry address and ran only our stub. It does not say
  XNU runs, that the ADT/`boot_args` are acceptable to XNU, or that a later jump into the kernel works.
* If the loader hangs, resets, the watchdog fires or another fault occurs, the screen stays or goes dark on the
  last stage marker, or an exception record is shown; that is where to look. Download Mode and one NAT-013
  restore session may be needed, as after runs 1–6 (who enters Download Mode is not established; in run 006 the
  owner did).
* The display lasted ≥ 83 s in runs 004–006; the reached-stage mask in every frame mitigates a missed frame,
  not a dark screen.
* A run without readable markers is inconclusive. RAM contents are volatile; the window zero does not touch
  storage.
