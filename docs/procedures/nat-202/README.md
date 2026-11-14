# NAT-202: where mediaserverd faults (native, decision 0083)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-e2s-md1 (NAT-201), one run on 2026-11-14 (reboot 10:30:54Z).
Afterwards stock RECOVERY was restored with a full hash check, and Android was verified:
- nat-013 assess: pass;
- `check_android.py`: pass, recovery_hash_match true.

The phone reached Download Mode by itself.

## Result: T-media (trap202)

**mediaserverd faults at one site, the same every time.** There are 46 `usertrap:` lines, all mediaserverd's and no other
process's. launchd reports 10 exits due to SIGSEGV; the counter reaches "crashed 46 times in a row".

| | |
|---|---|
| exception | `EXC_BAD_ACCESS`, code 0x1 0x0 |
| pc | **0x0**: a call through a null function pointer |
| lr | CoreImage +0xcc into a local function (unslid 0x194b1458c) |

The frames, symbolised with `dscsym.py` (slide 0x1040000):
1. CoreImage ×4;
2. CMCapture ×2;
3. libdispatch ×2;
4. CMCapture ×2.

**The faulting call.** Disassembly at 0x194b14588 shows `blr x8`, with `x8` loaded from a table of function pointers on the stack
and arguments `(ctx, 0x0B71)`. The next two calls in the same table pass `0x0C11` and `0x0BD0`. Those are `GL_DEPTH_TEST`,
`GL_SCISSOR_TEST` and `GL_DITHER`: CoreImage disables GL state through its OpenGL ES dispatch, and the entry is empty.

**The caller.** Up the stack, CMCapture calls `+[BWCoreImageFilterRenderer context:err:]` (class decoded from the ObjC metadata),
which makes a `CIContext`. It is reached from 0x1a2115c0c, the start of
`+[BWCoreImageFilterRenderer prewarmPortraitFilterVersion:semanticStyleFilters:]`.

**The donor's account.** HackiOS (`references/hakios` 87bf485, `userland/src/inject_media.c`) explains this exact fault:

> the capture stack "prewarms" the Core Image filters of the portrait mode, for which Core Image wants an OpenGL ES context;
> there is no GPU, the context has no functions behind it, and the daemon jumps to address 0 -- every time launchd restarts it.

The donor replaces that method with an empty one in its library `libhakios.media.dylib`, which the kernel inserts into
mediaserverd. Our md0 `etc/inject.conf` lacked that line. NAT-203 adds it.

## Beside it

- **reason200: R-reason.** SpringBoard aborted three times, pid 13 at 274.2 s, then pid 131 twice. Each time it was the
  same `Invalid parameter not satisfying: routingContextUID`, as in NAT-200.
- **smp198: S2-all.** `GenericARMPE: 10 of 10 processors are running` at 111.2 s; no panic.
- **Display and touch.** W-ok, D2-refreshing, P2 (both rails verified), C2 (rate ratio 2.04). Touch: 3 of 3 ID reads, event
  thread up.
- **Frames.** Not comparable: SpringBoard restarted. fbcopy181 K-none, swipe175 S-none, bbd188 B0.
- **Busy share.** top186 U-free, median 0.064.

## Corrections recorded here

- **`trap202.py` after the run.** It could not symbolise pc 0, because a negative "unslid" address went to `dscsym.py`. The fix,
  made after the run and to symbolisation only, passes addresses below the slide unlooked-up. The verdict rules are unchanged.
- **`session_nat202.py` docstring.** Its first line describes the image as "e2r with boot-arg systrace=1 in place of
  touch_lat=1". That is the abandoned first approach of NAT-201. The image that ran, by its pinned hashes, is the NAT-201 one:
  `user_exception_trace_enabled` defaults to 1 and no `systrace` boot-arg is set. The driver's body and hashes are correct.
  `derive204.py` corrects the text in the next driver.
- **NAT-201's `evidence.json`.** It gives `recorded_at` 15:55Z. The real time was about 10:28Z, before this run. The file is
  hash-pinned in the registry, so the mistake is recorded here instead.

## Files

- Analysis: `artifacts/nat-202/analysis/` (`trap202.json`, `reason200.json`, `smp198.json`, `verdict.json`, `kernel-text.txt`
  and the scV analysers); `artifacts/nat-202/analyse.sh`.
- Run: `artifacts/nat-202/run-001`. Restore: `artifacts/nat-202/restore-001`.
- Inventory: `devices/local-2026-11-14-nat202.json` (local, untracked).
