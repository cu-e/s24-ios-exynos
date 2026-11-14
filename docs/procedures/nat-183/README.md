# NAT-183: scU, the nearest-neighbour scaling copies from a per-layer run table (host)

## Why

NAT-181 (K0) showed that NAT-180's run copy saved only 0.18 ms. NAT-182 measured why on the same A520 core at the same clock, from
Android userland:
- **Run copy, NAT-180 style:** 7.83 ms. Finding the runs still reads and compares `fColumn[x]` for every panel pixel, so it costs
  about as much as the per-pixel loop (7.44 ms).
- **Runs found once, then 45 `memcpy` per row:** **2.32 ms**, with the same pixels.
- **Memory is not the limit:** a straight 10 MB `memcpy` into write-combined memory takes 1.30 ms.

## What changed (one object, additions only)

`iokit/MiniIOMobileFramebuffer.cpo` is built from `MiniIOMobileFramebuffer.patch`, against the original source and not on top of
NAT-180:
- **`struct ColumnRun { to, from, count }`.** `fColumnRun` holds `fPanelWidth` entries and is allocated beside `fColumn` at start.
- **In `drawLayer()`.** Right after `fColumn` is worked out, and only for nearest-neighbour (`!filter`), its runs are written to
  `fColumnRun` and handed to the row job as `job.runs`/`job.runCount`. That is once per layer per frame (1080 steps). If the table
  could not be allocated, or with the filter, `job.runs` is NULL.
- **In `drawRows()`.** With `job.runs`, each row is `runCount` `memcpy` calls. Without it, the unchanged per-pixel loop runs, which is
  kept as the fallback.
- **Unchanged.** The bilinear path, `fb_diff`, the unscaled path and the threading. The helpers read the same job, as they do with
  `fColumn`.

Everything else is scS (NAT-176). The command line is scS's with the tag `nat_attempt=NAT183-scU`, still 254 B.

**Kernel** `artifacts/nat-183/kernel-001`: no-storage `564946fbb7b9e27a99978e6b77c4c5eb29658162bc9fd2e2a9eb019993f2bb4a`,
0 undefined. `build.py` checks that it is NAT-176's record plus exactly this object.

## Host checks

`python3 -B docs/procedures/nat-183/test_nat183.py`: 3 OK.
- **Equivalence.** The run-table block and the row-copy block are cut verbatim from the patched source and compiled into a harness. The
  output must equal the per-pixel loop byte for byte over a guarded row, with exactly one `memcpy` per run. Maps tested:
  - the driver's 1125 → 1080 map: 45 runs;
  - a crop of it (37 runs) and an empty range;
  - an upscale 750 → 1080 (331 runs) and an offset layer;
  - 2000 random monotonic maps with repeats and jumps, with random crops.
- **No table where none belongs.** With the filter, and with no allocated table, `job.runs` stays NULL.
- **Mutants caught.** Five were tried, and all five fail the test: run condition `>=`, count += 2, `from` off by one, length in pixels
  not bytes, and the filter guard removed.
- **Patch scope.** No line is removed; the per-pixel loop is still there once.
- **On the phone in Android** (NAT-182): `table_wc` gives the same pixels as the per-pixel loop.
- **Build** `artifacts/nat-183/build-001`: loader sites rc 0 / ok / bad 0, relocscan clean, 254 B.
- **Package** `artifacts/nat-183/package-001`, image `loader-diag-xnu-scU-md1`: RECOVERY
  `bd274be10ff2b3dba21cecc62880d237a2aebdf3f35910bfc0016b6db4cb95a0`.
- **Session** `session_nat184.py` (ec619f9a…), derived by counted replacement from NAT-177's (`derive184.py --check`).

## Registered verdicts for NAT-184

These use NAT-181's analyser `docs/procedures/nat-180/fbcopy181.py`, unchanged: the median of "us each in the driver" over the steady
5 s windows.

| verdict | condition |
|---|---|
| K-none | no steady window (inconclusive) |
| K2 | ≤ 5.0 ms (expected from NAT-182: about 2.3 ms of copy plus the driver's other work) |
| K1 | < 8.0 ms |
| K0 | ≥ 8.0 ms |

Reported beside K:
- `swipe175`'s verdict and the swipe copy median (`tl: v` done − shown);
- dpp177 (it must stay R-ok and identical), cpuclk173, touch170 and frames159;
- the display verdicts and the panel thumbnail, where a wrong picture would show.

NAT-181 showed that SpringBoard can stop answering the synthetic swipes partway through a run. A swipe verdict is only compared when the
swipes animated, which shows as more than one swap per swipe.

## Not established here

- Host evidence plus an Android-userland reference only. XNU's `memcpy` differs from bionic's.
- Whether the frame rate rises: rendering takes about 12 ms of a 21 ms swipe frame.
