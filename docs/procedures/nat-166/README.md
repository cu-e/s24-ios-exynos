# NAT-166: cpu0 is saturated; the touch poll is a large share of it (native-device)

- **Decision:** 0067 under 0061, one attempt, consumed.
- **Image:** scM (NAT-165): scJ, `cpuload=1000`, and a kernel that calls `redwood_cpufreq_init()` on E1S.
- **Outcome:** pass. Stock RECOVERY was restored with a full hash, and Android was verified.
- **Touch:** none.

## Load (`load166.py`)

The run produced 201 `tl: u` lines, one per second, from 183 s to 384 s. **cpu0 reads 100% in every sample, verdict L2-saturated.**

cpu1–9 also read 100%. They never run (NAT-153), so they accumulate no idle time; they are not graded.

For cpu0 the reading is meaningful. Idle time accrues only between `recount_processor_idle()` and `recount_processor_run()`, that is
when cpu0 enters `processor_idle()` (`osfmk/kern/recount.c`, `sched_prim.c:6403`). So cpu0 had a runnable thread through every whole
second of the run.

This corrects the withdrawn NAT-161 reading (`../nat-161/ERRATUM-2026-11-14.md`): the core is not half idle, it is fully busy.

`frames159` gives 9.61/s and 26.00 ms in the driver, the same as NAT-159, so the load thread costs nothing measurable.

## The touch event thread is the largest single suspect

| Interval | Time per 1000 polls |
| --- | --- |
| 123–182 s, before the home screen | **19.30–19.38 s** |
| afterwards | 18.5–21.8 s |

The same figure appears in NAT-153, 159, 161 and 164. The thread sleeps 10 ms per poll (`delay_for_interval(e1s_poll_us)`, which
sleeps for intervals this long). So **each poll spends about 9.3 ms of CPU**, which is close to half of cpu0 at about 52 polls per
second.

The cost is the bit-banged SPI. `e1s_spi_transfer()` runs `spi_delay()` three times per bit, each `e1s_halfbit` = 400 volatile loop
iterations. A 0x87 event read moves 2 + `STM_EVENT_SIZE` bytes. That gives roughly 4 kHz of SPI clock, while the stock DTS gives this
chip `spi-max-frequency = <10000000>` (`references/s24-linux` 417484173abc, `arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r*.dts`,
node `tsp_stm_spi`, `compatible = "stm,stm_ts_spi"`).

## Next

Cut the touch poll's cost without losing touch:
- a shorter half-bit (`e1s_halfbit`), still far below the 10 MHz limit;
- later, the touch IRQ instead of polling.

Then measure cpu0 load, poll period and frame rate again with the same rule. The 255-byte line is full with `cpuload=1000`, so the
half-bit goes in as the kernel default.

**Not established:**
- the per-thread split of cpu0;
- whether the idle counter would read below 100 on an idle cpu0 here: no idle phase was sampled.
