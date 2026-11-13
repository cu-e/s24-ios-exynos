# NAT-120: the whole iOS home screen on the physical panel (`loader-diag-xnu-sc6-md1`)

Evidence kind: **native-device** + **owner observation**. One RECOVERY-only run, 2026-11-13, decision 0047 (under 0044/0019).
Owner: `claude-opus-nat116-20261113`.

## Run and restore (measured)

Preflight `ready-read-only` (stock RECOVERY, battery 84 %, 39.4 °C). Execute: readback `e430d54e...` matched, reboot 13:53:09Z;
loader 1209:0001, md1 delivered, Download Mode 04e8:685d at the deadline. `nat-012/restore_stock.py --bus 5 --address 50`:
100,663,296 B acknowledged; Android booted, RECOVERY = stock, user-data directories present; `assess` pass. Permit closed.

## Result

* **Owner observation** (answer to a question after the run, verbatim choice): "The whole iOS home screen (icons, background)".
  First owner-confirmed complete iOS 16.5 home screen on the S24's physical panel. Not a photograph; time of the look not recorded.
* `analyze120.py` (rule fixed in NAT-119): `W-ok` / **`D2-refreshing`**, iOS verdict `F1-new-frame`. 14 kernel kicks of DECON0
  (`e1s_decon: kick 3..16`, kernel 199.5-329.6 s, every 10.0 s): `FRAME_COUNT` +1200/+1201 per 10 s = **120.0 refreshes/s** of the
  panel while iOS ran; `TRIG_CON 0x3063` before and after (HW trigger enabled, not masked); `GLOBAL_CON` alternates 0x113/0x133
  (bit 5, as seen by NAT-022, uninterpreted). The first two kick lines fell in the log gap.
* SpringBoard: no abort. MiniIOMobileFramebuffer: 7 frames/s, ~54 ms per frame in the driver (CPU copy/scale), 0 µs GPU wait.
* Panel memory at the return: 1,149,579 non-black pixels (home-screen layout, `artifacts/nat-120/analysis/panel-thumb-ascii.txt`);
  the loader no longer drew over it.

## What changed the outcome vs NAT-118 (owner saw only the bottom bar)

1. The loader stopped painting marker bands over panel rows 0-2063 after the kernel's return (`nat119_no_draw`).
2. The kernel's DECON0 HW-form kick. Note: TRIG_CON already read `0x3063` (HW trigger on) at the logged kicks, so whether the kick
   was *needed* for refresh during the kernel window is not separated from the loader's last pre-jump kick; what is measured is
   that the panel refreshed at 120 Hz throughout the window.

## Not established

The lock screen as a separate state (the donor hook auto-answers unlock); input (touch disabled); GPU acceleration (CPU renderer);
60 FPS of *content* (panel refresh is 120 Hz, but iOS produces ~7 frames/s).
