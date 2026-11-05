# Generated planning view I/O qualification

LAB-002; owner `codex-team-lab-view-io-20261105-ch`. Host-only source and local
filesystem work. Branch `team/lab-002-20261105`, worktree
`worktrees/lab-002-20261105`, baseline `bf14600d5a2d6f70c33899634d463db49b47a6f6`.
No device access, compiler, emulator, shared source mutation, or live registry
benchmark is involved.

Register `LABVIEW-001` against this existing procedure before execution, then
verify its saved owner, task, status, procedure and hypothesis in the primary
registry. The experiment tests whether comparing generated text bytes under the
existing ledger lock preserves coordination and publication failure detection
while avoiding replacement and fsync for unchanged files.

Run one bounded Python job from this worktree:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3.12 -s docs/procedures/lab-view-io/qualify.py --run qualification-5 --reuse-focused qualification-4
```

The runner sets a 256 MiB address-space limit, executes only `test_lab.py` and
`test_planning.py`, and measures actual wrapped filesystem calls (the wrappers
delegate to the original functions). All registries and output files are local
to fresh artifact directories or temporary directories. The unchanged source
baseline is read using `git show` with lazy fetching and optional locks disabled.
For both implementations and 100/500 independent synthetic tasks, first publish
all files, then measure a repeated identical snapshot, an advancing snapshot
timestamp and a real task-changing transaction. Count text writes, JSON writes,
fsync and replace calls; measure elapsed wall time with `perf_counter`. Setup is
excluded from measured phases. Fixed timestamps make equal-byte cases explicit;
an advancing timestamp legitimately changes BOARD.md and the JSON index.

`qualification-1`, `qualification-2` and `qualification-3` failed before tests with `MemoryError`.
The initial `ru_maxrss` comparison (1,711,892 versus 9,304 KiB) did not establish
resident startup usage: that counter can inherit a pre-exec maximum. An actual
`/proc/self/status` stdlib-import diagnostic with user-site loading disabled
showed Python 3.14 VmSize 260,112 KiB and VmRSS 23,768 KiB after importing
`unittest.mock`; its virtual reservation nearly exhausts a 256 MiB address-space
cap. Python 3.12 also failed, with actual VmSize 258,888 KiB / VmRSS 24,052 KiB
before the ledger read. A bounded `/proc/self/maps` diagnostic identified a
233,242,624-byte read-only mapping of `/usr/lib/locale/locale-archive`. Use
per-command `LC_ALL=C` to avoid that archive mapping and `PYTHONUTF8=1` to retain
the original UTF-8 text encoding, with the same 256 MiB cap. Record actual
process memory counters. Disable user-site loading for this job and inherited
CLI children; do not change global site files or unrelated processes. Keep all
original failed reports. This is an address-space constraint diagnosis, not a
claim that the Python process resident set used 1.7 GiB.

The focused 36-test suite passed in `qualification-4`, including the expected
baseline negative-control failure. Its subsequent benchmark failed because the
synthetic project did not declare all four permission scopes. The fixture now
declares them explicitly. `--reuse-focused qualification-4` verifies exact source
and test hashes before reusing that passing result; a fresh reproduction can omit
that option and use a new run name to execute the suite and measurements.

The focused tests must establish real inode/mtime preservation, selective
replacement, repair of missing and corrupt bytes, containment before skipping,
and detectable interrupted publication with authoritative state/events already
saved and the old JSON index retained. Existing parallel claim, owner,
dependency, blocked reservation and snapshot checks must still pass. An
unreadable existing regular file must fall back to the existing atomic writer;
nonregular targets must not be opened for comparison.

Save original command output, exit codes, source and tool hashes, baseline bytes,
counts and timings even on failure. Record the experiment afterward. Timings are
local observations, not a throughput guarantee. Full `make check` is deferred to
the coordinator after integration because this worktree lacks ignored private
inventory and broad build inputs. Leave LAB-002 in progress for review.
