# NAT-198: ten CPUs running in XNU on the S24 (native, decision 0081)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-e21-md1 (NAT-197), one run on 2026-11-14 (reboot 09:28:43Z).
Afterwards stock RECOVERY was restored with a full hash check, and Android was verified:
- `artifacts/nat-198/restore-001/report.json`, from the nat-012 trace;
- nat-013 assess: pass;
- `check_android.py`: pass, recovery_hash_match true.

The phone reached Download Mode by itself. No button press was needed.

## Result: S2-all (smp198), C2-all-ten (analyze150)

- **All ten registered cores ran.** `GenericARMPE: 10 of 10 processors are running` at 107.19 s. cpu1–cpu9 joined within the
  1 s start wait. No failure line, no early-marks line, no fault, no panic.
- **The drop worked on every core type** (A520, A720, X4). No core reached NAT-195's fallback probe, so no core was still at EL2.
- **The stop path worked at the timed return.** cpu5 began the return (`psci: cpu 5 ends the system: the return to the boot loader is
  the boot processor's to make`). The boot CPU completed it, with no `did not stop` note, and Download Mode followed.
- **Work ran in parallel.** e1s-top's 250 s window recorded 5.22 s of process CPU time in a 4.95 s span, which one core cannot do.
  The busy share over the swipe windows fell from 0.993 (NAT-196, one CPU, U-sat) to 0.154 (U-free).

## What is not yet right

1. **SpringBoard aborts under SMP.** `userabort: SpringBoard[13]` came at 216.42 s, 0.33 s after the first synthetic press.
   SpringBoard[115] aborted the same way at 301.64 s. In the one-CPU scV runs SpringBoard stayed alive (NAT-196: S1).
   - The stack, symbolised with `docs/procedures/nat-189/dscsym.py` (slide 0x3731c000) and identical both times: `abort` ←
     libc++abi ← libobjc ← `std::terminate` ← libdispatch ← `_pthread_wqthread`. That is an uncaught Objective-C exception in a
     dispatch block on a workqueue thread.
   - The exception reason is not in the kernel log.
2. **The frame measures are not comparable with scV.** SpringBoard restarted twice inside the swipe window:
   - fbcopy181 had 4 steady windows (scV: 36);
   - swipe frame rate median 20.4, max 60.3;
   - driver copy median 0.86 ms (scV 1.99);
   - bbd188 46.3 ms of backboardd CPU per frame, median of 7 spans.

   No frame-rate claim is made from this run.
3. **The topology is flat.** Every core registered as `cluster_id 0`, `type 0`. The A520/A720/X4 clusters are not described to the
   scheduler (roadmap S10).
4. **The secondaries' clocks were not set.** Only cpu0's FREQ_REQ (C2, 1958.4 MHz) was made (S11).

Unchanged against scV:
- display W-ok, D2;
- touch170 P1, with presses logged (E1-coordinates);
- cpuclk173 C2;
- mediaserverd crash-loops as in scV (10 SIGSEGV exits here, 5 in NAT-196).

## Next

- **The SpringBoard exception.** Get its reason; the `NSException` text goes to SpringBoard's os_log, not to the kernel log. Then
  decide whether it is a race that only SMP exposes, or a timing or ordering effect, for example in the synthetic swipe.
- **S10.** Cluster topology in the device tree / ADT.
- **S11.** Per-cluster clocks through the stock ACPM FREQ_REQ.
- **S12.** Frame measures against scV once SpringBoard stays up.

## Files

- Analysis: `artifacts/nat-198/analysis/`:
  - `smp198.json`, `verdict.json`, `kernel-text.txt`;
  - fbcopy181, bbd188, top186, cpuclk173, touch170, e2p196 and pixels.
- Analysis script: `artifacts/nat-198/analyse.sh`.
- Run: `artifacts/nat-198/run-001`, `artifacts/nat-198/run-001.log`.
- Restore: `artifacts/nat-198/restore-001`.
- Inventory: `devices/local-2026-11-14-nat198.json` (local, untracked).
