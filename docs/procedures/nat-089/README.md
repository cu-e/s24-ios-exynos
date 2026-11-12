# NAT-089: reading a restore-mode run without refusing it, and the Stage A job set

Evidence class: **host-test**. Nothing here ran on a phone.

## Why

NAT-088 (native, outcome inconclusive) showed on the S24 that Apple's launchd in restore mode skips 20 of 23 boot tasks and respawns a job, but its pre-registered ladder read R9:
the returned text was in a second collector boot with two ring-overrun drops, so NAT-081's replay rule refused it, and the launchd boot-task lines are in the kernel
`[System Event]` form, which the NAT-087 analyser does not read. This task fixes both on the host, using the real NAT-088 archive as the test input, and prepares the next question.

## Files

| file | what |
| --- | --- |
| `kl_reader.py` | reads every boot of a collector archive with NAT-062's own `parse_kl`/`unescape`; merges the `KL` dumps of replay boots by offset; a different byte string at one offset is a *conflict* (listed, the first kept); the head/tail ranges minus the records received are exact *holes*; the text carries a marker at every hole and at the announced gap |
| `analyze_nat089.py` | Stage A analyser, pre-registered rows A1-A8 (see its docstring): boot-task lines (kernel and console form), per-label launchd spawns/exits, `ps -A` heartbeat lists, panic and PID 1 exit |
| `test_nat089.py` | 60 tests: hand-built dumps (every number written out), row-by-row hand-built texts, and the real NAT-088 archive (literal facts read by hand before this code existed) |
| `mutate_nat089.py`, `mutation.json`, `equivalent.json` | mutation pass over the two modules (derived from NAT-087's runner) |
| `stage-a-jobs.json` | the Stage A small root: hashes and the job table read from the plists |

## What the real NAT-088 archive gives under the new reader

The final dump (`why=2`, 57,665 bytes announced: head 8,192, announced gap 16,705, tail 32,768) arrives with 399 of 428 records and ONE hole of 2,784 bytes (offsets 33,441-36,225), no conflicts.
Over its text the analyser reads exactly the 3 boot tasks that ran (`commit-boot-mode`, `restore-datapartition`, `init-with-data-volume`), the 20 that were skipped, "Early boot complete" at kernel 193.752018 s,
52 launchd lines, 3 `ps -A` lists, and the heartbeat job `com.nat085.ps` with 3 spawns (first at launchd clock 224.159344 s) alive in the last list. These match the hand reading recorded in NAT-088. It does not change
NAT-088's recorded outcome (inconclusive under the pre-registered ladder). Run against the Stage A job table the row is A8, because that image had no Apple job: the analyser says so instead of guessing.

## Stage A (prepared, not run)

Question: with restore-mode launchd, which of Apple's daemons from the donor set are running at the last `ps -A` list, which died, and with what reason?
Small root: `tools/ios/build_pid1_chain.py --recipe artifacts/nat-083/recipe --rc rc.nat083 --jobs --skip-job com.apple.wifid --skip-job com.apple.backboardd --skip-job com.apple.SpringBoard --job docs/procedures/nat-085/com.nat085.ps.plist`.
It holds 19 Apple plists plus the heartbeat. Seven Apple jobs start by themselves (RunAtLoad or KeepAlive true and not disabled: containermanagerd, distnoted, fseventsd, logd, usermanagerd, powerd,
runningboardd); `com.apple.syslogd` is `KeepAlive` but its stock plist says `Disabled: true`, so launchd does not start it (an earlier draft of this table counted eight; `read_jobs` now excludes
disabled jobs and `test_the_stage_a_tree_has_seven_self_starting_apple_jobs_not_eight` pins it). Two more plists are disabled while a feature flag is off (cfprefsd.xpc.daemon.system, containermanagerd.system;
the flag state of the phone's userland is not known). The remaining eleven start only when a client asks for their Mach service, so the run also shows which on-demand lookups happen. Eight plists
carry `LimitLoadToSessionType` (seven `System`, one `System` only if a feature flag is on): which launchd domain may load them is a question of the run (the NAT-088 heartbeat, which has no such key, ran in `user/501`), so
the analysis table lists the raw `disabled` and `limit_session` of every job next to its spawns and exits. wifid is left out (no Wi-Fi driver; the donor ran it with a
Wi-Fi boot-arg), backboardd and SpringBoard are left out until the daemons below them are known, because the log window (head 8 KiB + tail 32 KiB) cannot hold their output (the donor reports
about a megabyte of SpringBoard output in half a minute).

Not established by this task: that any Apple daemon runs on the S24, that the persona warning (`Unable to find persona with type 6`) is harmless for them, or anything about display, input, GPU or SpringBoard.
`build_pid1_chain.py` gained `--skip-job` (the label must be in the donor's set; the report lists the skipped labels).

Persona note (source review of `references/apple-xnu`, nothing measured): the type in launchd's `Unable to find persona with type 6` is `PERSONA_SYSTEM_PROXY` (`bsd/sys/persona.h:45`). The kernel's `personas_bootstrap()`
(`bsd/kern/kern_persona.c:96-125`) only initialises the list and the default credentials; it creates no persona, so every persona lookup returns ESRCH until user space allocates one. The warning is therefore expected on
this kernel, and it was harmless for the heartbeat (`ps` ran and exited 0 in NAT-088). Whether a daemon that spawns with a persona attribute fails the same way is one of the things Stage A can show; if a daemon
exit line names a persona or `posix_spawn` error, that is the first thing to read.
