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
produces frames. It is neither the driver nor a CPU limit: NAT-161 measured the single core about 50% busy.

`frames159` gives 9.77/s and 26.02 ms, the same as NAT-159, so the instrumentation costs nothing measurable.

The panel shows the home screen with two widgets and the stock icons, among them the live Clock icon
(`artifacts/nat-164/analysis/panel-thumb-x3.png`). Animated content of that kind is the likely source of the redraws. That is not
established.

## Consequence

The idle home screen does not measure the path's capacity. Capacity needs continuous interaction. Two routes:
- the owner swipes during the run (the decoder already splits frames under touch, and gives touch-to-panel latency);
- a kernel-side synthetic gesture: the touch driver posts a scripted swipe on a timer. This needs no owner and is repeatable.
