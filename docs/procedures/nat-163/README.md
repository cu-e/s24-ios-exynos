# NAT-163: scL, scJ with per-swap timing lines (host-test)

- **Evidence kind:** host-test. No device was used.
- **Next step:** NAT-164 runs scL once.

## Why

NAT-161 showed that, on the idle home screen, the single core is about 50% idle. Frames still come only every ~100 ms (about 10 per
second, in every run since NAT-159). The driver's statistics lines cannot tell why.

`touch_lat=1` makes the kernel print the timing lines below (`references/s24-port` c8860dec) into the loader console log we already
read back (`loader_log_line`):

| Line | Source | Meaning |
| --- | --- | --- |
| `tl: s ID at US` | `MiniIOMobileFramebuffer.cpp:873` | every swap handed over (SwapEnd) |
| `tl: v ID ready US shown US done US` | `MiniIOMobileFramebuffer.cpp:1051` | every frame: GPU done, its beat came, pixels in the panel's memory |
| `tl: p TYPE FINGER X Y at US` | `bsd/dev/redwood_input.c:124` | every touch sample posted |

These lines separate the cases:
- CoreAnimation hands over a frame only every ~100 ms, so the swap interval is about 100 ms;
- a frame waits inside the driver (`swap_to_done` much larger than the copy);
- frames wait for the beat.

With touch, the same lines give touch-to-panel-memory latency.

## Image

scJ's command line with `touch_lat=1` after `fb_filter=0`, and the tag `NAT163-scL`: 254 bytes. Everything else is unchanged:
- the payload is byte-identical to scJ's after the cmdline field;
- of the loader objects, only `08-markerlib52.c.o` differs (the image name);
- the loader checkpoint check gives rc 0 on the NAT-143 symbols;
- relocscan finds 0 relocations that are not allowed.

| Item | Value |
| --- | --- |
| RECOVERY (`artifacts/nat-163/package-001`) | `6ab4112f6f9102443b4b7b472562e30aa37f27b17dbd953cdfead7cf50d67f5a` |
| `Image.payload` | `93a2989acf6ea87dd4055bf63065da5e05b1bf95020d317b50da4c393f57e00b` |
| Session | `session_nat164.py` (`derive164.py`, counted from `nat-158/session_nat159.py`, 8 lines) |

The per-core load line (`tl: u`, `redwood_cpufreq.c`) needs a separate `cpuload=MS` boot argument, and the 255-byte line has no room
for it. `docs/procedures/nat-161/cpu161.py`, which uses the `ps` snapshots, remains the CPU measure.

## Decoder (`tl164.py`)

The decoder reports, separately for swaps idle and swaps within 1 s of a touch sample:
- the swap interval;
- the beat wait (ready→shown);
- the copy (shown→done);
- swap→done;
- the share of 60 Hz intervals;
- touch-to-panel latency: the sample → the first swap after it → its `done`. This is the kernel's part only; it says nothing about
  the panel or a camera.

## Commands

| Command | Result |
| --- | --- |
| `python3 -B docs/procedures/nat-163/build.py --out artifacts/nat-163/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs` | rc 0, 254 B, gates pass |
| `python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-163/build-001 --out artifacts/nat-163/package-001` | rc 0 |
| `python3 -B docs/procedures/nat-163/derive164.py --check` | pass |
| `python3 -B docs/procedures/nat-163/test_nat163.py` | 7 OK (synthetic lines in the exact formats; the kernel carries them) |
