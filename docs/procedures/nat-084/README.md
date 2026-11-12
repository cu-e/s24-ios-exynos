# NAT-084: first Apple user space on the S24 (native-device, decision 0032)

One native run of `loader-diag-xnu-rt-md1` (decision `docs/decisions/0032-nat083-loader-diag-xnu-rt-md1-single-run-2026-11-12.md`, committed in 50785ef before any device access), RECOVERY slot only, restored from the pinned stock afterwards (NAT-013 with the pyusb venv python), Android checked afterwards. Judged by `docs/procedures/nat-083/analyze_nat083.py`, unchanged (sha256 f20bcf32...857a9).

## What the analyser says (pre-registered ladder)

Chain PASS, ladder **row 1, variant a**, pass = true: the donor `apfs` VFS mounted the delivered 2,475,720,704-byte image from RAM (`rd=md1`, volume "System", 45,044 files, 16,545 directories), the donor `/sbin/launchd` (stage0) mounted the small image from md0 on `/redwood` and exec'd `/redwood/sbin/init` (35 checks, 0 failed), `etc/rc` ran Apple's own `/bin/df`, `/sbin/mount`, `/bin/ps -A`, `/usr/bin/vm_stat` (all clean, outputs in `numbers.json`), then `exec /sbin/launchd.darwin` was reached with no exec error and no panic or PID 1 exit text. Row 1a, as registered, means exactly that and no more.

## What the log shows beyond the ladder (read by hand after the analyser; not a registered row)

Apple's launchd ran. Its own 7,885 bytes of console text are in `launchd-console.txt` (the text between `Darwin Ignition Sequence` and `REBOOTING INTO RECOVERY MODE.`; nothing else from the kernel log is committed because the kernel banner carries the host user name). In order:

1. `libignition` (Darwin Ignition Sequence 1.0.0) printed its configuration (`hardware target: d22ap`, `rd: md1`, `stage count: 0x7`), ran stage `hello`, then stage `preboot` failed: `failed to lookup preboot: 25` (errno 25 = ENOTTY) -> `ignition boot failed: 25` -> `ignite() returned 25`. launchd did **not** stop there.
2. `Darwin Bootstrapper Version 7.0.0 ... libxpc_executables-2462.120.4` started (this is the real `com.apple.xpc.launchd`), printed our boot-args, `entering ondemand mode`, and ran its boot tasks in order: `fsck` (skipped: not main OS), `mount-phase-1`, `data-protection` ("No SEP present on this device"), `finish-obliteration`, `detect-installed-roots`, `commit-boot-mode`, `restore-datapartition` (optional, absent), `mount-phase-2`, `init-with-data-volume`, `MSUEarlyBootTask`, `fips`.
3. `fips` ran Apple's **corecrypto FIPS POST from the dylib: 18 self-tests PASSED (238 ms)**. That is real dyld-loaded Apple code running AArch64 crypto code paths on this CPU.
4. The next boot task, `keybag` (`MKB_INIT`), failed fatally: `Could not open /private/var/keybags/systembag.kb: No such file or directory` (also `.writing`), `Unable to load keybag with No Crypto: -7`, `FATAL KEYBAG ERROR: kb_load`, `REBOOTING INTO RECOVERY MODE`. The kernel then logged `nvram ... write auto-boot`, unmounted `/private/var` and `/redwood`, and `MACH Reboot` / `PMRD: Restart total 31 ms` (last line of the log, kernel time [203.345]; launchd's own wall-clock stamps run from 00:03:22.388 to 00:03:23.198 on its 1970-based clock, so it ran for about one second before the keybag failure).

So the analyser's "no PID 1 exit" is literally true (PID 1 did not exit; a boot-task child asked for a reboot) but understates the run: the run **ended by the userland-requested reboot at kernel time 203.3 s**, not by the `loader_return_after=60` limit. The first USB return was Download Mode at dt 379.91 s (class `cap-reset`, consistent with the loader's 360 s deadline); whether the kernel's own reboot path ever reset the SoC in the time between is not established (the log ends at the restart notification).

## Deviations and disclosures

* The analyser was first run before the collector had finished (no `archive/manifest.json`), which gave chain PARTIAL and row 9. That was an operator error (timing), not a device finding. The outputs are kept as `analysis-early.*` / `kernel-log-early.txt`; the same unchanged analyser was rerun on the complete archive.
* The driver's own `--restore` option could not be used (needs adb; the phone was in Download Mode): the NAT-013 restore tool was used instead (first try, readback and `assess` pass).
* A stray empty file `--help` was created by running `check_android.py --help` (that script has no help; argv[1] is its output file). It was removed; no device access was involved.
* The whole-image SHA-256 of the delivered root is still unverified (NAT-078 open). This run did not need it.

## Not established

That launchd can run its services (the job list is empty by design); that any XPC service, `backboardd` or `SpringBoard` can start; anything about display, input or GPU; that the reboot path of the project's XNU resets the SoC.
