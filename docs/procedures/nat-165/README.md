# NAT-165: scM, per-core load lines with kernel timestamps (host-test)

- **Evidence kind:** host-test. No device was used.
- **Next step:** NAT-166 runs scM once.

## Why

NAT-161's CPU split from `ps` snapshots was withdrawn (`../nat-161/ERRATUM-2026-11-14.md`). Whether the single core is saturated on
the idle home screen is still open. NAT-164 showed the driver is not the limit: CoreAnimation hands over a frame every ~106 ms, and
the driver needs 26 ms of that. A per-core busy share with kernel timestamps decides it. The upstream kernel has it already:
- boot-arg `cpuload=MS`;
- `bsd/dev/redwood_cpufreq.c` `load_thread`;
- output lines `tl: u at US CORE:PCT …` through `loader_log_line`.

On E1S, though, `redwood_input_init()` never calls `redwood_cpufreq_init()`: references/s24-port `0002-e1s-input.patch` puts it
under `#else`. That function is what calls `load_start()`.

## Kernel (`artifacts/nat-165/kernel-001`, no-storage `f13b7c346cbb0c74f8485787f1b1076fc734f44e1c9e8df17d72041b4245d92f`)

The kernel is NAT-152's seven rebuilt objects with the same patches, except `bsd/redwood_input.o`. That object's patch
(`redwood_input.patch`) is NAT-121's, every line kept, plus `redwood_cpufreq_init();` with a comment in the E1S branch.

The source built (derive-001) equals the pinned upstream `redwood_cpufreq.c` byte for byte. With no `cpufreq=` and no `ddr=`
boot-arg, `redwood_cpufreq_init()` does only this:
1. `load_start()`, which starts the thread only if `cpuload` is set;
2. `ddr` defaults to 2, and acts only with `cpufreq_wanted()`;
3. returns at `if (!cpufreq) return`.

So it changes no clock, voltage or DDR vote. The test checks this from the source text.

The new `redwood_input.o` references `_redwood_cpufreq_init`; NAT-152's does not. bsd objects link after every osfmk object, so the
loader-checked addresses do not move: the loader's own check gives rc 0, and the 13 constants sit on the NAT-143 symbols.

## Image

scJ's command line with `cpuload=1000` after `fb_filter=0`, and the tag `NAT165-scM`: **255 bytes**, the maximum the chain allows.
There is no `cpufreq`, `ddr` or `membench` token.

| Item | Value |
| --- | --- |
| RECOVERY (`artifacts/nat-165/package-001`) | `f0e1cfd923c89e8f202427f6815b7adfc1adc94bdd66dc9022a61dd9c6049257` |
| `Image.payload` | `1450397b04b9a433f1c17b00dac7ee4687bf388f87304aa7ab1ebedbb6b7f8aa` |
| Session | `session_nat166.py` (`derive166.py`, counted from `nat-158/session_nat159.py`, 8 lines) |

## Decoder (`load166.py`)

`load166.py` reads the `tl: u` lines inside `frames159`'s steady windows and gives:
- per core, the median, minimum and maximum busy %;
- a grade for core 0, the boot CPU and the only running one: **L2** saturated (≥ 90%), **L1** busy (60–90%), **L0** headroom.

Cores that never run accumulate no idle time and may read as busy, so they are not graded.

## Commands

| Command | Result |
| --- | --- |
| `krn-044/rebuild.py` with NAT-152's arguments and `--extra bsd/redwood_input.o=docs/procedures/nat-165/redwood_input.patch`, `--expect-string 'tl: u at %llu'` | rc 0, 0 undefined |
| `python3 -B docs/procedures/nat-165/build.py --out artifacts/nat-165/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs` | rc 0; NAT-152 gate passed; relocscan 0 not allowed |
| `python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-165/build-001 --out artifacts/nat-165/package-001` | rc 0 |
| `python3 -B docs/procedures/nat-165/test_nat165.py` | 6 OK |
