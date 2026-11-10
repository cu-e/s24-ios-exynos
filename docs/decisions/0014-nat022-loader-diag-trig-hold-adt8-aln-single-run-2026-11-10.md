# 0014: One native run of the NAT-022 `loader-diag-trig-hold-adt8-aln` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code session, in answer to a
question (asked in Russian) that named the reason for the new image (native run 005 of decision 0013
reached the loader's `MEM`, `ZERO` and `COPY` stages and then reported, from inside the loader,
SLOT 4, ESR `0x96000061` = alignment fault on a store, ELR `0x800a9954` = `adt_set_dram+0x268`, FAR
`0x9e2d743fc`; cause found on the host by two independent routes: the loader runs with the MMU off, so
data accesses are Device memory and must be naturally aligned, while `adt_patch.c` stored the 64-bit
`dram-size` ADT value at an address aligned only to 4 bytes), the fix (every 64-bit ADT property access
replaced by two aligned 32-bit accesses), the host checks (alignment-trap reproduction: old source
faults, new source does not; static scan 4 findings before and 0 after; byte-identical ADT output;
`make check` passes), the loader `Image.payload` and RECOVERY image SHA-256s, the device access (as
decision 0013), what the loader will do (still stops at `PRE_JUMP`, no jump), the risks and the
recovery path, with the choice "Да, один запуск loader-diag-trig-hold-adt8-aln".

## Scope

Exactly one image: NAT-022 `loader-diag-trig-hold-adt8-aln`
(`artifacts/nat-022/build-006/loader-diag-trig-hold-adt8-aln/Image.payload`, SHA-256
`2fb3968787688f4feb5b1dc09e4622309f1e22e5e8d76c82178d8716f1642da9`, 21767776 bytes; the loader `Image`
is `f0e61342dabb231098b71a13eb023a47d068adcec39fca1dc4b86e8d868f4cb7`, 212992 bytes), packaged with the
NAT-006 builder into the RECOVERY image SHA-256
`cdf4f3a15831fb7c6c488085da33c12ade231460323583fd4090114945b285cd`
(`artifacts/nat-022/package-006/package.json`). Source commit `c5b942a` (NAT-027 evidence:
`docs/procedures/nat-022/evidence-nat027.json`). Compared with the run-005 image the loader code differs
only in `adt_patch.c` (five 64-bit ADT property accesses become pairs of aligned 32-bit accesses); the
payload is the same `adt_size`-fixed payload (`payload.adt8.bin`). The image stage markers, dwell and
DECON0 kicks are those of decisions 0012/0013, and the image still halts at `PRE_JUMP` instead of
jumping: the held marker is a statement about the loader, not about XNU, and the kernel copy is never
entered. Sequence: full-hash write to RECOVERY (`/dev/block/sda18`) only, full readback, one
`adb reboot recovery`, owner-operated camera recording (~2 minutes), then restore of the pinned stock
RECOVERY (`session_aln.py --restore` if Android returns, otherwise Download Mode and one NAT-013
session). Driver: `docs/procedures/nat-022/session_aln.py` with its own one-shot marker
`artifacts/nat-022/native-attempt-loaderhold-aln-used.json`.

## Device access granted (and nothing else)

Identical to decision 0013: DECON0 main block `0x19100000` (reads `GLOBAL_CON`, `TRIG_CON`,
`FRAME_COUNT`, `SHD_REG_UP_REQ`; writes `TRIG_CON` and `SHD_REG_UP_REQ` in the vendor driver's order;
only with the MMU off, only after the first marker, never after an earlier kick faulted), the
framebuffer at `0xFA200000`, the PMU INFORM register `0xbc` (`0x12860000`), the S5E9945 watchdog at
`0x10040000` armed for 83 s, GIC initialisation (`0x10200000`, `0x10240000`), and the loader's RAM
work: zero the window it chose from the S-Boot DTB (256–512 MiB, outside the DTB's reserved ranges, the
loader image, the payload, the framebuffer and the log area), copy the ~21 MB payload segments and the
ADT/boot_args into it, patch the ADT copy, clean data caches over it. Run 005 completed the zeroing
and the copy; this run is the first to reach the ADT patch, `boot_args`, the full-window cache clean
and the `PRE_JUMP` hold. No storage device and no partition other than RECOVERY is written.

## Not granted

Any jump into the kernel copy or execution of XNU code, retries, any other image, any other partition,
any reset/data prompt answer, any other MMIO. Each needs a new decision. The mandatory boundary of
decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Host evidence only for this image (NAT-027): the alignment-trap build of the real `adt_patch.c`
  faults on the run-005 source and not on this one, the static scan of the loader's unscaled accesses
  finds none, and the earlier header, RAM/segment and ADT-room checks pass. Not host-testable and not
  covered: data accesses whose addresses are computed at run time outside `adt_patch.c`; the RAM
  window `choose_window()` gets from the S-Boot DTB; whether the full-window cache clean fits the
  83 s watchdog together with the ≈ 7 s zeroing and ≈ 1 s copy measured in run 005 (the clean is
  unmeasured); whether anything in the window is firmware memory not listed as reserved.
* If the loader hangs, resets, the watchdog fires or another fault occurs, the screen stays or goes dark
  on the last stage marker, or an exception record (stage, ESR, ELR, FAR) is shown; that is where to
  look. Download Mode and one NAT-013 restore session may be needed, as after runs 1–5 (who enters
  Download Mode is not established).
* The display lasted about 60–65 s in runs 002/003 and ≥ 83 s in runs 004/005, so late stages may not be
  visible; the reached-stage mask in every frame mitigates a missed frame, not a dark screen.
* A run without readable markers is inconclusive, not a failure of the phone. RAM contents are
  volatile; the window zero does not touch storage.
