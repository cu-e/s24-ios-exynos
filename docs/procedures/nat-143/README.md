# NAT-143: scD image: a home screen that is up long enough to show a touch-caused UI action

Evidence kind: host-test. No device was used. Owner claude-opus-usb130-20261113.

## Why

NAT-142 showed finger → STM → XNU → /dev/redwood-touch → backboardd. The owner touched for minutes and saw no iOS reaction, at about
70% confidence. A re-read of its log (docs/procedures/nat-142/README.md, "After the run") finds a timing cause, not a fault:
- backboardd reported touches (`TouchDetectionMode` 0x1) only from 238 s;
- the home screen came at ~243 s;
- the timed return came at ~252 s (`loader_return_after=150` counted from ~102 s).

So the UI could take touches for ~14 s, and the home screen was up for ~10 s.

## Changes against scC (NAT-141)

| Item | scC | scD | Why |
| --- | --- | --- | --- |
| `loader_return_after` | 150 | **270** | the home screen is up from ~243 s until ~372 s instead of ~252 s |
| loader deadline (`NAT044_DEADLINE_S`) | 475 | **595** | receive cap 240 + 270 + loader work 60 + pixel report 25 = 595 ≤ 600 (the NAT-079/NAT-115 rules, asserted in build.py) |
| `rec_secs` | 150 | **270** | the screen recording stays on over the same window (`rec_mb=64`, a ring of about 70 frames at 1/3 scale) |
| kernel | 9213cff4… | **6aa8b6eb…** | `e1s_touch.o` only: every STM press and release is logged with its kernel time, `e1s-touch: press N: finger F x X y Y` / `release N: …` (at most 512 lines); moves are not logged |
| session | watcher/collector 600 s | **720 s** | Download Mode comes at about +620 s after the reboot (deadline 595 s from the loader's start at ~+21 s) |

The rest is scC's: the engine (NAT-130), the root, md0, every other cmdline token (246 B), and the start sequence.

The coordinate nibble order was checked against Samsung's `struct stm_ts_event_coordinate` (stm_dev.h:259-266). There, byte 3 holds
`y_3_0:4` then `x_3_0:4`, LSB first, so x = b1<<4 | b3>>4 and y = b2<<4 | b3&0xf. The derived e1s_touch.c already has this order;
only the donor's original 0003 patch had the two nibbles swapped. No change was needed.

The kernel watchdog rule is unchanged: if the feed is not proven, the kernel itself cuts `loader_return_after` back to 63 s
(`e1s_wdt_window`, NAT-115).

## Analyser (registered before the run)

`analyze144.py` reports every analyze142 verdict, plus:

- **Clocks.** The log text is two streams: the console (launchd with os_log wall time, HakiOS lines) and then the kernel ring
  (`[t]`). With no RTC, the wall clock runs on uptime. Each run measures this. launchd's `spawned with pid N` is compared with the
  kernel's first `memorystatus_update(enter): pid N`. NAT-142 has 53 pairs, with a median offset of -0.005 s and all within
  -0.02..+0.54 s. `clock_check` is ok when there are at least 3 pairs and the median is within 1 s.
- **UI timeline.** The HakiOS `touch detection mode` lines and `unlock: asked, answer 1` give `home_at`. That unlock is the donor's
  automatic one, 10 s after SpringBoard's start; it is not a touch.
- **ui verdict.**
  - **U2-app-launched-after-press** is given when an application other than `com.apple.Spotlight` first appears in launchd's
    `UIKitApplication:` lines after the home screen, at most 20 s after a press made on the home screen, and clock_check is ok.
    Spotlight is excluded because SpringBoard starts it by itself (NAT-118 to NAT-140, without touches).
  - Otherwise the verdict is U1 (presses on the home screen, but no such application) or U0.
- **Other reports.** W1-press-then-wake (a mode 0xfe → 0x1 change within 5 s after a press). Also the count of recorded frame
  changes within 2 s of a home-screen press, a count only, because frames change without touches too.

## Tests (host)

| Command | Result |
| --- | --- |
| `TMPDIR=<scratch> python3 -B -I docs/procedures/nat-143/test_nat143.py` | 8 OK: NAT-141's five cases on the NAT-143 patch (Samsung start order, write audit, no-READY bound, summary, old wiring); press/release lines with raw x/y; moves not logged; the patch differs from NAT-141's only in the touch log |
| `python3 -B docs/procedures/nat-143/test_analyze144.py` | 7 OK. On NAT-142's real text: S3/E1, modes 0xff→0xfe→0x1→0, home at ~242 s, U0, W0, 24 frame changes, clock_check ok (53 pairs). Synthetic additions give U2 (press, then Preferences 10 s later), U1 (Spotlight only; app 25 s after the press), U0 (app before the home screen), U1-app-after-press-clock-unverified (wall clock shifted 60 s), W1 |
| `python3 -B -I docs/procedures/nat-143/derive144.py --check` | counted derivation from session_nat142.py (ced8653c…) |

## Build

| Item | Value |
| --- | --- |
| Kernel | `artifacts/nat-143/kernel-001` (KRN-044), kernel.no-storage 6aa8b6eb27009e16d0e7a618c5e4becca6f36561ac5b632912bdda13078fd100, 0 undefined, 29 stubs. After normalizing the path, loader_return.o, redwood_input.o, e1s_acpm.o and e1s_pmic.o are byte-identical to NAT-141's; e1s_touch.o differs |
| Image | `loader-diag-xnu-scD-md1`; RECOVERY da5c03c2c41af74332a054062de2a7e7de3e3bc987bc93e55ea2aafd68dc1cda, payload 55ad4eea5cf069c6fa4d826825b4259862e6e28761a621dbcc5a8ae69f39d963 (26199248 B), loader Image 02ede202c61547565df9fcec25ee35fa8f84004e8f89df1fa74668a0ba879354. Of the loader objects, only 08-markerlib52.c.o differs from scC (the deadline define) |
| Cmdline | 246 B: scC's with `nat_attempt=NAT143-scD`, `loader_return_after=270`, `rec_secs=270` |
| Session | `session_nat144.py` 17b86433bb746a8ee61f33c0423dd77b301df5ab5961d23d342c655271f11010 |

## Known risks for the native run

- **Log size.** NAT-142's returned text was 459 KB (319 KB console, 140 KB kernel) against the 8 KiB head + 512 KiB tail of the dump.
  Two more minutes, with app launches, may exceed that. The loss would then be the oldest console lines (boot), not the home-screen
  part or the kernel ring. The clock check uses all pids present, including late ones.
- **Unobserved state.** No run has kept iOS up for more than ~10 s after the home screen. A later fault (memory, a crash) is possible
  and would itself be a finding.

## Not established

This is host evidence only. It does not show that iOS acts on a touch; NAT-144 tests that on the phone.
