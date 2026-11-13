# Decision 0063: one NAT-153 run of loader-diag-xnu-scH-md1 (early marks of the PSCI-started cores, loader addresses in place)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 (the owner's standing authorization of 2026-11-14) names bounded CPU experiments, PSCI `CPU_ON` of secondary cores
included, so this run needs no separate owner question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason (NAT-151 is not repeated unchanged)

NAT-151 (decision 0062) ran scG. The loader stopped before the kernel: scG's start.patch moved five checkpoint sites,
`loader_jump` and `_set_mmu_ttb`, which the loader holds as compile-time addresses. The phone came to Download Mode by itself at
the 595 s deadline and was restored.

scH (NAT-152) carries the same diagnostics with every one of those addresses unchanged. The new verifiable reason is the loader's
own check on this payload:
- `nat036_check()` from the image's loader source, run by `docs/procedures/nat-150/check_loader_sites.py` on the window copied from
  the payload: scH rc 0; scG rc 2 `NAT031_SITE_BAD` site 1, the NAT-151 failure;
- all 13 loader constants name the same symbol+offset as in the NAT-143 kernel that ran in NAT-149.

The unicorn model of the built kernel (`artifacts/nat-152/model-secondary.json`) gives:
- a started core runs NAT-143's instructions plus 5 mark blocks and their branches;
- the boot processor's instructions are identical to NAT-143's (0 inserted).

`small_cores=0` (redwood.patch, `ml_parse_cpu_topology()`) means no core is paired as a slower core's secondary, so the boot CPU is
not paired under a core that never runs. This replaces NAT-150's machine_routines change.

## Image

loader-diag-xnu-scH-md1 (NAT-152):
- RECOVERY `artifacts/nat-152/package-001/loader-diag-xnu-scH-md1/recovery.img`,
  SHA-256 e90fe5b00269b434b8707f565d3d4365d9ba03c72a94e9a754c86c4a16d39164 (100663296 bytes);
- payload 2a35d84282ad5570255a31c4768e84740d3bead3de1f56c5c8c3646fa70e3ca2 (26206800 bytes at 2048);
- loader Image 48841f6ca11f8dba715ef3db3d6370c4523e9d55cf4cce4129505413f11f08aa;
- kernel 8d62baff503ddfe75ebf388fa13e9e8bf47cf46e942b54887f5c9221b44d14b4.

Changes against scF (NAT-149's image):
- two kernel objects, start.o and psci_smp.o;
- the attempt tag;
- the boot-arg `small_cores=0`.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-152/session_nat153.py`, f97f9d4b…5e0a). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-150/analyze150.py`:
- **loader:** the loader passes its checkpoint checks and jumps to the kernel, so a kernel ring arrives. If no ring arrives, the
  loader's CK records say where it stopped.
- **`smp`:** C2-all-ten / C1-some / C0-one, from the running count.
- **cores that have not joined:** `early_where` E0–E6 per core and the affinity state (0 on, 1 off, 2 on pending). E0 = the core
  never ran the kernel's reset vector.
- **frame windows:** against NAT-144's 21.72/s and 57 ms.

## Risk, time limit, stop mechanism, restore

Same as decisions 0059, 0060 and 0062:
- delivery cap 225 s, receive cap 240 s;
- timed return 270 s with the fed watchdog;
- loader deadline 595 s → Download Mode (also seen from the loader's exception loop in NAT-151);
- watcher and collector 720 s.

Beyond NAT-149's behaviour, a started core writes only its own 128 B of marks.

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
