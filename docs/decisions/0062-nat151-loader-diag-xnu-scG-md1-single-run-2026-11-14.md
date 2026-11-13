# Decision 0062: one NAT-151 run of loader-diag-xnu-scG-md1 (early marks of the PSCI-started cores)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 (the owner's standing authorization of 2026-11-14) names bounded CPU experiments, PSCI `CPU_ON` of secondary cores
included, so this run needs no separate owner question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason (NAT-149 is not repeated unchanged)

NAT-149: the firmware accepted `CPU_ON` for cores 1–9, but none reached `arm_init_cpu()`, and nothing tells where they stopped.
scG adds per-core early marks between the core's first instruction and the MMU switch, plus PSCI `AFFINITY_INFO` after the wait.
NAT-150 checked the marks on the unicorn model of the built image (`docs/procedures/nat-150/README.md`,
`artifacts/nat-150/model-secondary.json`): a matching core runs NAT-143's instructions plus the mark blocks only, and the boot path
gains two `cbz`. scG also cuts the per-core wait from 5 s to 1 s, so the home screen comes in time for a frame-rate window, and it
never pairs the boot CPU under a core that may not run.

## Image

loader-diag-xnu-scG-md1 (NAT-150):
- RECOVERY `artifacts/nat-150/package-001/loader-diag-xnu-scG-md1/recovery.img`,
  SHA-256 a9f0eed0175fc9f4aea26dd67a50b6f2ca5b62494cf70414250f3700d8dd6de0 (100663296 bytes);
- payload a68fd474af6775d5c66c525edf66b0baf006ff9e169795f0c67bf1e70cd2c213 (26206896 bytes at 2048);
- loader Image de0e0d87b2c7b47828257369d80ddb448be42d946b654eb4060fbde5b393afc0;
- kernel c84e72397f3bfad01e5fd305d15bc2340dc96629fe6517c81f00627aa2ee8901.

Changes against scF: three kernel objects (start.o, psci_smp.o, machine_routines.o) and the attempt tag. It is written only to
RECOVERY /dev/block/sda18 with a full-hash readback before the single reboot (`docs/procedures/nat-150/session_nat151.py`,
7a8b7331…1ec4). Stock restore SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-150/analyze150.py`:
- `smp`: C2-all-ten / C1-some / C0-one, from the running count;
- per core that has not joined, `early_where` E0–E6 and the affinity state (0 on, 1 off, 2 on pending);
- the frame windows, against NAT-144's 21.72/s and 57 ms.

## Risk, time limit, stop mechanism, restore

Same as decisions 0059 and 0060:
- delivery cap 225 s, receive cap 240 s;
- timed return 270 s with the fed watchdog;
- loader deadline 595 s → Download Mode;
- watcher and collector 720 s.

A started core writes only its own 128 B of marks beyond NAT-149's behaviour.

If the kernel fails before it takes over the watchdog (about jump + 13 s), the phone may loop through SEC_UPLOAD (NAT-146). Then:
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written, and iOS runs from RAM.

Restore:
1. nat-012 `restore_stock.py` with the venv python;
2. `check_android.py` and nat-013 assess;
3. `task done` (on pass) or `task update` BEFORE the permission is closed.

One attempt, with no retry without a new verifiable reason.

## Physical action asked of the owner

From the home screen (about +4:00 after the reboot) until about +6:20:
- scroll the home-screen pages;
- open Settings and scroll it;
- swipe up to go home.

Afterwards, tell how smooth it was.
