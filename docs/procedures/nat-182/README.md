# NAT-182: copy-bandwidth reference on the A520 cpu0 (Android userland)

**Evidence kind:** android-userland. An own static test binary, `copybench.c` (NDK 28.2 clang, `-O2 -static`), was run once through
`adb shell` from /data/local/tmp, pinned to cpu0 (CPU part 0xd80, Cortex-A520, the core iOS runs on in our native images) and then
deleted. No setting was changed: the governor stayed `energy_aware`, and cpu0's `scaling_cur_freq` read 1959000 kHz before and after
every test, the same clock as the C2 native runs.

## Why

NAT-181 left the framebuffer scaling at 8.74 ms per frame, a time that scales with the core clock and barely with the instruction count.
The question was whether the limit is the write-combined store path, the source reads, or the code.

## Results (`artifacts/nat-182/run-cpu0-v2.txt`, 15 repeats, caches flushed of the source before each)

| test | median | what it says |
|---|---|---|
| `pixel_wc`: the driver's per-pixel nearest loop → WC | 7.44 ms | the same order as native 8.74 ms (the native figure also includes the driver's other work) |
| `pixel_cached`: the same → cached | 7.38 ms | the destination type does not matter |
| `runs_wc` / `runs_cached`: NAT-180's run copy | 7.83 / 7.87 ms | no gain, as on the phone in NAT-181 |
| `runs_cached_clean`: + `dc cvac` of the panel | 8.41 ms | a cached panel plus a cache clean is worse |
| **`table_wc` / `table_cached`: runs found once, 45 `memcpy` per row** | **2.32 / 2.32 ms** | **3.2× faster, same pixels (checked)** |
| `memcpy_wc`: a straight 10 MB copy → WC | 1.30 ms | the floor: write combining is not the limit |
| `memset_wc` / `memset_cached` | 0.42 / 0.41 ms | the store path to WC is as fast as to cached |
| `read_src`: 11 MB cached read | 1.08 ms | the source reads are cheap |
| `read_wc_lines`: one load per 64 B from WC | 8.26 ms | reading WC is slow; the driver never reads the panel (`fb_diff=0`) |

## Conclusion

The copy is bound by the code, not by memory:
- **Where NAT-180 fell short.** Its `copyColumnRuns` still loads and compares `fColumn[x]` for every panel pixel to find the runs, which
  costs about as much as the per-pixel copy did on the in-order A520.
- **What works.** Finding the runs once, when the column map is made (it changes only with the layer geometry), leaves 45 `memcpy` per
  row. That takes 2.32 ms on the same core and clock, against 7.4 ms.
- **Why the clock fits.** The time scaling with the core clock (NAT-170 against NAT-173) fits this: it was instructions all along, and
  a run copy that still visits every pixel saves almost none of them.

Next:
- **NAT-183 (host).** The run table in MiniIOMobileFramebuffer, built beside `fColumn`; `drawRows()` copies from it.
- **NAT-184 (native).** Verdict K2 (≤ 5 ms) is expected.

## Not established

- **Native time.** XNU's arm64 `memcpy` is not bionic's, and the native driver also does work besides the copy, so the native figure
  needs NAT-184.
- **Frame rate.** Whether a shorter copy turns into more frames: rendering takes about 12 ms of a 21 ms swipe frame (NAT-175).
