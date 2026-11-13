# NAT-113: Stage C3 native run — first iOS pixels confirmed in the scanned panel memory (the Apple logo)

Date: 2026-11-13. Owner: `claude-opus-nat113-run-20261113`. Decision: `docs/decisions/0043-nat113-loader-diag-xnu-sc3-md1-single-run-2026-11-13.md`.
Image: `loader-diag-xnu-sc3-md1` (RECOVERY `aedbf05f...`, built in NAT-114). Evidence kind: native-device.

## Result

**Verdict `P1-panel-has-pixels`, report complete.** At the kernel's return (63 s window) the panel memory the display DMA scans
(`0xfa200000`, 1080x2340, stride 4320) held **27,517 non-black pixels** forming the **Apple logo**, centred, on black
(`artifacts/nat-113/analysis/panel-thumb.ppm`, 108x234 RGB332 thumbnail; colour `0xe0e0c0` ≈ white in RGB332).

It is iOS's picture, not the kernel's:
* backboardd[16] swapped three frames at kernel time 229.03 / 229.10 / 229.18 s (surfaces 2, 2, 4; 1125x2436 BGRA); the first swap
  switches the text console off (`PE_initialize_console(NULL, kPEGraphicsMode)` in `show()`), and this kernel has no boot logo of
  its own (no `vc_progress`/logo lines in the log).
* The kernel's screen recording (`rec_secs=30 rec_mb=64`) began at 229.083 s and holds **3 frames, all identical** (same FNV-1a
  `0xd5b719ed`), 9,816 non-zero bytes each = 3,272 white pixels at 1/3 scale ≈ 29,448 in the 1125x2436 surface ≈ 27,156 when
  scaled to the 1080x2340 panel. The panel count is 27,517 (1.3% apart, consistent with rounding of the scaling).
* SpringBoard[13] (spawned 189.77 s) and backboardd[16] (189.39 s) are alive in the last of 7 complete ps lists; no panic.

So the chain SpringBoard/backboardd → CoreAnimation `sw_renderer` → IOSurface → `MiniIOMobileFramebuffer::drawLayer` → panel
memory works on this phone. What iOS drew is its **boot Apple logo** — the state before the lock screen.

## What this does not establish

* That the panel **lit** these pixels: nobody looked at the screen; the DECON/RDMA scan of `0xfa200000` is consistent with NAT-070
  but was not re-read here.
* Why no further frame came: after 229.18 s there was no swap for the remaining ~21 s of the window. Candidates (not tested):
  SpringBoard still starting (the lock screen appears later on real devices too), lsd CPU-monitor contention (454 denial lines), or
  a missing service. The 63 s window cap (watchdog) ends the observation ~21 s after the logo.
* Any frame rate: three swaps in 150 ms then nothing.

## Run facts

| Item | Value |
| --- | --- |
| reboot request | 2026-11-13T09:48:21.485Z |
| loader on USB (1209:0001) | +26.4 s |
| root delivery | 2,475,720,704 B, 17.27 MB/s |
| PX/PR report | +264.2 … +270.8 s, 239 records, complete |
| KL dump (why=2) | 319,981 B, 0 holes, 0 gaps |
| Download Mode (04e8:685d) | +417.5 s (deadline reset) |
| stock restore | `docs/procedures/nat-012/restore_stock.py --bus 5 --address 41`, 100,663,296 B acknowledged, session end + reboot confirmed |
| Android | `sys.boot_completed=1`, SM-S921B / e1s / S921BXXS9BYH3, user data directories present, RECOVERY SHA-256 readback = stock |
| `restore_stock.py assess` | **pass** |
| registry | native=false after the run |

## Next steps that follow from the result

1. Longer observation of the same image line to see the lock screen: needs a kernel window > 63 s, i.e. a kernel-side feed of the
   S5E9945 watchdog (NAT-071) — the loader cannot feed it while the kernel has the only CPU.
2. Find what holds the next frame (SpringBoard → lock screen): read the kernel text after 229 s for SpringBoard/backboardd stalls;
   reduce lsd contention (it was pruned for Stage A, re-added since).
3. The kernel-side changes in (1)/(2) need the one-object rebuild loop (KRN-044).
