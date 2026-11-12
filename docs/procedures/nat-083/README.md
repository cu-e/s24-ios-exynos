# NAT-083: the delivered APFS as the kernel's root, Apple's userland on the project's XNU

Host-side material for one native run of `loader-diag-xnu-rt-md1` (decision `docs/decisions/0032-nat083-loader-diag-xnu-rt-md1-single-run-2026-11-12.md`).

Question of the run: with the delivered APFS image as the kernel's root (`rd=md1`), does the donor boot chain (stage0 -> init on the small image) run, do Apple's own `df`, `mount`, `ps -A`
and `vm_stat` run to completion on the project's XNU, and what does Apple's `launchd` do as PID 1 after `exec /sbin/launchd.darwin` with an empty job list?

| file | purpose |
|---|---|
| `build.py`, `make_variant83.py`, `build-report-*.json` | build of the loader/payload variant: md0 = small donor root, `rd=md1`, new image name and `nat_attempt` tag |
| `stage0-md0.patch` | counted substitution of the pinned donor `stage0.c` (`/dev/md1` -> `/dev/md0`, 3 occurrences); the project's md numbering is the opposite of the donor's |
| `rc.nat083` | the rc file of the small root: `/bin/df`, `/sbin/mount`, `/bin/ps -A`, `/usr/bin/vm_stat`, then `exec /sbin/launchd.darwin` |
| `derive83.py` -> `session_nat083.py` | the session driver, derived from NAT-080's `session_nat078.py` by 12 counted substitutions (`derive83.py --check`); the only launcher of the run |
| `analyze_nat083.py` | the pre-registered ladder (rows 1-9 of decision 0032) over the run's archive, the companion's record and the host copy of the root; uses NAT-081's replay-boot rule (`docs/procedures/nat-081/sessions.py`) |
| `test_nat083.py`, `test_analyze83.py` | host tests (derivation; formats rendered from the pinned C sources; the ladder; gaps; the real NAT-078 archive through `analyze()` and `main()`) |
| `mutate_nat083.py`, `mutation.json`, `equivalent.json` | the mutation pass over the analyser and the derivation (639 candidates; the three survivors are explained) |

Commands (host only, no device):

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-083/test_analyze83.py
    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-083/test_nat083.py
    python3 -B -I docs/procedures/nat-083/derive83.py --check
    python3 -B -I docs/procedures/nat-083/session_nat083.py --image loader-diag-xnu-rt-md1 --out artifacts/nat-083/preflight-001      # gates only, opens nothing

The run itself (`--execute`) needs the decision file, the `native` permit citing it and the native task of the run; see the decision. After the run the analyser is applied unchanged:

    artifacts/nat-065/venv/bin/python -B -I docs/procedures/nat-083/analyze_nat083.py --archive <run>/archive --events <run>/usb-events.jsonl --report <run>/report.json \
        --delivery <run>/delivery --root artifacts/nat-083/system-padded.apfs --size 2475720704 \
        --sha256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6 --out <run>/analysis.json --log-out <run>/kernel-log.txt

Evidence class of everything in this directory: host-test. Nothing here measures the phone; the real kernel text is judged only after the run.
