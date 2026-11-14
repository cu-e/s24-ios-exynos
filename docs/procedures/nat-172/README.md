# NAT-172: scQ — a cpu0 clock probe and one stock DVFS request (host build)

- **Evidence kind:** host-test. No device was used.
- **Why:** NAT-170 left cpu0 100% busy, with ~80 ms of each ~98 ms frame spent in userland rendering. cpu0 is a Cortex-A520 at the
  clock S-Boot left (NAT-171). Android runs this cluster at 400–1959 MHz (672 MHz when idle) and holds it at the maximum for the
  first ~70 s of every boot.
- **Stock path (NAT-171, S):** the kernel never writes the CPU PLL or voltage. It sends FREQ_REQ
  `{2 | seq<<16, kHz, 0, timer}` on APM mailbox channel 0 and waits for the reply; the firmware does the PLL and the voltage.

## Change (only `bsd/e1s_acpm.o`; patch = NAT-123's plus these)

1. **The transport takes a channel.** The PMIC path calls it with channel 2 as before; the MFD functions and their write whitelist are
   unchanged (`build.py patch_delta`).
2. **The probe also validates channel 0** with the same checks as channel 2 and must find it AP-polled (`poll=1`, as logged on the
   phone in NAT-170). A bad channel 0 is skipped; the PMIC setup does not depend on it.
3. **`e1s_cpuclk_raise()`** runs once after "PMIC channel ready":
   - It reads PLL_CPUCL0 `PLL_CON3` (CMU_CPUCL0 0x1DC40000 + 0x10c, read only; M/P/S fields and 76.8 MHz OSCCLK as in
     `cmucal-sfr.c`/`cmucal-node.c`).
   - It times 3 × 8 Mi dependent `add x, x, #1` (32 per loop iteration, checked in the object) and keeps the best rate in adds/µs.
   - It logs the mailbox `INTMR1`.
   - **No request is sent** if the target is not one of this phone's 17 policy0 levels (boot-arg `e1scpuclk`, default 1959000; 0
     turns it off), channel 0 is not valid, the PLL does not decode, or the PLL is already within 1% of the target.
   - Otherwise it sends one `{2, 1959000, 0, 0}` on channel 0 and logs the error and the 4 reply words. After 50 ms it reads the PLL
     and times the loop again.

## Host tests (`test_nat172.py`, 17 OK)

The harness is NAT-123's fake APM plus a channel-0 "firmware" that sets a fake PLL_CON3 and logs every channel-0 command; any other
command shape counts as bad.

- **NAT-123's own 10 PMIC cases** re-run on this transport: all pass.
- **Normal:** exactly one `dvfs ch0 00ss0002 001de458 00000000 00000000`, error 0, PLL 672000 → 1958400 kHz, and both PMIC rails
  verified.
- **No request** (each with the PMIC still verified): at max; PLL disabled; channel 0 not polled, wrong type, or a bad pointer; a
  non-stock boot-arg; `e1scpuclk=0`.
- **Other cases:**
  - stock 1440000 by boot-arg is sent as `0015f900`;
  - a silent firmware gives one error 60 and the PMIC still works;
  - an ignored request shows in the after-readback.
- **Analyser** `cpuclk173.py`: verdicts on host runs and synthetic text.

## Build

| Item | Value |
| --- | --- |
| Kernel | `artifacts/nat-172/kernel-001`, no-storage `5891f6aad205b453fffad7d32b5aeece715145d10dc5321e63910a1ef2fef352`, 0 undefined; NAT-169's record with only `bsd/e1s_acpm.o` changed |
| Gates | loader sites rc 0, verdict ok; relocscan, 0 not allowed; 255 B |
| Image | `loader-diag-xnu-scQ-md1`, loader Image `42a001f5…565c`, payload `c60622b9…73c2` (26206448 B) |
| RECOVERY | `d73121352e1c538f013e8a3d09533c93aeeb304bde0186d1b6f6137179a01622` |
| Session | `session_nat173.py` `09154b464c567e0963a75eaee52cc59bcb1daa960d49cec94c4f900bd217861c` (`derive173.py --check`) |

## Risks for NAT-173 and not established

- **Firmware acceptance.** Will the firmware act without the `DM_DATA_INIT`/`DM_POLICY_UPDATE` that Linux sends on ESCA? The
  readback shows it (C-same).
- **Reply words.** Their meaning is unknown; they are logged raw.
- **Heat.** There is no thermal loop. The run lasts ≤ 270 s at a level stock Android itself uses at every boot. The DSU stays at its
  S-Boot level.
- **The add rate.** Reading it as MHz assumes a 1-cycle dependent add (Cortex-A520, inference).
