# 0013: One native run of the NAT-022 `loader-diag-trig-hold-adt8` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code session, in answer to a
question that named the reason for the new image (native run 004 stopped at the loader's payload
header check; `adt_size` 13956 is not a multiple of 8), the one-byte difference from the run-004
image, the RECOVERY image SHA-256, the RECOVERY-only write with readback, the single
`adb reboot recovery`, what the loader will now do (window choice, zero, copy, ADT patch, cache clean,
stop before the jump), the device access (as decision 0012 plus writes into the RAM window), the risks
and the recovery path, with the choice "Да, один запуск loader-diag-trig-hold-adt8".

## Scope

Exactly one image: NAT-022 `loader-diag-trig-hold-adt8`
(`artifacts/nat-022/build-005/loader-diag-trig-hold-adt8/Image.payload`, SHA-256
`766218b288b3fddaef79d7347f91b57aab5f7329e4d574389eb142226726a87a`, 21767776 bytes; the loader
`Image` is `901565b225c2137ebd99e4684cb4dc9a6b4f3ecf68632eedcf9ef8b16cf7db28`, 212992 bytes, the same
bytes as in run 004), packaged with the NAT-006 builder into the RECOVERY image SHA-256
`38411cd82af4ae4b68079472d68936c23b3877208f301f33c295741ae991ce38`
(`artifacts/nat-022/package-005/package.json`). Source commit `1092fab` (NAT-026 evidence:
`docs/procedures/nat-022/evidence-nat026.json`). Compared with the run-004 image the `Image.payload`
differs in one byte (offset `0x34028`, the low byte of the payload header's `adt_size`, `0x84` →
`0x88`); the loader code is unchanged. The image stage markers, dwell and DECON0 kicks are those of
decision 0012, and the image still halts at `PRE_JUMP` instead of jumping: the held marker is a
statement about the loader, not about XNU, and the kernel copy is never entered. Sequence: full-hash
write to RECOVERY (`/dev/block/sda18`) only, full readback, one `adb reboot recovery`, owner-operated
camera recording (~2 minutes), then restore of the pinned stock RECOVERY (`session_adt8.py --restore`
if Android returns, otherwise Download Mode and one NAT-013 session). Driver:
`docs/procedures/nat-022/session_adt8.py` with its own one-shot marker
`artifacts/nat-022/native-attempt-loaderhold-adt8-used.json`.

## Device access granted (and nothing else)

Identical to decision 0012: DECON0 main block `0x19100000` (reads `GLOBAL_CON`, `TRIG_CON`,
`FRAME_COUNT`, `SHD_REG_UP_REQ`; writes `TRIG_CON` and `SHD_REG_UP_REQ` in the vendor driver's order;
only with the MMU off, only after the first marker, never after an earlier kick faulted), the
framebuffer at `0xFA200000`, the PMU INFORM register `0xbc` (`0x12860000`), the S5E9945 watchdog at
`0x10040000` armed for 83 s, GIC initialisation (`0x10200000`, `0x10240000`), and the loader's RAM
work: zero the window it chose from the S-Boot DTB (256–512 MiB, outside the DTB's reserved ranges,
the loader image, the payload, the framebuffer and the log area), copy the ~21 MB payload segments
and the ADT/boot_args into it, patch the ADT copy, clean data caches over it. In run 004 the loader
stopped before this RAM work; this run reaches it for the first time, so the RAM writes are new
in practice though already covered in kind by 0012. No storage device and no partition other than
RECOVERY is written.

## Not granted

Any jump into the kernel copy or execution of XNU code, retries, any other image, any other partition,
any reset/data prompt answer, any other MMIO. Each needs a new decision. The mandatory boundary of
decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Host evidence only for this image (NAT-026): the loader's header, RAM/segment, ADT-room and entry
  conditions and the real `adt_patch.c` accept the payload on the host. Not host-testable and first
  seen on the phone: the RAM window `choose_window()` gets from the S-Boot DTB; whether anything in it
  is firmware memory not listed as reserved; the time that zeroing 256–512 MiB and copying 21 MB take
  with the MMU off against the 83 s watchdog.
* If the loader hangs, resets or the watchdog fires, the screen stays or goes dark on the last stage
  marker; the stage named by that marker is where to look. Download Mode and one NAT-013 restore session
  may be needed, as after runs 1–4 (run 004: the host saw `04e8:685d` about 116 s after the reboot
  request; who entered it is not established).
* The display lasted about 60–65 s in runs 002/003 and about 83 s in run 004, so late stages may not be
  visible; the reached-stage mask in every frame mitigates a missed frame, not a dark screen.
* A run without readable markers is inconclusive, not a failure of the phone. RAM contents are
  volatile; the window zero does not touch storage.
