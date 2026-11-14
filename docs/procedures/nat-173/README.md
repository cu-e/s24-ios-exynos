# NAT-173: cpu0 doubled to 1958 MHz by one stock DVFS request (native-device)

- **Decision:** 0070 under 0061, one attempt, consumed.
- **Image:** scQ (NAT-172).
- **Outcome:** pass, verdict **C2**. Stock RECOVERY was restored with a full hash, and Android was verified; its own DVFS was active
  again, with policy0 reading 1152000 after boot.
- **Touch:** none.

| | Before | After one `FREQ_REQ {2, 1959000, 0, 0}` on APM channel 0 |
| --- | --- | --- |
| PLL_CPUCL0 `PLL_CON3` | `0xa0190200`: M 25, P 2, S 0 = **960 MHz** (S-Boot's level) | `0xa0660400`: M 102, P 4, S 0 = **1958.4 MHz** |
| Dependent adds per µs | 959 | 1958 |
| Firmware reply | — | error 0; words `00010000 001de458 00000000 00000000` (index field cleared, kHz echoed) |

- The add rate matches the PLL decode to the MHz. This confirms the 1-cycle-add reading of the probe and that the request took
  effect within 50 ms.
- The firmware accepted the request without the ESCA DM init that Linux sends. NAT-171's open question 1 is answered for this case.

## Effect, against NAT-170

| | NAT-170 (960 MHz) | NAT-173 (1958 MHz) |
| --- | --- | --- |
| Framebuffer driver per frame | 17.89 ms | **8.93 ms** |
| `frames159` | 10.16/s, interval 98.4 ms | 9.58/s, interval 104.3 ms |
| cpu0 busy (`load166`) | 100% | median 100%, minimum **36%** |
| Touch poll (`touch170`) | 11.82 s per 1000 polls | 11.43 s, 0 high-line events |
| Display | W-ok, D2, S1, P2 | the same |

## Reading

- **CPU work halves.** The kernel's CPU work per frame halves with the clock.
- **The idle home screen is not CPU-bound.** Its frame rate does not change: CoreAnimation hands over about 10 swaps per second
  whatever the clock (NAT-164's T-cadence). The idle screen therefore cannot show 60 FPS capacity.
- **Next measurement.** Frames during an animation: a home-screen page swipe, posted by a kernel thread through the same
  `redwood_touch_post` path real touches use (NAT-144). Then swap intervals per gesture (`tl164.py`).
- **cpu0 still reads ~100% busy most seconds.** What keeps it busy at a fixed frame cadence is open (crash-respawn loops such as
  mediaserverd are suspects).

## Not established

- The frame rate under animation.
- The DSU/L3 clock, which stays at S-Boot's level.
- Temperature: there is no readout.
- The meaning of the reply word 0.
