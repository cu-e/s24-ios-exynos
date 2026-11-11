# NAT-052: XNU C checkpoints over the USB log engine (host-test image)

Evidence kind: **host-test**. Nothing in this directory has run on the S24. The image below was built and exercised only in the
unicorn-based simulators of NAT-036 (resume model) and NAT-047 (DWC3 device model + the unmodified NAT-041 collector). A simulated
host seeing a simulated device is not hardware evidence, and `QEMU virt`/unicorn are not an Exynos model.

## Why

The checkpoint images of runs 008-009 report how far the kernel got only as coloured frame bands that a camera has to film. The owner
asked for the computer to receive the messages of a real native run by itself. NAT-041/NAT-047 give the loader an EP0-only DWC3 device
engine that a host collector pulls from; NAT-036 gives the kernel a resumable path through C checkpoints 11-16 and 30-44. This task joins
them: at every checkpoint the loader's stub queues one text record, so the computer learns the stop, its register values and, at the
end, the hold, without any camera.

## What was built

`build.py` derives the image `loader-diag-xnu-ckpt3-usb` from the committed NAT-036/NAT-047 patch pipelines plus `patch_ckpt52.py`
(exact-match anchors, each exactly once, all-or-nothing). The new code is `src/glue52.h` and `src/glue52_impl.h`; everything else is the
unmodified NAT-020/022/036/041/042/045/047 sources (their hashes are in `build.json` and checked by `test_nat052.py`).

At each call of `nat036_ckpt_c` (the five asm stops and the 17 default C stops, 22 arrivals) the stub, which already runs MMU-off and by
physical address, now does in this order:

1. `nat036_report` (unchanged), then `kv = nat052_vbar_enter()`: if `VBAR_EL1` is not the loader's, install the loader's vectors
   (captured by `nat052_capture_vbar()` right after `nat047_bringup()`), so a fault in the polled engine lands in the loader's handler,
   not in the kernel's still-unmapped vectors;
2. `nat052_note_stop(&r)`: one TEXT record
   `CK n=N arr=A last=L x2= x3= mask= sctlr= sp= kttbr0= vbar= setups=<delta>[ esr= elr= far=]` (the last three only for an early
   exception, `x2 & 0xff == 1`); field order is the contract with `decode52.py`;
3. the existing pass: bands redrawn and then `nat052_service()` (a fixed 0.3 s of engine polling) instead of the camera dwell;
4. `nat052_vbar_leave(kv)`: give the kernel's vectors back and return into the kernel by the NAT-036 resume path.

At the final hold (`MK_CKPT3` hold, the last stop) `nat047_hold(MK_ST_CKPT, mask)` emits `HOLD stage=0x.. code=0x..` and the loop keeps
polling and showing frames until the NAT-044 deadline reset (`--deadline-s`, default 60 s after the 83 s watchdog arm; values above 63 are
refused). The engine is never serviced from XNU itself: between stops the kernel runs with the engine unattended.

One collision was resolved: NAT-047 used frame kind 13 for `MK_USB`, which NAT-036 already uses for `MK_CKPT3`. `patch_ckpt52.py` moves
`MK_USB` to 15 in this image only; `docs/procedures/nat-047/decode47.py` must not be used on this image's frames (a test pins that).

## Findings (host-test)

* The glue adds exactly four hunks to NAT-036's `markerlib3.c` (include, pass, hold note, hold show), four to `ckpt3.c` (include, enter,
  declaration, leave), one to `marker.h` (`MK_USB`) and two to `loader.c` (declaration, the one call); NAT-047's own hunks are used unchanged
  except one `loader.c` include anchor (tests `Patch`).
* Build is reproducible (two builds, same SHA-256), has no SIMD and no misaligned access (capstone disassembly + `scan_unaligned`), keeps
  stub, stack, log and loader end in one 2 MiB block at each loader base seen so far (`0x800a0000`, `0x80180000`, `0x801a0000`), and
  emits only the known run-006 `loader.c:67` `-Wunterminated-string-initialization` warning.
* The model chain (NAT-035/036 resume model with a recording double of the glue): per arrival the order is enter, note, pass, leave; the hold
  has no leave; the kernel state after the last stop equals an uninterrupted run (`Chain`).
* With the unmodified NAT-041 collector (`interval 0.02`, `io_timeout 1000 ms`, `dead_after 30 s`, `grace 10 s`, no ack channel) and kernel
  gaps with **no polling at all** between stops (profile `GAPS_S`, longest 8 s), all 22 notes arrive complete and in order with a zero drop count,
  the hold is announced after the last note, the earlier loader log precedes the first note, the loader's vectors are installed during every
  service window and the kernel's are back after it, the whole run is at the hold well before the 60 s deadline, and the stack in use stays
  below a quarter of the loader's (`UsbFull`).
* An early exception in the model (arrival 8) is reported with esr/elr/far and only for that stop (`UsbException`). If the engine never came
  up, every call completes, the vector swap still happens, the hold is reached and the deadline reset comes with no log (`UsbEngineDown`). A
  short stop list gives a short but complete record (`UsbShort`).
* Mutation check (`mutants.py`, not part of `make check`): see `evidence.json` for the result of the recorded run.

Run everything: `capvenv/bin/python -W ignore -I docs/procedures/nat-052/test_nat052.py` (45 tests, about 65 s; the venv needs unicorn and
capstone; `TMPDIR` on a disk with a few hundred MB). Mutants: `... docs/procedures/nat-052/mutants.py --json OUT`. Build:
`python3 -I docs/procedures/nat-052/build.py --out artifacts/nat-052/build-NNN --loader-source artifacts/nat-020/build-003/source`, package:
`python3 -I docs/procedures/nat-047/package.py --build artifacts/nat-052/build-NNN --out artifacts/nat-052/package-NNN`.

## What is not established

* Real DWC3 behaviour after a no-poll gap (stale events, a host timeout that wedges the controller) is untested; the simulator has no caches,
  MMU, interrupts or real controller. The engine's DMA block is in the loader image: stale cache lines on it are possible and untested.
* The service window is fixed (0.3 s per pass, no acknowledgement channel). A note that the host does not pull inside that window stays in
  the engine's ring until the next window; the ring can fill (the engine counts drops) if the kernel runs long between stops and the
  host is slow. `setups=` is a delta of control transfers served since the previous note, not a count of stops.
* The HSI0 power/clock/PHY/DWC3 register writes of the NAT-045 ladder are the first writes to that block from this loader; NAT-043 is the
  image that tests them without the kernel, and its hardware result is the precondition of any run of this image.
* The time budget depends on real kernel gaps and draw times; the NAT-044 deadline reset is the only fail-safe, and its hardware result
  is NAT-046 (re-enumerated as Download Mode at +73.0 s, one observation).
* Kernel execution past checkpoint 16 is not covered; the kernel's `TTBR0` changes in `arm_vm_init` and the stub refuses later stops.
* The acceptance wording "SPSR/ELR of the return" has no counterpart in a resumable return (there is no exception return); the record
  carries the NAT-035 resume state instead, and `esr/elr/far` for an early exception.

## Decision draft and next steps

`decision-draft.md` is the text of the decision file for one native run of this image. It is not a decision, nothing was asked of the
owner and nothing was run. It needs, in this order: NAT-043 passing on hardware (the log channel exists), a session driver and analyser for
this image (child task NAT-057), the udev rule (NAT-050, owner's root), then a run-time owner confirmation.
