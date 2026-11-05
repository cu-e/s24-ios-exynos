# LAB-002 review handoff

Owner: `codex-team-lab-view-io-20261105-ch`; branch/worktree:
`team/lab-002-20261105` / `worktrees/lab-002-20261105`; base:
`bf14600d5a2d6f70c33899634d463db49b47a6f6`. Keep the task in progress for
coordinator review. Only `tools/lab.py`, `tests/test_lab.py` and this procedure
directory changed. No registry or generated worktree views are included.

`publish_views` still resolves every path through `within` before any skip. It
compares regular-file bytes to the rendered UTF-8 bytes under the caller's
existing ledger lock. Equal text files retain their inode and mtime. Missing,
different, unreadable and nonregular targets use the existing atomic writer;
read errors do not prevent a repair that the old atomic replacement allowed.
The authoritative registry/event transaction is unchanged. The JSON index is
still unconditionally atomically replaced last. Schema, authorization, claims,
ownership, dependencies and reservations are unchanged.

`LABVIEW-001` was registered and its actual saved owner/task/planned status,
procedure and hypothesis verified before testing. The qualification runner
also saved that prospective plan and its registry digest before execution.
All tests and benchmarks used independent temporary registries, never the live
primary registry. The baseline source is the exact `git show` output for the
base commit, retained with its SHA256 and command exit status.

The 36 focused tests passed in 3.915005 s (`qualification-4/focused-tests.txt`).
That includes the existing parallel claim, ownership, dependency, blocked path
reservation and board-check tests plus seven new filesystem tests. The new tests
check actual bytes, inodes and mtimes; changing only a timestamp; a task-changing
transaction; missing/invalid UTF-8/CRLF repair; external symlink rejection before
skipping; real FIFO replacement; a read-denial fault followed by real atomic
replacement; and a mid-publication failure that saves state/events while keeping
the old index, fails board-check, and repairs successfully. The avoided-write
test fails against the original source as the expected negative control.

`qualification-5` reused that passing result only after verifying exact hashes
of production and both test files, then measured actual wrapped atomic writers,
fsync and replace calls; wrappers delegate to real filesystem operations.
Every phase's complete output-file SHA256 manifest matched between baseline and
patched implementations, including the authoritative registry and JSON index.

| Tasks | Phase | Text writes baseline / patched | JSON writes | Fsync baseline / patched | Seconds baseline / patched |
|---|---|---|---|---|---|
| 100 | Identical snapshot | 102 / 0 | 1 / 1 | 103 / 1 | 0.321678 / 0.018860 |
| 100 | Advancing snapshot | 102 / 1 | 1 / 1 | 103 / 2 | 0.317088 / 0.024590 |
| 100 | Task transaction | 102 / 3 | 2 / 2 | 104 / 5 | 0.344406 / 0.063502 |
| 500 | Identical snapshot | 502 / 0 | 1 / 1 | 503 / 1 | 1.555981 / 0.063853 |
| 500 | Advancing snapshot | 502 / 1 | 1 / 1 | 503 / 2 | 1.550453 / 0.072408 |
| 500 | Task transaction | 502 / 3 | 2 / 2 | 504 / 5 | 1.567511 / 0.201193 |

Replace counts equal fsync counts in all phases. A changing snapshot timestamp
legitimately rewrites BOARD.md. The transaction writes state/lab.json first,
then STATUS.md, BOARD.md and one affected card, then state/board.json last.
These single local timings are observations, not a throughput guarantee; no
claim is made about every source of the observed main-checkout writer delay.

Preserved failures: `qualification-1`, `-2` and `-3` each exited 1 before tests
with MemoryError under the 256 MiB address-space cap. Initial `ru_maxrss` figures
were insufficient to attribute resident startup memory and that interpretation
was corrected. Actual bounded `/proc` diagnostics identified the 233,242,624-byte
read-only locale archive mapping. Per-command `LC_ALL=C PYTHONUTF8=1
PYTHONNOUSERSITE=1` avoids that mapping and keeps UTF-8 output. No global setting
changed. `qualification-4` exited 1 after its passing suite because the initial
synthetic fixture omitted three declared permission scopes; only that fixture
was corrected before the measurement-only rerun. All original failure reports
and tracebacks remain local. The final job's actual VmPeak was 42,312 KiB and
VmHWM 35,648 KiB under the 268,435,456-byte address-space limit.

Actual successful measurement command (exit 0):

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 timeout --signal=TERM --kill-after=5s 180s python3.12 -s docs/procedures/lab-view-io/qualify.py --run qualification-5 --reuse-focused qualification-4
```

Local evidence root: `worktrees/lab-002-20261105/artifacts/lab-view-io/`.
The final evidence capsule is `qualification-5/evidence.json`; it binds the
committed production/test/procedure bytes, prior failed reports, prospective
plan, baseline source, test logs, measurements, commands/exits and tool hash.
`git diff --check` passed. Full `make check` and primary-registry consistency
checks remain for the coordinator after integration; they were not repeated in
the isolated worktree with absent private inventory. No compiler, emulator,
phone, ADB, root, flash, reboot, APK or MMIO operation was performed.

Next: review the small production diff and its evidence, integrate the scoped
commit, run the coordinator's common checks and assess LAB-002 acceptance.
