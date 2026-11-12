# NAT-088: native run of `loader-diag-xnu-rm-md1` (decision 0034)

One run, 2026-11-12, RECOVERY only, restored from the pinned stock (NAT-013), Android and data checked. Evidence class: **native-device**.

**Pre-registered result (analyser `analyze_nat087.py`, unchanged): chain row 9 / restore row R9, not evaluated. Outcome `inconclusive`; the task is not completed.**
The kernel's returned text is in the collector's second boot (the loader restarted after the kernel's own return). NAT-081's replay rule refused that boot because the ring lost
3,338 bytes (two producer-reported drops), and the first boot ends at checkpoint 27 with no return.

**Hand reading beyond the ladder** (second boot, kernel-log dump `why=2`, head 8192 + gap 16705 + tail 32768; labelled as post-hoc, see `evidence.json`):

* launchd skipped 20 boot tasks and ran only `commit-boot-mode`, `restore-datapartition` and `init-with-data-volume`: exactly the three the host-side Boot-dictionary reading predicted
  (decision 0034). `launchd_cache_loader`, `keybag` and `tzinit` were skipped; "Early boot complete. Continuing system boot." at kernel time 193.752 s.
* launchd stayed alive and respawned the job `com.nat085.ps` every 10 s up to the last returned line (kernel time 244.25 s); three complete `ps -A` lists and the xpcproxy spawns of pids 12, 13 and 14 are in the text.
* No panic and no reboot request; the kernel handed control back by itself at `loader_return_after=60` (first return with a live PID 1).
* Not seen: the line `Restore environment starting.` (it is not in the returned text; it may lie in the 16,705-byte gap or the 3,338 lost bytes).

Two host-side findings for the next analyser: (1) the replay reader must tolerate ring-overrun drops and (2) restore-mode launchd logs its boot tasks in the kernel `[System Event] ... [Event: X] Skipping boot-task`
form, which the NAT-087 ladder does not read.

Files: `launchd-console.txt` (launchd-only lines, sanitized, ring order, not chronological), `numbers.json`, `evidence.json`, `task.json`. The full dump texts stay under `artifacts/nat-087/run-001/` (they contain the host user name).
