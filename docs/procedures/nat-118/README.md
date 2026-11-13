# NAT-118: native run of `loader-diag-xnu-sc5-md1` (D22AP /product in the ADT)

Evidence kind: **native-device** (one RECOVERY-only run, 2026-11-13, decision 0046 under 0044/0019). Owner:
`claude-opus-nat116-20261113`.

## Run and restore (measured)

Preflight `ready-read-only` (stock RECOVERY, battery 84 %, 31.0 °C; preflight-001 stopped at the decision gate because the file
did not name "decision 0019" literally; fixed in the text, no device action). Execute: readback `9696818f...` matched, reboot
12:48:41Z; loader on USB, md1 delivered, Download Mode 04e8:685d at the deadline. Restore with `nat-012/restore_stock.py --bus 5
--address 47`: 100,663,296 B acknowledged; Android booted, RECOVERY = stock, user-data directories present; `assess` **pass**.
Native permit closed.

## Result (`analyze118.py`, rule fixed in NAT-117): `W-ok` / **`F1-new-frame`**

* **SpringBoard no longer aborts.** No `userabort: SpringBoard`, no bounding-path exception (NAT-116 had 9 aborts). The `/product`
  hypothesis is supported: the abort is gone and only the ADT and `wait_dump=1` changed.
* backboardd swaps: logo at 236.5 s; layer cleared at 282.9 s; **new content from 293.4 s**, then continuous swaps.
  MiniIOMobileFramebuffer statistics: 1 frame/s at 301-313 s, then **6-7 frames/s** from 318 s to 339 s (≈54-60 ms per frame in the
  driver, 0 µs waiting for the GPU; drawing is the CPU software renderer).
* Recording: 73 frames (full 64 MiB), the first 4 are the logo, **69 differ from the logo** (from kernel 295.6 s).
* **Panel memory `0xfa200000` at the return: 1,149,581 non-black pixels** (NAT-113: 27,517 = logo; NAT-116: 0). The 108x234
  thumbnail (`artifacts/nat-118/analysis/panel-thumb-ascii.txt`) shows the structure of the iOS **home screen**: a status-bar row at
  the top, two large widgets, four rows of four app icons each with a label row under them, a small search/page pill, and a dock
  of four icons at the bottom. The colours are mostly white/grey, with blue and green icon areas.
* `hakios: unlock: asked, answer 1`: the donor's SpringBoard hook answers the unlock request itself, so the system goes to the home
  screen without a lock-screen interaction. `SBCoverSheetPrimarySlidingViewController` (the lock-screen/cover sheet) is
  instantiated in the log.
* Other: mediaserverd crashes 5 times with SIGSEGV (launchd respawns it); no kernel panic; the window ended by its timer at 150 s.

## What this establishes and what not

Established (native-device): real iOS 16.5 SpringBoard draws its home screen through CoreAnimation's CPU renderer, and
the picture is in the memory the panel scans, at about 7 frames/s.

Not established:
* that the physical panel shows it. Nobody looked at the phone during the run. The display controller still scanning
  0xfa200000 after S-Boot is unmeasured (IOS-003 R15), so the next run needs the owner's eyes or a photo.
* the lock screen as a separate state. The hook unlocks by itself. Seeing the lock screen needs that hook off or a
  frame from before the unlock: the recording holds 69 frames from 295.6 s, and only statistics, not pixels, come back over USB.
* input (touch is disabled: `e1stouch=0`), GPU acceleration (none), and 60 FPS (measured 6-7 frames/s).
