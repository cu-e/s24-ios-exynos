# Shared source integration gate

INT-002; permanent kernel/build/boot/virtualization integrator
`codex-integrator-kernel-20261106-cm`. Base `aac27cfbc0d71b34eda33ddf366c72427507ae0b`;
branch/worktree `team/int-kernel-20261106` / `worktrees/int-kernel-20261106`.
The first priority is a genuine XNU QEMU console. No phone work is authorized.

Both kernel and platform integrators use **the same primary-checkout
`state/.integration.lock`**, never a worktree-local lock and never `.lab.lock` as
an outer lock. Prepare and review candidate commits in an isolated worktree
outside the lock. Freeze a JSON plan with full primary base/candidate commit
identities, ordered candidate commits, source-to-candidate mapping, exact source
paths, and existing review/evidence/dependency capsule paths plus SHA256 values.
Do not include registry or generated planning files in a source candidate.

The gate's audit mode obtains that exclusive flock and checks the actual current
primary HEAD, candidate identity/ancestry/path set, clean candidate, and capsule
hashes. Any primary staged changes or dirty/untracked intersection with source
paths rejects the candidate. Unrelated dirty primary registry/views remain
untouched. A stale base requires a refreshed candidate and plan; it never means
silently rebasing or accepting another owner's implementation.

Publication additionally requires an existing root approval receipt naming the
exact plan digest and the resource lease. This receipt records session approval,
not authentication or independent authority. Root must approve the concrete
candidate/protocol before any real primary publication. Under the same continuous
flock, repeat the audit, fast-forward primary to the frozen candidate SHA, verify
that exact HEAD, run the one shared common check, and verify HEAD again. Retain
all failure/publication/check results. There is no implicit rollback. Integrators
and the coordinator must also take this same lock for other primary Git writes.
Ordinary lab registry updates keep their own short `.lab.lock`; the integration
gate does not hold that lock across checks.

Initial development is limited to light isolated Git/filesystem/process tests.
Register `INTGATE-001` before executing those tests. In temporary repositories,
verify real competing processes use one lock, stale HEAD is checked after lock
acquisition, dirty source/staged index and registry candidates are rejected,
unrelated dirty ledger bytes remain unchanged, and an approval mismatch cannot
publish. No full build, common `make check` or QEMU run is authorized for this
initial qualification. Tool publication itself needs independent review first.

The light suite also performs real fast-forwards in disposable repositories,
substituting a tiny check callback that tries to acquire the same lock. It
verifies continuous lock ownership and retention of the published HEAD after a
synthetic check failure. This does not execute the project's common check or
qualify its supervisor/admission/timeout path.

Run the light suite with a fresh owned output directory, `LC_ALL=C`,
`PYTHONUTF8=1`, `PYTHONNOUSERSITE=1`, a 256 MiB `prlimit --as=268435456`, and
`GATE_TEST_OUTPUT` naming that directory's `cases` subdirectory:

```sh
python3.12 -s docs/integration/kernel/test_gate.py -v
```

Shared CLI (publication remains subject to concrete root approval):

```sh
python3.12 -s tools/integration_gate.py audit --root PRIMARY --plan PLAN.json --output FRESH_OWNED_DIRECTORY
python3.12 -s tools/integration_gate.py publish --root PRIMARY --plan PLAN.json --approval APPROVAL.json --output FRESH_OWNED_DIRECTORY
```

The plan keys are `base_head`, `candidate_head`, `candidate_worktree` (relative
to primary), `commits` (ordered full SHAs), `commit_map` (ordered objects with
`source` and `candidate` SHAs), `paths` (unique exact relative file names), and
`bindings` (existing review/evidence/dependency objects with `path` relative to
primary and `sha256`). Approval keys are `approved_by: "root"`, `plan_sha256`
and a nonempty `resource_lease`. Plans/receipts are bounded to 1 MiB and parsed
from the exact bytes whose digest is recorded. All other file hashes stream.
An audit passes without granting publication permission. A changed base/plan
requires refreshed root approval before publication.

Every source-to-candidate mapping must have an identical binary/full-index patch
with external diff and text conversion disabled. All `state/` and `planning/`
paths are forbidden, including both lock files. Ignored data at a new candidate
path and symlink parents are rejected too. The common check records live
0.2-second session samples and peak aggregate RSS, terminates its owned session
on the 2 GiB RSS stop threshold, low-memory/pressure condition or deadline, and
records remaining owned PIDs after cleanup. Sampled aggregate stopping is not a cgroup hard
limit and can observe overshoot between samples. Stable 4 GiB admission is
required before publication and again before the common check.

Future common checks require three consecutive available-memory samples at or
above 4 GiB, a root resource lease, at most two jobs and a 2 GiB sampled
aggregate owned-RSS stop threshold. Guest execution remains a separate root-admitted queue
with at most one QEMU; the gate does not grant a guest lease. Preserve existing
source tools and immutable artifacts.

The first actual common check failed because the initial extra 2 GiB
`RLIMIT_AS` prevented the JVM from reserving compressed class space, despite a
180,826,112-byte peak owned RSS. Root independently reproduced this with
`javac -version`: exit 1 under that cap, exit 0 without it. The gate now leaves
inherited address-space limits unchanged and records
`address_space_limit_bytes: null` for no gate override. This does not remove the
RSS/job/pressure/deadline/cleanup policy, skip tests, or add JVM options. The
original failed publication and diagnostic remain immutable artifacts.

Next component: independently reviewed/frozen VM-008, followed by guest object
components. The supplied immutable object graph is
`worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json`,
SHA256 `afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`:
bsd 538, osfmk 325, iokit 104, libkern 77, security 23, pexpert 11, libsa 1,
san 1. Source implementation remains with its original owners. Independent
review and concrete root approval are still pending.
