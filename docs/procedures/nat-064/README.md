# NAT-064: a root device for the payload kernel (`rd=md0` -> ramdisk) and the NAT-063 `!BSD` line

Evidence kind: **source-review** (pinned XNU/loader sources) plus a **host-test** (payload rebuild and comparison, `compare_payloads.py`). Nothing here ran on the S24.
Line numbers are those of the unpatched XNU 22.5.0 copy `worktrees/vm-007-20261105/artifacts/avf-kernel-source/cache/originals/xnu` (hashes in `evidence.json`); the payload kernel
is built from that tree plus the project patches (`artifacts/nat-020/build-003/source/xnu/{hackios/redwood.patch,e1s/patches}`), which is why the panic of NAT-063 names
`IOKitBSDInit.cpp:841` where the unpatched file has the call at 808.

## Result in brief

1. **`!BSD` is by design, not a fault.** The project's own kernel patch (`hackios/redwood.patch`, `iokit/bsddev/IOKitBSDInit.cpp`, hunk at old line 683) shortens the wait for the `IOBSD`
   resource to **100 ms when `rd=md*`** is set (`bsdWait = kSecondScale / 10`). The task card assumed a 30 s wait; that premise was wrong. The log shows the wait took about
   **102.5 ms** of kernel time (below), i.e. the thread slept and was woken at its deadline: the kernel's sleep/timer path worked on the phone.
