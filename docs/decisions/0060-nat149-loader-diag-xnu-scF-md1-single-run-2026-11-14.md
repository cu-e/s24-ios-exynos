# Decision 0060: one NAT-149 run of loader-diag-xnu-scF-md1 (ten CPUs, one boot CPU in /cpus)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decisions 0019, 0044 and 0052, with the owner's separate answer
below (PSCI `CPU_ON`/`CPU_OFF` are not named in 0052, as in decision 0059).

## Owner consent

On 2026-11-14 the owner was told:
- NAT-146 failed, and its cause was found and checked on the kernel model;
- scF changes exactly nine words (running → waiting);
- the procedure is decision 0059's (PSCI for cores 1–9, RECOVERY only with readback, 595 s, stock restore and Android check);
- an early failure would loop through SEC_UPLOAD again and need their buttons.

The owner answered: "Да, запускай сейчас".

## New verifiable reason (NAT-146 is not repeated unchanged)

NAT-146 stopped inside `ml_parse_cpu_topology()`. NAT-148 ran the kernel's own code on the NAT-035 model:
- the scE ADT reaches `_Assert(topology_info.boot_cpu == NULL)`;
- the scF ADT parses 10 CPUs with boot CPU 0 and runs the model chain to checkpoint 14 (`docs/procedures/nat-148/README.md`,
  `artifacts/nat-148/model-topology.json`).

## Image

loader-diag-xnu-scF-md1 (NAT-148, commit 9ab0122):
- RECOVERY `artifacts/nat-148/package-001/loader-diag-xnu-scF-md1/recovery.img`,
  SHA-256 56e9d3acfac4d0438c93c2eefb5f7da7b50ee94e4454bf613eb7c36b26386d3d (100663296 bytes);
- payload 0788e7d812d604c6002e9096ef6b4f88d05a8b5da2e3e25ee7f73d92d3cb682a (26206640 bytes at 2048);
- loader Image f1bb4ba9c8fe3475574f96bde46eb308cf32aa69b84ff120d001e10cafe1cfcf;
- kernel 6aa8b6eb…d078.

The payload differs from scE's only in the attempt tag and the nine `/cpus` state values. It is written only to RECOVERY
/dev/block/sda18 with a full-hash readback before the single reboot (`docs/procedures/nat-148/session_nat149.py`, 80c97917…34cd).
Stock restore SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Risk, time limit, stop mechanism, restore

Same as decision 0059: delivery cap 225 s, receive cap 240 s, timed return 270 s with the fed watchdog, loader deadline 595 s
→ Download Mode, watcher and collector 720 s.

Known additional limit (NAT-146): a failure before the kernel takes over the watchdog (about jump + 13 s) resets the phone into
SEC_UPLOAD, and upload mode's restart boots RECOVERY again. If that happens:
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

From the home screen (about +3:30 to +4:15 after the reboot) until about +6:20:
- scroll the home-screen pages;
- open Settings and scroll it;
- swipe up to go home.

Afterwards, tell how smooth it was.

## Interpretation registered before the run

`docs/procedures/nat-145/analyze146.py`, unchanged:
- **C2-all-ten:** XNU ran all ten cores.
- **C1-some:** some cores ran; failed cores and firmware answers are listed.
- **C0-one:** no secondary ran.

`fps_best_window` and `fps_median_interval_ms` are compared with NAT-144's 21.72/s and 57 ms; this is the kernel's frame count,
not a camera measurement. If the kernel ring is missing, the result comes from the loader's CK records (as in NAT-146), with no
verdict invented.
