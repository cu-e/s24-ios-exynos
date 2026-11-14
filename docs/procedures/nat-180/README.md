# NAT-180: scT, the nearest-neighbour scaling copies runs of columns (host)

## Why

NAT-175 and NAT-177 measured the framebuffer driver at 8.77–8.91 ms per frame on the only running core. Almost all of it is CPU scaling
of the 1125×2436 iOS surface onto the 1080×2340 panel (`fb_filter=0`, nearest neighbour). The per-pixel loop does one load and one store
for each of the 2.5 million panel pixels.

Hardware scaling through DPP1 (NAT-178's plan, NAT-179) is stopped by the safety classifier and waits for the owner. This task touches no
display register. It only makes the existing software copy cheaper.

## What changed (one object)

`iokit/MiniIOMobileFramebuffer.cpo` is built from `MiniIOMobileFramebuffer.patch`:
- **Removed.** In `drawRows()`, the non-filter branch's loop `for (x = cx0; x < cx1; x++) to[x] = from[fColumn[x]];` (three lines).
- **Added.** `copyColumnRuns()` walks `fColumn` and copies each stretch where the source column rises by exactly one with one `memcpy`.
  - With 1125 → 1080 one source column in 25 is left out, so a panel row is **45 runs** of about 24 pixels (96 B) each.
  - Any other map (repeats when upscaling, jumps, crops) simply ends a run there.
- **Unchanged.** The bilinear path (`fb_filter=1`), the `fb_diff` counting loop, the unscaled path, the column map itself and the
  threading.

Everything else is scS (NAT-176): the read-only display snapshot, the swipe thread, `touch_lat=1` and the cpu0 FREQ_REQ. The command
line is scS's with the tag `nat_attempt=NAT180-scT`, still 254 B.

**Kernel** `artifacts/nat-180/kernel-001`:
- no-storage `bdb71bd6ca366b7565a6252f42876486cb088a958fb7b870c16dea8bff76f4b4`, 0 undefined;
- `build.py` checks that it is NAT-176's record plus exactly this object, with the same expect-strings;
- NAT-176's view for nat-123's four-object check is extended to hide that one verified object.

## Host checks

`python3 -B docs/procedures/nat-180/test_nat180.py`: 5 OK.

- **Equivalence.** The helper is cut from the patched source and compiled on the host. Its output is compared byte for byte with the
  replaced loop, over a guarded 4096-word row. Maps tested:
  - the driver's own formula for 1125 → 1080 (45 `memcpy` calls), a crop of it and an empty range;
  - an upscale 750 → 1080, with repeated columns;
  - an offset layer;
  - 2000 random monotonic maps with repeats and jumps and random crops.
- **Mutants caught.** Three were tried, and all three fail the test: a run condition of `>=`, a length one too long and a start one off.
- **Patch scope.** The only removed lines are the three loop lines. `copyColumnRuns(` appears only in its definition and in the one call.
- **Analyser** `fbcopy181.py`. Boundary verdicts were tested on synthetic statistics lines. On NAT-177's real log it gives
  K0 / 8.914 ms / copy 8.77 ms / F30, which is the baseline.
- **Build** `artifacts/nat-180/build-001`: loader sites rc 0 / ok / bad 0, relocscan clean, 254 B.
- **Package** `artifacts/nat-180/package-001`, image `loader-diag-xnu-scT-md1`:
  - RECOVERY `4aa3d32ca90c98c2e810e49892454f945386b63f384d6af1e7ee9221bdd653ac`;
  - payload `4a520259a1403d2467092a4eb6c915c172aca678b866c63fbf979290d24df24d` (26207328 B).
- **Session** `session_nat181.py` (0fb770a1…), derived by counted replacement from NAT-177's (`derive181.py --check`).

`test_nat180.py` gained the analyser tests after `build-001`. Because it is not a build input, `build.json`'s `nat180_sources` holds its
earlier hash. `evidence.json` lists the final hashes.

## Registered verdicts for NAT-181 (`fbcopy181.py`)

The driver time is the median of MiniIOMobileFramebuffer's own "us each in the driver" over the steady 5 s windows (NAT-159's
`frames159` rule). The baseline from NAT-177 is 8.914 ms.

| verdict | condition |
|---|---|
| K-none | no steady statistics window (inconclusive) |
| K2 | driver median ≤ 5.0 ms |
| K1 | driver median < 8.0 ms |
| K0 | driver median ≥ 8.0 ms: no gain shown |

`swipe175`'s verdict (F60 ≤ 18 ms, F30 ≤ 36 ms, F-low) and the swipe copy median are reported beside K. The other NAT-177 analysers are
rerun as well: dpp177, cpuclk173, touch170, frames159 and the display verdicts. The display verdicts are how the run would show a
corrupted panel; the host test is the evidence that the pixels are unchanged.

## Risk specific to this image

- The `memcpy` targets the same write-combined framebuffer mapping and the same addresses the loop wrote. Only the access width changes.
- No register, no new mapping and no new memory are involved.
- An error in the run logic would show as a wrong picture, not as a hang. The host tests exclude that error for the tested maps.

## Not established here

- Host evidence only: how much time the phone saves, which depends on write-combining bandwidth to DRAM.
- Whether a shorter driver time turns into more frames. Rendering also takes most of each interval: NAT-177's other_ms is 86.7 ms per
  frame at the idle median.
