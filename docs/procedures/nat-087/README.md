# NAT-087: Apple's launchd in restore/ramdisk mode (`xrd=md0`), no boot tasks, no service cache needed

Host-side material for one native run of `loader-diag-xnu-rm-md1` (decision `docs/decisions/0034-nat087-loader-diag-xnu-rm-md1-single-run-2026-11-12.md`).

Why: the NAT-086 run (decision 0033) got Apple's launchd past the `keybag` boot task (`/chosen/ephemeral-storage` made keybagd print `DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT`;
eleven more boot tasks ran) and ended at the boot task `launchd_cache_loader`: the donor recipe deletes `System/Library/xpc/launchd.plist` on purpose ("launchd must load our choice of
jobs, not all 500 that Darwin has"), the loader aborted (`Failed to create SecStaticCodeRef [-67068|errSecCSStaticCodeNotFound]`) and XNU panicked by design (`launchd_cache_loader[28]
exited -- exit reason namespace 7 subcode 0x1`). The job `com.nat085.ps` never ran.

Disassembly of the pinned `sbin/launchd` (capstone over the IPSW binary of the local iPhone10,3 16.5 unpack; **source review, nothing observed on the phone yet**):

* launchd asks sysctl `kern.bootargs` and searches it with `strstr` for `rd=md0` (and the strings `Restore`, `Ramdisk`, `RamDisk`); a hit sets a restore flag.
* The boot-task predicate (0x10003b8c8) runs a task if it is `PerformAlways`; after a userspace reboot only `PerformAfterUserspaceReboot` tasks; with the restore flag a task without
  `PerformInRestore` is skipped. In the embedded Boot dictionary only `commit-boot-mode`, `init-with-data-volume` (`PerformAlways`) and `restore-datapartition` (`PerformInRestore`,
  program `/usr/libexec/HorizonSetup`, absent here) qualify. `launchd_cache_loader` (`RequireRun`, `RequireSuccess`) does not.
* With the restore flag and no data volume the line `Restore environment starting.` is logged and a missing service cache is not fatal (`No service cache` is the fatal path otherwise).

The kernel must keep rooting on `rd=md1` (the delivered APFS). XNU's `PE_parse_boot_argn_internal` compares whole keys, so a last token `xrd=md0` is invisible to the `rd` lookup, while
`kern.bootargs` returns the whole line and launchd's `strstr` finds `rd=md0` inside `xrd=md0`. (The donor's own boot keeps `rd=md0` for the same reason.)

Question of the run: with ` xrd=md0` as the last command-line token, does launchd print `Restore environment starting.`, skip every boot task but the three, continue without a service
cache, and stay alive long enough to run the job twice?

The single variable relative to NAT-086 is the command line (one token and the `nat_attempt` tag). The ADT (`ephemeral-storage`), the small root with the one job, the delivered root, stage0/init
and `rc.nat083` are NAT-085's.

| file | purpose |
|---|---|
| `build.py` | NAT-085's build with the token appended by a hook on `make_cmdline` (the chain below it stays as reviewed); refuses an existing `xrd=` and a line of 256 bytes or more; post-checks `build.json` (`rd=md1` once, no other `rd=` token, ends in the token) and records `nat087_*` |
| `derive87.py` -> `session_nat087.py` | the session driver, derived from NAT-085's `session_nat085.py` by 9 counted substitutions (`derive87.py --check`); the only launcher of the run |
| `analyze_nat087.py` | NAT-083's chain ladder (rows 1-9, unchanged module) and then the pre-registered restore ladder R1-R9 over the console text after the last `$ exec` line |
| `test_nat087.py` | host tests: XNU's real `bootargs.c` compiled with shim headers; Apple's launchd Boot dictionary; the build wrapper; the built payload vs NAT-085's byte for byte; the derivation; the reader and ladder; the real NAT-084 and NAT-086 archives |
| `mutate_nat087.py`, `mutation.json`, `equivalent.json` | mutation pass over the analyser, the build wrapper and the derivation |
| `task.json`, `evidence.json` | the registry entry and the host-test evidence of this directory (the native task NAT-088 is in `docs/procedures/nat-088/task.json`) |

Commands (host only, no device):

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-087/test_nat087.py
    python3 -B -I docs/procedures/nat-087/derive87.py --check
    python3 -B -I docs/procedures/nat-087/session_nat087.py --image loader-diag-xnu-rm-md1 --out artifacts/nat-087/preflight-001      # gates only, opens nothing

The run itself (`--execute`) needs the decision file, the `native` permit citing it and the native task of the run (NAT-088); see the decision. After the run the analyser is applied unchanged:

    artifacts/nat-065/venv/bin/python -B -I docs/procedures/nat-087/analyze_nat087.py --archive <run>/archive --events <run>/usb-events.jsonl --report <run>/report.json \
        --delivery <run>/delivery --root artifacts/nat-083/system-padded.apfs --size 2475720704 \
        --sha256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6 --out <run>/analysis.json --log-out <run>/kernel-log.txt

Evidence class of everything in this directory: host-test (source review for the launchd reading). Nothing here measures the phone. That launchd enters restore mode, skips the tasks, survives
without a service cache and loads the job are all unknown until the run. Hand-written: the console text of a launchd in restore mode (no run has printed it).
