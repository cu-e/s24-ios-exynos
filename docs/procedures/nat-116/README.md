# NAT-116: native run of `loader-diag-xnu-sc4-md1` (150 s kernel window, wait dump)

Evidence kind: **native-device** (one RECOVERY-only run on the S24, 2026-11-13, decision 0045 under 0044/0019), plus
host analysis of what the host received. Owner: `claude-opus-nat116-20261113`.

## Run and restore (measured)

* Preflight `ready-read-only` (stock RECOVERY `96620b8b...`, battery 84 %, 30.6 °C). Execute: RECOVERY readback
  `c0642059...` matched, reboot at 12:05:44Z.
* USB: loader 1209:0001 at +20 s; delivery of the 2.48 GB md1 root `delivered` (16.7 MB/s); loader gone at +492 s;
  Download Mode 04e8:685d at +496 s (the NAT-044 deadline path, as designed).
* Restore: `nat-012/restore_stock.py --bus 5 --address 44` acknowledged 100,663,296 B, session end + reboot confirmed;
  Android booted (`sys.boot_completed=1`, SM-S921B / e1s / S921BXXS9BYH3), RECOVERY readback = stock, user-data
  directories present; `nat-013 assess` = **pass**. Native permit closed.

## What the returned log shows

The KL dump (why=2, 938,750 B kernel log: 8 KiB head + 512 KiB tail received, a 406 KB gap) and the PX/PR report arrived complete.

1. **SpringBoard crashes in a loop. The crash was not visible in NAT-113 because its window ended at 250 s.** `SpringBoard[13]`, spawned at
   ~189 s, aborts at **288.46 s** (`userabort: SpringBoard[13] aborts`), then launchd respawns it every ~5-6 s:
   pids 70, 75, 78, 81, 84, 87, 90, 94, 9 aborts in total until 334 s (`service has crashed 3 times in a row`). Every
   instance logs the same exception:

       *** Assertion failure in -[_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:], _UIScreenComplexBoundingPathUtilities.m:326
       *** Terminating app due to uncaught exception 'NSInternalInconsistencyException', reason: 'Failed to load bounding path
       bitmap data from the asset manager for asset name: BoundingPathBitmap-1125x2436-375x812-3.00x'

   The kernel's `userabort` back traces have the same frames as the userland "First throw call stack", so the
   two records are of the same abort.
2. **Frames**: backboardd swapped the logo at 228.14/228.21 s (recording: 2 frames, FNV `0xd5b719ed` = the NAT-113 logo).
   At **278.05 s** backboardd swapped with no surfaces (`swap 3/4: surfaces 0 0 0 0`, layers cleared). At the return the panel
   memory is **black** (`panel_nonzero 0`; decode113 verdict `R1-recording-has-pixels`, meaning the recording holds the logo
   and the panel holds nothing). No frame other than the logo was produced.
3. **Window**: `--- loader_return_after expired ---` at 336.49 s kernel time, which is 150 s after the 186.5 s bsd_init
   and not the 63 s cut. The phone was not reset by the 83 s watchdog during that time. This fits the kernel
   feed working. The `e1s_wdt: fed ...` line itself was **not received**: it was printed before the received tail, inside
   the gap. So `analyze116.py` gives **X-window** by its strict rule (`fed=None`).
4. **Wait dump**: `waitdump: begin`, the first line (`launchd.darwin[1] threads 5`), then a **kernel panic**:
   `Console I/O from interrupt-disabled context @serial_console.c:168`. The patch calls `printf` per thread
   under `ml_set_interrupts_enabled(FALSE)` (kernel-combined.patch, wait_dump), and the DEVELOPMENT kernel's serial
   console forbids that. The panic path returned to the loader as designed. No thread states were captured, so the
   H-verdict is **X-none**. The question it was meant to answer was resolved by item 1 instead.

## Verdict

