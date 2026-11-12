# NAT-086: native run of `loader-diag-xnu-ep-md1` (decision 0033)

Result (native-device, one run, 2026-11-12, RECOVERY only, restored from the pinned stock): **chain row 1b, stage row S4**, not S1. The task is not completed (its acceptance says a non-S1 row is recorded as the finding).

| question | observed on the S24 |
|---|---|
| does `/chosen/ephemeral-storage = 1` make keybagd skip? | **yes**: `****** DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT ****` for `keybag` and again for `usermanagerd` |
| does Apple's launchd get past `keybag`? | **yes**: 11 more boot tasks (usermanagerd, dirs_cleaner, xpcroleaccountd, init_featureflags, auearlyboot, tzinit, finish-restore, finish-demo-restore, sysstatuscheck, prng_seedctl, launchd_cache_loader) |
| does it stay alive and run `com.nat085.ps` twice? | **no**: `launchd_cache_loader` aborted (`Failed to create SecStaticCodeRef [-67068\|errSecCSStaticCodeNotFound]`), XNU panicked by design (a critical boot task exited); the job never ran |

Sanitised launchd console text (only user-space text, no kernel text): `launchd-console.txt`. Numbers: `numbers.json`. Evidence: `evidence.json` (outcome `fail` = stage S1 not reached; not a measurement failure).

## Why `launchd_cache_loader` failed (host review, not yet observed on the phone)

1. `/System/Library/xpc/launchd.plist` is absent from the delivered root because the donor recipe deletes it (`artifacts/nat-083/recipe/userland/build.sh`: "launchd must load our choice of jobs, not all 500 that Darwin has"). The log line `Unable to open /System/Library/xpc/launchd.plist [2:No such file or directory]` is therefore expected, and the loader (which verifies exactly that file and `launchd.plist.sig`) cannot succeed.
2. launchd's per-boot-task predicate (disassembly of the pinned `sbin/launchd`, function at `0x10003b8c8`): `PerformAlways` runs; after a userspace reboot only `PerformAfterUserspaceReboot`; if flag B is set and the task has no `PerformInRestore` it is skipped; otherwise it runs. Flag B (together with flag A, which also makes launchd read `disabled.plist`) is set at `0x100041440` when `strstr(kern.bootargs, "rd=md0")` (import `_strstr`, resolved through the chained fixups) or one of the strings `Restore`, `Ramdisk`, `RamDisk` matches. This run had `rd=md1`, so every boot task ran. The donor recipe says the same in `userland/src/init.c`: "The boot-args stay those of a RAM disk (rd=md0), which is what launchd reads to leave out the boot tasks of a real device."
3. XNU's boot-arg parser compares whole keys (`pexpert/gen/bootargs.c`, `PE_parse_boot_argn_internal`), so a token such as `xrd=md0` is invisible to the kernel's `rd` but contains the substring `rd=md0` for launchd.

Next: NAT-087 (host) prepares one image that adds the token `xrd=md0` and nothing else; its native run is a separate task under its own decision.

## Disclosures

* The first `assess` call used wrong arguments (argparse exit 2, nothing executed) and was repeated correctly.
* The returned log has a 5,321-byte gap between the libignition configuration lines and the FIPS lines (head 8192 + tail 32768 bytes of the ring); absence inside it is "not established".
