# NAT-085: keybagd skips its init (`ephemeral-storage`), Apple's launchd gets past the `keybag` boot task

Host-side material for one native run of `loader-diag-xnu-ep-md1` (decision `docs/decisions/0033-nat085-loader-diag-xnu-ep-md1-single-run-2026-11-12.md`).

Why: the NAT-084 run (decision 0032) put Apple's userland on the S24 up to the launchd boot task `keybag`: `keybagd --init` went down the `MKB_INIT` path (no
`/private/var/keybags/systembag.kb`, no SEP), printed `FATAL KEYBAG ERROR` and asked launchd to reboot into recovery at kernel time 203.3 s. Disassembly of the shared
cache's `os_variant_uses_ephemeral_storage` and of keybagd shows a way around that path that needs no SEP and no keybag file: keybagd prints
`DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT` and returns when sysctl `hw.ephemeral_storage` is non-zero. XNU (`kern_mib.c`, `sysctl_load_devicetree_entries`) creates that
sysctl from the device-tree property `/chosen/ephemeral-storage` when it is exactly four bytes.

Question of the run: with `/chosen/ephemeral-storage = 1` in the ADT, does keybagd skip its init, which boot tasks does Apple's launchd run after `keybag`, and does
launchd stay alive long enough to run a launchd job twice (`/bin/ps -A`, KeepAlive, 10 s throttle)?

The single variable set relative to NAT-084 is: the ADT property, one launchd job (`com.nat085.ps`), and the new image name / `nat_attempt` tag. `rc.nat083`, the delivered
root image and the stage0/init pair are NAT-083's.

| file | purpose |
|---|---|
| `make_adt85.py` | appends `("ephemeral-storage", u32 1)` to `/chosen` of the pinned ADT (refuses another input, a duplicate property, a lossy re-serialisation); output `artifacts/nat-085/e1s-eph.adt` |
| `build.py`, `build-report-pid1.json` | build of the loader/payload variant: NAT-083's build with the ADT swapped (exactly one swap) and md0 = the small root with one job; `tools/ios/build_pid1_chain.py --job` copies the plist into `root/LaunchDaemons` |
| `com.nat085.ps.plist` | the one job: `/bin/ps -A` to `/dev/console`, `RunAtLoad`, `KeepAlive`, `ThrottleInterval 10` |
| `derive85.py` -> `session_nat085.py` | the session driver, derived from NAT-083's `session_nat083.py` by 10 counted substitutions (`derive85.py --check`); the only launcher of the run |
| `analyze_nat085.py` | NAT-083's chain ladder (rows 1-9, unchanged module) and then the pre-registered stage ladder S1-S9 over the console text after the last `$ exec` line |
| `test_nat085.py` | 62 host tests (ADT edit; derivation; job; stage ladder; gaps; negative control on the real NAT-084 archive) |
| `mutate_nat085.py`, `mutation.json`, `equivalent.json` | mutation pass over the analyser, the ADT edit and the derivation |
| `evidence.json` | host-test evidence of this directory |

Commands (host only, no device):

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-085/test_nat085.py
    python3 -B -I docs/procedures/nat-085/derive85.py --check
    python3 -B -I docs/procedures/nat-085/session_nat085.py --image loader-diag-xnu-ep-md1 --out artifacts/nat-085/preflight-001      # gates only, opens nothing

The run itself (`--execute`) needs the decision file, the `native` permit citing it and the native task of the run (NAT-086); see the decision. After the run the analyser
is applied unchanged:

    artifacts/nat-065/venv/bin/python -B -I docs/procedures/nat-085/analyze_nat085.py --archive <run>/archive --events <run>/usb-events.jsonl --report <run>/report.json \
        --delivery <run>/delivery --root artifacts/nat-083/system-padded.apfs --size 2475720704 \
        --sha256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6 --out <run>/analysis.json --log-out <run>/kernel-log.txt

Evidence class of everything in this directory: host-test. Nothing here measures the phone. That keybagd skips on the phone, that launchd loads the job and that
launchd stays alive are all unknown until the run.
