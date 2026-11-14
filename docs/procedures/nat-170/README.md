# NAT-170: the gated touch poll frees ~40% of cpu0's poll time; cpu0 still saturated (native-device)

- **Decision:** 0069 under 0061, one attempt, consumed.
- **Image:** scO (NAT-169): shadowed GPP9 `DAT` and the touch poll gated on gpa1-2.
- **Outcome:** pass, verdict **P1**. Stock RECOVERY was restored with a full hash, and Android was verified.
- **Touch:** none.

| | NAT-168 | NAT-170 |
| --- | --- | --- |
| ID reads | 3/3 ok | 3/3 ok, same bytes |
| Seconds per 1000 polls | 19.47 | **11.82** (P1) |
| Gate after 21000 polls | — | line low in 3, skipped 20157, high-line reads 840 with **0 events** |
| Device ID read | 5.241 ms | **2.457 ms** |
| `frames159` | 9.55/s, driver 25.94 ms, other 78.8 ms | **10.16/s**, driver **17.89 ms**, other 80.5 ms |
| cpu0 (`load166`) | 100% (L2) | 100% (L2, 78 steady samples) |
| Display | W-ok, D2, S1, P2 | the same |

## Reading

- **The access cost.** The ID read fell by the predicted share. Per bit it went from 4 loads + 3 stores to 1 load + 3 stores, which
  puts a GPIO load at about 10.6 µs and a store at about 5.8 µs (estimate, `touch170.py`). Bus reads on this phone are very slow under
  this kernel.
- **The poll.** It now costs ~1.8 ms per 10 ms period, the 1000-poll slope minus the sleep. That remainder is mostly wakeup latency
  on a busy core and the full read every 25th poll.
- **The gate.** It lost nothing at idle (0 events on 840 check reads). A touch run is still needed to check it under events.
- **The driver.** Its time per frame fell 26 → 17.9 ms with no change to the driver. The likely cause is that the touch thread no
  longer preempts it (inference).
- **cpu0 is still 100% busy.** About 80 ms of each ~98 ms frame interval is spent outside the driver. Freed CPU went to userland
  rendering, and the frame rate rose only 6%. The limit is now rendering speed on one Cortex-A520 (NAT-171), so the next levers are
  its clock (NAT-171), more cores and the GPU.

## Not established

- The gate with a finger on the screen.
- cpu0's clock under this loader.
- Why the driver time fell.
