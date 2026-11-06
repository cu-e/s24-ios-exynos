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
or memory admission defers the test, with no automatic retry.

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
