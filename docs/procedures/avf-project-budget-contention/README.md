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
