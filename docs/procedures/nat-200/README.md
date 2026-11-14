# NAT-200: why SpringBoard aborts with ten CPUs (native, decision 0082)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-e2r-md1 (NAT-199), one run on 2026-11-14 (reboot 09:59Z).
Afterwards stock RECOVERY was restored with a full hash check, and Android was verified:
- nat-013 assess: pass;
- `check_android.py`: pass, recovery_hash_match true.

The phone reached Download Mode by itself.

## Result: R-reason (reason200), with S2-all again (smp198)

- **Ten CPUs again.** `GenericARMPE: 10 of 10 processors are running` (104.94 s), no panic. At the timed return cpu2 began the
  stop path, and the boot CPU finished it.
- **SpringBoard aborted three times.** pid 13 at 241.86 s, with no touch before it; then pid 122 twice, at 316.49 s and later.
- **The reason**, copied by the NAT-199 scan (2 scans; 1 distinct text):

  ```
  Terminating app due to uncaught exception 'NSInternalInconsistencyException',
  reason: 'Invalid parameter not satisfying: routingContextUID'
  ```

  The first-throw stack, symbolised with `dscsym.py` (slide 0x24090000):
  1. CoreFoundation;
  2. `objc_exception_throw`;
  3. Foundation (the `NSAssert` handler);
  4. **MediaPlayer** +0x1c8;
  5. **MediaControls** +0x98;
  6. libdispatch;
  7. `_pthread_wqthread`.

  MediaControls, the Now Playing / media-route UI inside SpringBoard, hands MediaPlayer an empty audio routing context.

## Interpretation (to be checked, not established)

**The route context.** It comes from the media server. mediaserverd crash-loops with SIGSEGV in every run since NAT-118:
- launchd respawns it about every 5 s;
- 10 exits in NAT-198, "crashed 37…40 times in a row".

**Why only on ten CPUs.** In four one-CPU scV runs (NAT-186, 188, 192, 196) SpringBoard never aborted. The likely reading: with
ten CPUs, MediaControls' dispatch work runs while there is no route context, and with one CPU it ran later or not at all. It is a
reading, not yet a measurement.

**The fix candidates follow the cause.**
- Make mediaserverd stop crashing. First its fault needs recording: no `usertrap` lines, because boot-arg `systrace` is off.
- Or keep MediaControls from asking for a route while there is none.

## Beside it

- **Display and touch.** W-ok, D2. Touch P1 (E1-coordinates). C2 (cpu0 1958.4 MHz).
- **Busy share.** top186 U-free, busy share 0.108.
- **Frames.** Not comparable: SpringBoard restarted inside the swipe window, and fbcopy181 found no steady window (K-none).
  - bbd188 B2: 4.1 ms of backboardd CPU per frame, a median over few frames.
  - Swipe frame rate 45.3, a single window.

## Files

- Analysis: `artifacts/nat-200/analysis/` (`reason200.json`, `smp198.json`, `verdict.json`, `kernel-text.txt` and the scV
  analysers); `artifacts/nat-200/analyse.sh`.
- Run: `artifacts/nat-200/run-001`. Restore: `artifacts/nat-200/restore-001`.
- Inventory: `devices/local-2026-11-14-nat200.json` (local, untracked).
