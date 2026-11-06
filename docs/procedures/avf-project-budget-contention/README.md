# Shared-budget contention measurement

VM-044 investigates actual wave20 finite broker-lock timeouts without changing
its AF193 runner, plans, approvals, queue, products or surviving processes.
The VM016 first-command resource stop and VM012 pre-child validation failure are
both actual `Project budget lock acquisition timed out` outcomes. They are not
silently classified as stale ownership or retried compiler work.

Register a new bounded host experiment before running the fixture. It creates
six real Python controllers and six tiny Python sleeping children in an owned
temporary project. The allocation, stable broker lock and state are independent
of the real resource queue. Controllers register sequentially, then concurrently
sample their real child sessions at the accepted cadence. They remain alive until
all monitoring rounds finish; their own children and reservations are cleaned
before the controllers exit. No compiler, guest, QEMU or common suite runs.

Instrumentation wraps the accepted functions in each test interpreter only.
It records actual nonblocking flock attempts, acquisition wait, the interval from
successful acquisition to transaction return (a conservative held-time bound),
/proc scans, live-validation time and fsync time. Source files and guards are not
patched during measurement. Host memory/pressure and swap observations are
retained; host swap is not attributed causally to this project. Unsafe pressure
or memory admission defers the test, with no automatic retry. The conservative
host-control-only gate reuses accepted `qemu_host.pressured`: full avg10 >=2 or
some avg10 >=10, plus three one-second observations of MemAvailable >=4GiB.
This follows the coordinator instruction to defer observed PSI pressure; the
resource queue itself does not define a PSI threshold, and production budget
behavior is not changed by this harness condition. The same gate is checked
after measurement.

The correction must follow the measured bottleneck, keep the finite0.5-second
lock guard and every ownership/allocation/snapshot/canonical/deadline/cleanup
check, and avoid cross-transaction caches. The exact corrected source and new
measurement require independent review and root common acceptance. This task
never grants an actual compiler retry or runner adoption.

```sh
python3 fixtures/public/avf-project-budget-contention/check.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --engine /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py \
  --out artifacts/avf-project-budget-contention/baseline-001
```

The registered baseline measured six finite lock timeouts in60 transactions.
Held-interval median was66.97ms (max108.60ms); the fresh full `/proc` scan consumed
median53.89ms and82% of total measured held time. Live validation and fsync were
much smaller. These are actual interval observations, not hard kernel maxima.

The prospective correction keeps that fresh scan inside the same lock. It uses
strict libc `realpath` for every PID's cwd/executable link to remove Python's
component-walk overhead. No path, PID, state or canonical result is memoized,
including within a scan. Every PID's current stat/start/RSS/swap and proc link
is still read; missing/permission failures remain fail-closed. A raw-target memo
was explicitly rejected because ancestry substitution could make it stale.

A separate actual CW77 OSKext command exited0 but retained a final project sample
lock error while AF193 still called it pass. The original capsule and genuine
object bytes remain unchanged. Prospectively, final sampling exceptions or
resource violations now produce resource-deferred qualification rather than
object credit, preserving the successful child exit and its artifacts.

The first corrected FE093 measurement is retained as a partial improvement:
2/60 finite timeouts remained (baseline6/60). Independent controls saw0/48 in
both versions, which demonstrates host-load variance rather than a guarantee.
No favorable rerun was selected. That source/capsule stays physically unchanged
in `vm-044-ep-20261106`; the next correction uses a separate fix1 worktree.

The same timing records reveal a second full scan outside each transaction:
`sample(session)` scanned all PIDs merely to obtain one requested SID's start,
then performed the full fresh locked scan. Median outside time was59.83ms in
the baseline and37.50ms in FE093. The final correction reads only that requested
`/proc/PID/stat` afresh; the existing immutable start identity is still checked
against the complete fresh locked table on every sample. No snapshot or path
validation moves outside the lock and no new cache is introduced.

Object and resource verdicts are distinct. A successful child whose final sample
is missing can still have its genuine Mach-O bytes and dependencies validated;
those object facts remain in its sidecar. Resource qualification is explicitly
inconclusive/failed, further compiler admission stops, and the whole run cannot
claim PASS or qualify a later eight-job trial. Child exit and output hashes are
retained. Historical AF193/CW77 records are not rewritten.

The direct-session-stat measurement is retained as another partial improvement:
1/60 finite timeouts remained, with no surviving owned children. Its immutable
2bb source and raw capsule remain in fix1. During the failed half-second wait,
15 other transactions acquired the lock, including five acquisitions by one
contender. The polling flock does not guarantee fair admission; lower scan cost
is not a guarantee that contention is eliminated. No favorable retry follows.

A separate fix2 preserves the measured timing code and catches failures during
stable-memory/project-before admission before child creation. It returns an
explicit resource-deferred command with child_started=false, not-started child
execution and inconclusive resources. Main retains this command and stops before
the next source row. Ordinary object/source validation errors keep their existing
classification; no failed observation is invented or labeled as a sample.

Handoff (2026-11-06): source stack is3be7c8a,6385cd1,3847923,a132516,
e4d2b0a,b78b181,0e6678d,3be77dd,fc58f8f. Final source is
`vm-044-ep-fix2-20261106/tools/build/avf_kernel_objects.py`, SHA
`e97a5c9e6edf4daae4924bafb9f50f9bbacf90f1257012da54401feebdb2f4f6`.
`measurement-001.json`, `measurement-002.json`, `measurement-003.json` bind the
three one-shot measurements and physical AF193/FE093/2bb sources. Timeout counts
are6,2,1 respectively; no result establishes solved contention. The final failed
waiter was overtaken15times during its half-second deadline. A fairness remedy
would require an operative separately reviewed change and a newly registered
measurement, not another observation selected for zero failures.

`focused-evidence.json` binds24 passing focused controls. It also retains failed
focused-001 and an exact-hash retrospective source archive. After that failed
assertion, the fix2 entrypoint was changed before a preservation reminder; its
original physical path no longer has the failed source. This provenance mistake
is explicit: the archives were created afterward from the exact committed bytes,
not captured during the failed run. Raw001 is unchanged. The corrected source,
control fixture, raw002 and all older physical AF193/FE093/2bb witnesses are now
preserved. No rerun is used to repair that history.

The prechild refusal checks force genuine finite lock contention before any child
starts. The dispatch check feeds that actual refusal into main's real row loop
with two explicitly synthetic source rows and a post-loop namespace stop seam.
It proves one command/one resource-deferred object record, resources inconclusive
and no second dispatch. It fabricates no Mach-O object and makes no source or
namespace qualification claim. Final-sample checks preserve real successful
Python child bytes while recording incomplete or failed resource qualification.
