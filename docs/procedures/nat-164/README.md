# NAT-164: per-swap timing of the idle home screen (native-device)

- **Decision:** 0066 under 0061, one attempt, consumed.
- **Image:** scL = scJ + `touch_lat=1` (NAT-163).
- **Outcome:** pass. Stock RECOVERY was restored with a full hash, and Android was verified.
- **Touch:** none in this run.

## Verdict: T-cadence

`tl164.py` read 363 swap lines and 363 frame lines:

| | Median | p10–p90 |
| --- | --- | --- |
| Swap interval (SwapEnd to SwapEnd) | **105.8 ms** | 91.7–112.4 ms |
| Beat wait (ready → shown) | 0 | 0 |
| Copy (shown → pixels in panel memory) | 26.0 ms | 25.9–26.1 ms |
| Swap → pixels in panel memory | **26.06 ms** | 26.0–26.2 ms |

The driver puts every frame in the panel's memory 26 ms after it is handed over. No frame waits for the beat or behind another
frame. CoreAnimation hands over a new frame only every ~106 ms, so the ~10 frames/s seen since NAT-159 is the rate at which userland
produces frames. It is not the driver. Whether it is a CPU limit is **not established**: NAT-161's "50% busy" is withdrawn (`../nat-161/ERRATUM-2026-11-14.md`). The `ps` deltas here (SpringBoard 21.9 s, launchd 7.2 s, in a span of roughly 40 s known only to within the 8.5–27 s `ps` run times) point to a busy core rather than an idle one.

`frames159` gives 9.77/s and 26.02 ms, the same as NAT-159, so the instrumentation costs nothing measurable.

The panel shows the home screen with two widgets and the stock icons, among them the live Clock icon
(`artifacts/nat-164/analysis/panel-thumb-x3.png`). Animated content of that kind is the likely source of the redraws. That is not
established.

## Consequence

The idle home screen does not measure the path's capacity. Capacity needs continuous interaction. Two routes:
- the owner swipes during the run (the decoder already splits frames under touch, and gives touch-to-panel latency);
- a kernel-side synthetic gesture: the touch driver posts a scripted swipe on a timer. This needs no owner and is repeatable.

## Erratum (same day)

This task's `evidence.json` summary says "not … the CPU (single core ~50% busy, NAT-161)". That clause rests on the withdrawn
NAT-161 figure (`../nat-161/ERRATUM-2026-11-14.md`). The verdict itself, T-cadence, stands: the driver finishes every frame within
26 ms and does not hold frames.

What the ~80 ms between frames is spent on is open. It may be userland work on a saturated core, which the `ps` deltas suggest; with
SpringBoard and launchd the largest consumers, mediaserverd's crash-and-respawn loop is a candidate. Or it may be the content's own
cadence. A per-core idle measurement (`cpuload=MS`) with kernel timestamps decides between them.
