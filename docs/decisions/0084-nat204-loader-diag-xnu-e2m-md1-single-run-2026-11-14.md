# Decision 0084: one NAT-204 run of loader-diag-xnu-e2m-md1 (mediaserverd with the donor's media library)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052, decision 0061 and
decision 0079. Decision 0061 covers new images within the bounded CPU experiments, including PSCI `CPU_ON` runs, without a separate
question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-202 recorded mediaserverd's fault: 46 times at one site, `pc 0`, a CoreImage OpenGL ES call through an empty dispatch table
under CMCapture's portrait-filter prewarm. The donor's `libhakios.media.dylib` exists for exactly this fault and empties that
method. NAT-203 adds it to the md0 root's inject list for mediaserverd. Whether mediaserverd then stays up, and whether SpringBoard's
`routingContextUID` abort under SMP goes with it, has never been run.

## What changes against e2s (NAT-202)

- **Changed.** The md0 small root only (`artifacts/nat-203/pid1-sc2-hbm/root.apfs`, SHA-256
  9a1eaab6f0a3fa278dc99ff6656a38658de8b212391eecf8dca5ba7d41c4d43d):
  - one added file, `lib/libhakios.media.dylib`, the pinned donor prebuilt;
  - one added line in `etc/inject.conf`.
  - It is user-space code inside one Apple daemon. It replaces Objective-C methods in that process only, at their 20F66
    addresses or not at all. It opens `/dev/hakios-torch`, which this kernel does not create, and touches no device.
- **Unchanged.** Everything else:
  - the NAT-201 kernel, byte for byte, with the user-exception trace on;
  - the loader;
  - the NAT-197 EL2→EL1 drop and the ten CPUs;
  - the delivered big root;
  - the command line, except the tag `nat_attempt=NAT203-e2m` (254 bytes).
- **Not touched.** Nothing on the phone outside RAM. No PMIC, clock or GPU change beyond scV's (cpu0 FREQ_REQ 1959000 kHz).

## Image

loader-diag-xnu-e2m-md1 (NAT-203):
- RECOVERY `artifacts/nat-203/package-001/loader-diag-xnu-e2m-md1/recovery.img`, SHA-256
  6d27f0de85bcba195c7b6546315b0cbe4f5f3b9577020666cb694c20c6894c96 (100663296 bytes);
- payload 1f71263d976311e204e034d43b49fbc17acea5f889290e23923ae49b026d92d3 (26208400 bytes at 2048);
- kernel no-storage dd5cbc7d9c6e58935b6bd1f3e0ad96632ad43bd174040c14d1c6b09e9861c07f.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot. The session driver is
`docs/procedures/nat-203/session_nat204.py`, SHA-256 64d4afefc6183899feb4b569b28671f674931b0dc2c94459565c31b215178f73.

Stock restore SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-203/media204.py` on the kernel text, first match:

| verdict | condition |
|---|---|
| M-none | no mediaserverd line: inconclusive |
| M-same | a mediaserverd trap at NAT-202's site: the library did not take effect |
| M-other | a mediaserverd trap elsewhere, or an exit due to a signal |
| M-fixed | mediaserverd lines, no trap and no exit due to a signal |

Beside it, from `reason200`:
- **A-gone:** no SpringBoard abort line.
- **A-same:** the same `routingContextUID` reason.
- **A-other:** another reason.

Also reported: `smp198` and the scV measures.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0081:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risk.** The e2s configuration ran to its timed return and Download Mode (NAT-202). The change is user-space code in one daemon;
the worst case is that daemon faulting, which launchd handles as it has in every run since NAT-118.

**If the phone loops through SEC_UPLOAD (NAT-146):**
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s);
3. the owner holds Volume Up + Volume Down until the blue screen, then presses Volume Up for Download Mode;
4. the stock restore follows.

**Restore.** No partition other than RECOVERY is written. Restore with nat-012 `restore_stock.py` under the venv python, then run
`check_android.py` and the nat-013 assess. `task done` or `task update` comes BEFORE the permission is closed.

One attempt, and no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
