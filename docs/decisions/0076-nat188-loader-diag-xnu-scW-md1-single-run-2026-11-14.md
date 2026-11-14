# Decision 0076: one NAT-188 run of loader-diag-xnu-scW-md1 (Reduce Transparency and Reduce Motion in the delivered root)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers new images, roots included, within the bounded experiments without a separate question. This file is the per-image
record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-186 showed the only core full during the swipes, with backboardd taking 76 % at a median 67.95 ms of CPU per frame (up to about
190 ms in the Today view). Without a GPU, iOS's blur materials are rendered on the A520. iOS's Reduce Transparency and Reduce Motion
remove those effects.

This is a new change, never run before: the preferences sit in the delivered userland root, and nothing of the kernel or the hardware
access differs from NAT-186.

## What changes against NAT-186's image

- **Changed.** Only the small md0 root (`artifacts/nat-187/pid1-sc2-hb-ax/root.apfs`, 3f91915709307fe2826ecbb1dee86c01b875e91ea060796c645051ee8a32cd49):
  NAT-110's plus `com.apple.Accessibility.plist` (two booleans) and its `etc/var.skel` line.
- **Unchanged.** The kernel (d7e7fee1…, NAT-185) and every driver.
- **Command line.** NAT-185's with the tag `nat_attempt=NAT187-scW`.
- **Not touched.** Everything on the phone outside RAM, as before.

## Image

loader-diag-xnu-scW-md1 (NAT-187):
- RECOVERY `artifacts/nat-187/package-001/loader-diag-xnu-scW-md1/recovery.img`, SHA-256
  fb65027cd6ddb7813b971d1918964027a5aa2c5a79fef4282859a83bad4f060c (100663296 bytes);
- payload f41eb9f2274a28862103d4eb586f0fc52c4bf38c1743c8356a54500c402102ca (26208032 bytes at 2048);
- loader Image 6669af39d1956f0041ef8a42954c2e9395dcc3c03806902ac5d7100c8d343658;
- kernel no-storage d7e7fee154104aaf9c59a4d2145c3901763259296ebd85cb373c388a4667c8b3.

Loader sites check rc 0; relocscan clean; command line 254 bytes.

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-187/session_nat188.py`, 88e8b06d8fa999ce0ce5f67f1ef2dab3ae764ebca4e50f771dcedeeb94daadef). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-187/bbd188.py` takes the median of backboardd's CPU per frame over the swipe spans (220–375 s). The baseline is
NAT-186's 67.95 ms.

| verdict | condition |
|---|---|
| B-none | no span with frames: inconclusive |
| B2 | ≤ 33.98 ms |
| B1 | ≤ 54.36 ms |
| B0 | otherwise |

Reported beside it:
- backboardd's share and the 60-Hz share of the frame intervals (NAT-186: 0.594);
- top186 (U verdict), K, swipe175, dpp177, cpuclk173, touch170 and the display verdicts;
- the last panel frame, where plain materials would show the setting took effect;
- whether the timed return was reached.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0072:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

Specific risk: none beyond NAT-186. The change is two booleans in a userland preference file. A malformed plist would at worst be
ignored by cfprefsd: the tests decode it, and it is the same binary-plist form as the eight NAT-108 preference files. If the kernel
stops, the fed watchdog expires and the loader deadline or the SEC_UPLOAD procedure applies.

If the phone loops through SEC_UPLOAD (NAT-146):
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down until the blue screen and presses
   Volume Up for Download Mode;
3. the stock restore follows.

No partition other than RECOVERY is written. Restore: nat-012 `restore_stock.py` with the venv python, then `check_android.py` and
nat-013 assess. `task done` or `task update` comes BEFORE the permission is closed. One attempt, and no retry without a new verifiable
reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
