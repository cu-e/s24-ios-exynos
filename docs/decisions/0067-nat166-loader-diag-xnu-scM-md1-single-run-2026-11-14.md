# Decision 0067: one NAT-166 run of loader-diag-xnu-scM-md1 (per-core load lines)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded CPU and display experiments, new kernels and images included, without a separate question. This file is
the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-164 (pass) showed that CoreAnimation hands over a frame every ~106 ms on the idle home screen, and that the driver needs 26 ms of
that. NAT-161's CPU share was withdrawn: its `ps` snapshots carry no usable timestamps. Whether cpu0 is saturated decides the next
lever:
- if it is saturated, CPU capacity (SMP or GPU);
- if not, the content's own cadence, and the need for a capacity test under interaction.

scM (NAT-165) is scJ with:
- boot-arg `cpuload=1000`;
- a kernel whose E1S `redwood_input_init()` also calls `redwood_cpufreq_init()`. Without `cpufreq`/`ddr` boot-args that function only
  starts the upstream load thread (`tl: u` lines, kernel timestamps). The source was checked: no clock, voltage or DDR change.

This is not a repeat: a new measurement after passing runs.

## Image

loader-diag-xnu-scM-md1 (NAT-165):
- RECOVERY `artifacts/nat-165/package-001/loader-diag-xnu-scM-md1/recovery.img`, SHA-256 f0e1cfd923c89e8f202427f6815b7adfc1adc94bdd66dc9022a61dd9c6049257 (100663296 bytes);
- payload 1450397b04b9a433f1c17b00dac7ee4687bf388f87304aa7ab1ebedbb6b7f8aa (26206800 bytes at 2048);
- loader Image 37508d4acb7aed29b120fa9e9f49dace242e3b6999d960feefd25f82309dd88c;
- kernel no-storage f13b7c346cbb0c74f8485787f1b1076fc734f44e1c9e8df17d72041b4245d92f: NAT-152's objects, only `bsd/redwood_input.o` changed.

The loader's checkpoint check gives rc 0, with the 13 constants on the NAT-143 symbols, and relocscan finds 0 relocations that are
not allowed. The command line is 255 bytes.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-165/session_nat166.py`, 7e2300ed…8e1c). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-165/load166.py`: cpu0's busy share (median of the `tl: u` samples) over `frames159`'s steady windows.
- **L2:** ≥ 90%, saturated;
- **L1:** 60–90%;
- **L0:** < 60%, headroom.
- No `tl: u` line at all means the hook did not run, and the run is **inconclusive**.

Also reported:
- `frames159` against NAT-159 (9.26/s, 26.0 ms), as the cost of the 1 s load thread;
- the display verdicts;
- the other cores' readings, which are not graded: they never run.

## Risk, time limit, stop mechanism, restore

Same as decisions 0063–0066:
- delivery cap 225 s, receive cap 240 s;
- timed return 270 s with the fed watchdog;
- loader deadline 595 s → Download Mode;
- watcher and collector 720 s.

The kernel change is one call in bsd init. It starts one kernel thread that reads idle counters and logs once a second.

If the kernel fails before it takes over the watchdog, the phone may loop through SEC_UPLOAD (NAT-146). Then:
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written, and iOS runs from RAM.

Restore:
1. nat-012 `restore_stock.py` with the venv python;
2. `check_android.py` and nat-013 assess;
3. `task done` or `task update` BEFORE the permission is closed.

One attempt, with no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen (comparability with NAT-153/159/161/164).