* By the pre-registered rule: `X-window` (feed line in the log gap) and `X-none` for H1-H4 (the wait dump panicked).
* What the run established instead: **H1-H4 are all superseded.** SpringBoard was not waiting. It was still starting
  (H1 partially right: 63 s was too short to see the next event), and then it **crashed deterministically** in UIKit
  (`_UIScreenComplexBoundingPathUtilities`) because the asset catalog returned no bounding-path bitmap for the iPhone X
  screen. No lock screen can appear while this abort happens.

## Cause hypothesis for the abort (host-checked, not yet tested on the phone)

* The asset exists by name: `UIKitCore.framework/BoundingPathData.bundle/Assets.car` of the root holds
  `BoundingPathBitmap-1125x2436-375x812-3.00x`. CoreUI catalogs select renditions by device traits (idiom, subtype,
  scale, gamut), which UIKit takes from MobileGestalt. MobileGestalt reads them from the device tree's `/product` node.
* **The image's ADT has no `/product` node.** The pinned `artifacts/nat-020/build-003/e1s.adt` has the children `chosen defaults
  cpus arm-io sweet-fbcon buttons options pram sweet-ufs`, and the payload has no `artwork-device-subtype` string. The
  donor's `tools/e1s/xnu/mkadt.py` adds `/product` from `research/ipsw-x/d22ap.adt` only when that file exists
  (`d22ap_product()`); that path is absent from the NAT-020 source tree.
* The real D22AP `/product` (from `DeviceTree.d22ap.im4p` of the local 20F66 IPSW, LZFSE-decoded with
  `tools/ios/lzfse_py.py`) carries `artwork-device-subtype` = 2436 (`0x984`), `artwork-scale-factor` = 3,
  `artwork-device-idiom` = `phone`, `artwork-display-gamut` = `P3`, `graphics-featureset-class` = `APPLE4`, `product-name`
  = `iPhone X`. The donors (Scion loader `identity_product`, ios-apollo `mkadt.py --artwork-subtype`)
  ship this node, and mkadt replaces the gamut with `sRGB`.
* Next image (NAT-117, host): the NAT-115 image with the ADT = pinned e1s.adt + the D22AP `/product` node built the
  way mkadt builds it, and the wait dump fixed (no printf with interrupts off) or removed. The run (NAT-118) answers
  whether SpringBoard gets past `_loadBitmapForScreen` and whether a frame other than the logo follows.

## Not established

That the panel lit any pixel (nobody looked at the screen); the cause of the abort (above is a hypothesis); input; GPU;
frame rate.

## Commands

    python3 docs/procedures/nat-115/session_nat115.py --out artifacts/nat-116/preflight-001 --image loader-diag-xnu-sc4-md1
    python3 docs/procedures/nat-115/session_nat115.py --out artifacts/nat-116/run-001 --image loader-diag-xnu-sc4-md1 --execute
    artifacts/recovery-rescue-20261110-01/venv/bin/python -I docs/procedures/nat-012/restore_stock.py --bus 5 --address 44 --out artifacts/nat-116/restore-001/restore-trace
    python3 docs/procedures/nat-012/check_android.py artifacts/nat-116/restore-001/android-check.json
    artifacts/recovery-rescue-20261110-01/venv/bin/python -I docs/procedures/nat-013/restore_stock.py assess --report artifacts/nat-116/restore-001/report.json --readback artifacts/nat-116/restore-001/android-check.json
    python3 docs/procedures/nat-113/decode113.py artifacts/nat-116/run-001/archive --json artifacts/nat-116/analysis/pixels.json --ppm artifacts/nat-116/analysis/panel-thumb.ppm
    (kl_reader.read_archive(...)['dumps'][1]['text'] -> artifacts/nat-116/analysis/kernel-text.txt)
    python3 docs/procedures/nat-115/analyze116.py --kernel-text artifacts/nat-116/analysis/kernel-text.txt --pixels artifacts/nat-116/analysis/pixels.json --out artifacts/nat-116/analysis/verdict.json
