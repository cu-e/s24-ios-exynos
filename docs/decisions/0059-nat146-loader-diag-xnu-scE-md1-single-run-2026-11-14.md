# Decision 0059: one NAT-146 run of loader-diag-xnu-scE-md1 (all ten CPUs through PSCI CPU_ON; frame rate)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052, with the owner's
separate answer below.

## Owner consent

Decision 0052 covers prepared single native experiments with display, touch, memory, interrupts, clocks/reset and watchdog. It does
not name PSCI `CPU_ON`/`CPU_OFF`, which are secure firmware calls that power CPU cores on and off. So the owner was asked separately on
2026-11-14 about this exact run. The question named: the scE image, PSCI CPU_ON for cores 1–9, CPU_OFF before the return, RECOVERY
only with readback, the 595 s limit, the standard stop and the stock restore. It also stated that a GPU (Xclipse PMU + SMC/HVC)
power-on is a separate plan and question. The owner answered: "Да, запускай сейчас".

Earlier direction (2026-11-14): "теперь мы переходим к быстрой отрисовке гпу что бы фпс было много".

## New verifiable reason

NAT-144 passed. Touch opens apps, and the owner reports «Открылись приложения, Свайп вверх работал». Its frames reached the panel
at about 16–17 per second during continuous activity (analyze146 on NAT-144's text: best steady window 21.72/s, half of the intervals
under 57 ms), all on one Cortex-A520 because of `cpus=1`. scE is the same system with all ten cores, so it measures how much of the
frame time is CPU contention on one little core.

## Image

Image loader-diag-xnu-scE-md1, built by NAT-145 (commit 8b0d627):
- RECOVERY artifacts/nat-145/package-001/loader-diag-xnu-scE-md1/recovery.img,
  SHA-256 ffa91748d09482c3f34de61ff0c6e2538001624cf963652157cbcb8cf71ec80f (100663296 bytes);
- Image.payload SHA-256 4384cf08fc876a03f6ef5ff0b4224a7e4942fe7d8437819678e9171a4a054bb8 (26206640 bytes at offset 2048);
- loader Image c65dc2776032df714747bd554d384e020ad9f460bfbc4d2e29e9d3a9fa6c558b; payload ADT 0c109c99…9bb6;
- kernel 6aa8b6eb27009e16d0e7a618c5e4becca6f36561ac5b632912bdda13078fd100, unchanged from NAT-144;
- cmdline (239 bytes) is scD's without `cpus=1`, with `nat_attempt=NAT145-scE`;
- written only to RECOVERY /dev/block/sda18 with a full-hash readback before the single reboot
  (docs/procedures/nat-145/session_nat146.py, 59a8002f…b24);
- stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Changes against scD (NAT-144)

- The ADT `/cpus` has `cpu0`–`cpu9` with the pinned Samsung DT MPIDRs (0x000–0x900), and the cmdline drops `cpus=1`.
- XNU's GenericARMPE registers ten CPUs. psci_smp.c sends `CPU_ON` (SMC 0xC4000003) for the big cores at once and for the three
  small ones 28 s later. A refusal, an entry fault or a core that never joins is logged, and the system continues on the cores it has.
- Before the timed return, `psci_smp_stop_others()` sends `CPU_OFF` to every other core and waits for `AFFINITY_INFO` OFF.

Touch, rails (LDO18 0x3d := 0xd8, LDO9 0x34 := 0xf0, as NAT-124/140/142/144), display, watchdog feed, root and window are NAT-144's.

## Risk

- PSCI CPU_ON/CPU_OFF are the standard calls the retail firmware serves to Android at every boot and CPU hotplug. They act on the
  cores' own power domains and are volatile. Nothing persists across the reboot.
- If a core faults or hangs the system, two things end the run: the fed watchdog stops being fed and resets the phone, or the loader
  deadline expires. The phone then boots as before. NAT-115 to NAT-144 showed both paths.
- No partition other than RECOVERY is written. iOS runs from RAM (`e1sufs=0`).

## Time limit, stop mechanism, restore

The limits are NAT-144's:
- delivery cap 225 s;
- loader receive cap 240 s;
- kernel timed return 270 s with the fed watchdog (fail-safe 63 s);
- loader deadline 595 s, then Download Mode (about +620 s);
- watcher and collector 720 s.

Restore:
1. Run nat-012 restore_stock.py with the venv python.
2. Run check_android.py and nat-013 assess. They must show boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, the stock RECOVERY hash
   and the user-data directories.
3. Run `task done`/`update` BEFORE the native permission is closed.

One attempt only, with no retry without a new verifiable reason.

## Physical action asked of the owner

Timing is counted from the reboot. With more cores, the home screen may come earlier than +4 min 15 s; the end is about +6 min 20 s.
From the home screen onward, keep the screen busy:
- scroll the home-screen pages left and right;
- open an app such as Settings and scroll its list up and down;
- swipe up to go home.

Afterwards, tell how smooth it looked compared with NAT-144.

## Interpretation registered before the run

`docs/procedures/nat-145/analyze146.py` reports every analyze144 verdict, plus smp, cpus and fps:
- **C2-all-ten:** XNU ran all ten cores.
- **C1-some:** a subset ran; the failed cores and the firmware answers are listed.
- **C0-one:** no secondary ran.

`fps_best_window` and `fps_median_interval_ms` are compared with NAT-144's 21.72/s and 57 ms. This is the kernel's count of frames
reaching panel memory, not a camera measurement. The owner's report is recorded separately.