2. **The cause of the NAT-063 panic is exactly what the log said**: `rd=md0` is already in the payload's command line, but the ADT has no `/chosen/memory-map` `RAMDisk` property, so `mdevlookup(0)` finds nothing.
3. **The fix is a payload change only**: `mkpayload.py --ramdisk IMAGE` (pinned, unchanged) adds one segment and one ADT property; the loader already rebases the property. Rebuilding the existing payload
   without ramdisk is **byte-equal** to `artifacts/nat-020/build-003/payload.bin`; the NAT-062 payload differs from a rebuild with its command line in **one byte** (the header's `adt_size`, patched by NAT-062 from 13956 to 13960).
4. **A ramdisk makes `adt_size` 14008 (a multiple of 8) by itself**: the NAT-062 `adt_size` header fix (13956 -> 13960) was written for an ADT without the property and must not be carried over (13956 + 52 = 14008 already satisfies the rule).
5. The `loader_return_after` timed return was never exercised (NAT-063 returned through the panic), but the timer path it depends on has now been seen to work; its quiesce calls are Qualcomm-driver code guarded by
   "was started" flags (reviewed below, not run).

## Path from `rd=md0` to PID 1 (source review)

| Step | Where | What happens |
|---|---|---|
| boot-arg | payload cmdline (`payload.bin` offset 0x48, 608-byte field): `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=... debug=0xc serial=3 cpus=1 keepsyms=1 -v` | `rd=md0` was already there in NAT-020 .. NAT-063; `e1sufs=0 ufsrw=0` keep the project's UFS code away from storage (no UFS line in the NAT-063 log) |
| 1. wait for `IOBSD` | `IOKitBSDInit.cpp:683-690` (+ patch: 100 ms for `rd=md*`) | `waitForMatchingService(IOResources{IOResourceMatched=IOBSD}, t)`; NULL -> `IOLog("!BSD")`; nothing publishes `IOBSD` here (no filesystem kext/storage), so it times out by design |
| 2. ramdisk -> device | `IOKitBSDInit.cpp:746-766` | once (`didRam`): `/chosen/memory-map` property `RAMDisk` = `{phys, size}` (two `uintptr_t`, 16 bytes; size <= `UINT_MAX<<12`) -> `mdevadd(-1, ml_static_ptovirt(phys)>>12, size>>12, 0)` (`bsd/dev/memdev.c:640`, phys=0: the base is a kernel VA). The patch adds the same for `RAMDisk1` (-> `md1`, never root) |
| 3. root name | `IOKitBSDInit.cpp:773-808` | `rdBootVar` = `md0`: `mdevlookup(0)` (`memdev.c:717`); found -> `BSD root: md0, major M, minor m` (794), `goto iofrootx`; **not found -> `panic("IOFindBSDRoot: specified root memory device, md0, has not been configured")` (808; 841 in the patched build) = NAT-063** |
| 4. mount | `bsd/kern/bsd_init.c:860-870` | loop `setconf(); vfs_mountroot()`; on failure `rootdevice[0]=0` and the loop repeats (`IOFindBSDRoot` sleeps 5 s on `mountAttempts`): **a failed mount hangs, it does not panic** |
| 5. filesystem | upstream doc `artifacts/nat-020/build-003/source/docs/e1s-userland.md` | APFS is tried first; a raw Mach-O is no APFS container, so the last entry `mockfs` mounts it and resolves `/sbin/launchd` to that file |
| 6. root auth | `bsd_init.c:444-461, 908` | `bsd_rooted_ramdisk()` (`rd=md0`) skips `FSIOC_KERNEL_ROOTAUTH` |
| 7. exec PID 1 | `bsd/kern/kern_exec.c:6892-6915` (`load_init_program`) | `launchdsuffix` boot-arg; `release` skips the `launchd.development` names and loads `/sbin/launchd` (upstream test line: `launchdsuffix=release cs_enforcement_disable=1`; `kern_cs.c:167` reads the latter, needed for the ad-hoc-signed test binary) |
| 8. PID 1 ends | `bsd/kern/kern_exit.c:1806-1831` | if PID 1 exits the kernel **panics**: `initproc failed to start -- no exit reason available -- (signal S, exit status N ...)` (`initproc_spawned` is only set by a real launchd); `N` is chosen by the test init |

`sweet-init` (`tools/e1s/sweet-init.S` -> `mkinit.py`, static ad-hoc-signed arm64 Mach-O, 16635 bytes, SHA-256 `93041871cea969e53211ffede941a7ca31bc666cf20faffd1d47dde6a84f0104` built here with clang 18) opens `/dev/console`, writes a PID line,
tries `mount("apfs","/mnt",RDONLY,"/dev/md1")`, then writes a heartbeat every 5 s (`select` as sleep) forever. It is the project's test `/sbin/launchd`, **not Apple's launchd**.

## Payload: rebuild and what a ramdisk changes (host-test, `compare_payloads.py`, result in `compare-result.json`)

| Check | Result |
|---|---|
| `mkpayload.py kernel.no-storage e1s.adt --cmdline <NAT-020 cmdline>` vs `artifacts/nat-020/build-003/payload.bin` | **byte-equal** (`071bc632...caf544`, exit 0). The task card names `Image.payload`: that file (21759584 bytes, `2b51c791...3e729`) is the NAT-020 loader `Image` (204800 bytes) followed by exactly this `payload.bin` (21554784 bytes) — checked, its tail equals the rebuild |
| same with the NAT-062 cmdline vs the NAT-062 patched payload (`a0562ac4...23ea`) | differs in **one byte** at offset 40 (`adt_size`: rebuild 13956, NAT-062 13960 = NAT-062's fix for the loader's multiple-of-8 rule) |
| with the stage-0 ramdisk (`--ramdisk sweet-init`), NAT-062 cmdline + ` launchdsuffix=release cs_enforcement_disable=1` | 11 segments (10 + the ramdisk at VA `0xfffffff008974000`, 0x8000 bytes = 16635 rounded to 16 KiB pages, file offset 21540848); `kernel_end_va` `0xfffffff008974000` -> `0xfffffff00897c000`; the segment table grows by one 32-byte entry (every file offset moves +32); the ADT grows from the raw 13956 by 52 bytes (32-byte name + 4-byte length + 16-byte value) to **14008** (`14008 % 8 = 0`; 48 more than NAT-062's patched 13960); `adt_off` 21540816 -> 21557488; payload 21554784 -> 21571504 bytes (+16720); build-time fallback `RAMDisk` = `{0xa4974000, 0x8000}` (ADT `dram-base` `0xa0000000`) |

Everything else (kernel segments, entry, `virt_base`, `phys_base`, `mem_size`) is unchanged. `fixups: 0` in the output means the kernel needs no chained-fixup rewrite (already flat).

## Loader: what it does with the segment and the property

* `shim/e1s-xnu/loader.c` (NAT-052 tree, `artifacts/nat-052/build-003/loader-diag-xnu-ckpt3-usb/source`) copies every segment of the table to `win_base + (vmaddr - virt_base)`, puts the ADT at `kernel_end`
  (after all segments, so after the ramdisk) and `boot_args` after it with `topOfKernelData = ba_pa + 16K` (lines ~696-730): the ramdisk lies below `topOfKernelData`, which the VM never receives.
* `adt_rebase_ramdisk(adt, adt_size, win_base - phys_base)` (`adt_patch.c:205`, called at `loader.c:713`) adds the delta to `RAMDisk`/`RAMDisk1` (length must be exactly 16); with no such property it finds nothing and returns 0
  — **so the ramdisk branch has never executed on the phone**; NAT-020..NAT-063 payloads had no property.
* The NAT-052 tree differs from the upstream NAT-020 tree in this file only by **alignment-safe 64-bit access** (`adt_ld64`/`adt_st64` with two 32-bit accesses; the MMU is off and property values are 4-byte aligned) and the MPIDR mask; the
  RAMDisk logic is the same. `loader.ld`, `adt_patch.h` are identical.
* The loader requires `adt_off`/`adt_size` to be multiples of 8: with the ramdisk `adt_size` is 14008 (ok); the old 13956 was the reason for NAT-062's header fix.
* The kernel then needs `ml_static_ptovirt(phys)` = `phys - gPhysBase + gVirtBase` to land on the copied bytes: `boot_args.physBase = win_base`, `virtBase = p->virt_base`, and the property is rebased by the same `win_base - phys_base`, so
  they agree **by construction**; whether `win_base` is the live window the NAT-063 run used (kttbr0 `0x9e...`) and the final property value are exactly what NAT-065 must check on the real loader code.

## The `!BSD` line, resolved

Observed (NAT-063, kernel log): `bsd_init: calling setconf` `[40.032410]` ... `cpu_start() cpu: 0` `[40.034543]` ... `!BSD` `[40.137418]`; panic text `rd=md0`, `mach_absolute_time: 0x3d3d7b61`.

* **Why `!BSD`**: `IOFindBSDRoot` waits for the `IOBSD` resource (`waitForMatchingServiceWithToken`, `IOService.cpp:6402-6470`: `copyExistingServices` -> `setNotification` -> `IORecursiveLockSleepDeadline`
  (`IOLocks.cpp:278`) -> `lck_mtx_sleep_deadline` (`locks.c:1152`) -> `assert_wait_deadline` + `thread_block`; the deadline is `now + nanoseconds_to_absolutetime(t)` via `clock_absolutetime_interval_to_deadline`, `clock.c:1671`)
  and prints `!BSD` when it returns without a match. With the project patch `t` is **100 ms** for `rd=md*`. Nothing publishes `IOBSD` (no storage, `e1sufs=0`), so `!BSD` is the expected outcome.
* **How long it took**: from `calling setconf` to `!BSD` 105.0 ms in the stamps. The microsecond field of the stamps is **inflated by 1.024**: `absolutetime_to_microtime` (`osfmk/arm/rtclock.c:462-472`) divides the sub-second ticks by
  `rtclock_usec_divisor = divisor / 1000000` (`rtclock.c:141`), an integer division: 25 for the ADT's 25.6 MHz timebase (`mkadt.py:25`, `TIMEBASE = 25600000`) instead of 25.6, so the field runs to 1,024,000 — which is what
  the unnormalised stamps `39.1000184`, `39.1012811` of NAT-063 are. Corrected, 105.0 ms is about **102.5 ms** (2.5 ms for `serviceMatching`, `copyExistingServices`, `setNotification` and other threads' work). The same
  inflation says the kernel runs on the 25.6 MHz constant from the ADT, not on a default of 24 MHz.
* **What it shows**: a thread blocked with a deadline was woken at (just after) that deadline: the timer queue, the virtual-timer interrupt (`CNTV_TVAL_EL0` via `ml_set_decrementer`, `machine_routines.c:2020-2031`; `rtclock` timebase from the ADT) and the scheduler wake
  path worked on this phone. If no timer interrupt were delivered, a blocked BSD thread could not be woken by its deadline (`timer_queue_expire` runs from the timer interrupt; the long-term timer queue is disabled on arm, `timer_call.c:86-91`).
* **What it does not show**: the absolute rate of the kernel's clock against real time. The kernel's stamps cannot be compared with the host's receive times (below), and both the deadline and the stamps use the same timebase, so a wrong
  `CNTFRQ`/timebase would scale both. Check (cheap, host, from the next run's panic text): the next run's log has the stamps of PID 1's `select` sleep (below) — agreement of that interval with 1 s only repeats the same self-consistency; an
  absolute reference needs `CNTFRQ_EL0` as the loader saw it (a note field) — not required for the next step.
* The `loader_return_after=8` thread-call (`xnu/hackios/files/osfmk/arm64/loader_return.c:455-467`, armed at `STARTUP(EARLY_BOOT, RANK_LAST)` about 0.2 s before the panic) did not fire in those 0.2 s — expected for 8 s. Its
  callback runs `redwood_var_save_on_return`, `redwood_adreno_stop`, `redwood_wifi_stop`, `redwood_adsp_stop` (Qualcomm drivers of the donor project) before `loader_return()`: in the code read here all four act only on state that
  those drivers set when they start (`ufs_ready && ufs_write_part >= 0`, `gpu_kept`, `dsp_started`/`whole_runs`, `running`); none of them started in NAT-063 (no log line). **Not run** on this phone; a timed return remains an untested path.
* **A correction to NAT-063**: its README gave "+49.1 s, 1.7 s after the last stop" as a *kernel* interval. Those are **host receive times**: the NAT-041 engine has a 32 KiB ring and no acknowledgement, the host drains it at its own pace, so
  note arrival times are not creation times. The kernel's own stamps put `Darwin Kernel Version` (printed in `kernel_bootstrap`, `osfmk/kern/startup.c:429`, after `arm_init` and so after checkpoint 21) at 39.85 and `!BSD` at 40.14: the kernel ran
  **about 0.3 s** from after the last stop to the panic. The conclusion that the 8 s timer did not cause the return stands (the panic did); the NAT-063 README is amended accordingly.

## Design for NAT-065 (minimal; nothing here is run)

**Image.** Same loader family as NAT-062 (`loader-diag-xnu-run-usb`, stub, DWC3 engine, analyser unchanged). Payload = NAT-062's loader `Image` (307200 bytes, unchanged) + the **NAT-065 payload**:

1. Ramdisk: the pinned `tools/e1s/sweet-init.S` + `mkinit.py` (clang `-target arm64-apple-ios16.0`), **with one small documented patch ("probe")** against the pinned `sweet-init.S` (base SHA-256 recorded, same licence as the file):
   keep `open("/dev/console")`, the banner and the PID digit; if `open` fails `exit(0x52)` (not `hang`); drop the `/dev/md1` mount; then `select(0,0,0,0,{1 s})` and `exit(0x51)`.
   Why: the unmodified init loops forever, so the run would end only through the *untested* timed return or the 57 s deadline reset, and PID 1's console text may not reach the host (the live-console path is the open item of NAT-063).
   The probe ends in a **panic** — the path NAT-063 proved delivers the log — with a verdict inside the panic text: `initproc failed to start -- no exit reason available -- (signal 0, exit status 81 ...)` = PID 1 ran and reached its end; `82` = no console. The `select` sleep gives a user-mode timer measurement
   from the log stamps. Failure modes stay observable: no root -> the mount loop sleeps 5 s per attempt and `loader_return_after=8` is the only return; exec failure -> a panic text of its own.
2. Payload: `mkpayload.py kernel.no-storage e1s.adt OUT --cmdline <NAT-062 cmdline> launchdsuffix=release cs_enforcement_disable=1 --ramdisk <probe init>`, then the NAT-062 steps that still apply (`nat_attempt=NAT062-run`, `loader_return_after=8` already in the string; **no** `adt_size` header patch — 14008 is a multiple of 8; a test must fail if the patch is applied).
   The four zeros `e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0` and `sweethw=0` stay; a host test pins them.
3. Reproducible: two builds, identical hashes; every input hashed (kernel, ADT, loader Image, `mkpayload.py`, `sweet-init.S`, `mkinit.py`, clang version).

**Host tests (no phone), on real build outputs.** (a) the payload differs from the NAT-062 payload only by the new segment, the `RAMDisk` property, `adt_off`/`adt_size`/`kernel_end_va`/`nsegs`/size and the two appended boot-args; (b) the ramdisk is a static arm64 Mach-O
with `LC_UNIXTHREAD` and an ad-hoc signature, expected size, entry inside `__TEXT`; (c) the **real loader code** (`adt_patch.c` compiled for the host plus the layout arithmetic of `loader.c`) on the built payload and a DTB with the live window of NAT-063 (`win_base` from the run archive's
loader fields or the DTB copy): the rebased `RAMDisk` equals `win_base + (rd_va - virt_base)`, is 16 KiB aligned, lies inside `[win_base, ba_pa)`, below `topOfKernelData`, and overlaps no other segment, the ADT or `boot_args`; the 8-byte rule holds; (d) the NAT-062 driver/analyser accept
the new image name and the analyser reports the exit-status line as a result (not as an unknown panic); (e) mutants: ramdisk omitted, property not rebased, delta sign flipped, size not rounded, `adt_size` patch re-applied, boot-arg dropped, `e1sufs=1`.

**Risks and what the next decision file must name.** The kernel will **mount a RAM image and run user-mode code from it** (PID 1 = the probe) — it can issue syscalls (open `/dev/console`, `select`, `exit`) and nothing else; the same RECOVERY-only write, stock restore from the pinned image and Android check
(decision 0019, as 0025/0026); both image hashes (RECOVERY, payload) and the ramdisk's; the changed command line (`+launchdsuffix=release cs_enforcement_disable=1`, DEVELOPMENT kernel); that `rd=md0` already existed and only the ramdisk is new; the 83 s watchdog and the 57 s deadline reset (the kernel
clock counted 40 s at the panic; the loader had enumerated USB about 20 s earlier, so a kernel that waits cannot exceed the reset: a loop in the mount path is cut by `loader_return_after=8`, if that path works, otherwise by the deadline reset with only the stub-time dump); one run, no retry; the untested timed-return code (`redwood_*_stop`) is named as a risk, not as covered.

## Not established

* Whether the ramdisk bytes arrive where `ml_static_ptovirt` points (by construction yes; NAT-065 tests the loader's arithmetic, the run decides).
* Whether `vfs_mountroot` accepts the raw Mach-O through `mockfs` and whether `exec` of the ad-hoc-signed init is allowed on this kernel (upstream says yes for its build; this payload has the strings `mockfs`, `launchdsuffix` and `/sbin/launchd` but nothing was executed).
* Whether PID 1's console text reaches `loader_log` live (NAT-061 says `kmoutput` calls `loader_log_putc`; the empty first dump of NAT-063 is unexplained) — the probe does not depend on it.
* The absolute clock rate; whether the GIC delivers more than the timer PPI; the `pe_arm_map_interrupt_controller` / `pe_arm_init_debug` warnings; what the timed return's quiesce calls do on this SoC.

## Files

`compare_payloads.py` (the host check; run as `python3 -I docs/procedures/nat-064/compare_payloads.py --out artifacts/nat-064/compare --json OUT.json`), `compare-result.json` (its output), `evidence.json`.
The rebuilt payloads, the stage-0 init and the object stay in the gitignored `artifacts/nat-064/` (hashes in `evidence.json`).
