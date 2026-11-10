# GPU-016 handoff

The result is in `research/notes/GPU-016-stock-vulkan-baseline.md`. Raw output stays in Git-ignored
`artifacts/gpu-016/session-001/` (`report.json`, `cooldown.json`, `cooldown-2.json`).

GPU-016 is the device measurement that GPU-003 asks for. It was added as a child task because GPU-003's
paths (`artifacts/`, `research/notes/`, `devices/`) overlap reservations held by NAT-001, KRN-003 and
KRN-041. GPU-003 is still pending in the registry. Close it, or narrow it, only after a reviewer accepts
this evidence for GPU-003's criteria.

## Repeat

The probe package must not be installed, and the phone must be awake and unlocked. Then run:

```sh
python3 -I docs/procedures/gpu-016/run_probe.py --run session-NNN \
  --apk artifacts/android-probe/apk-session7/s24-vulkan-probe.apk
```

The script refuses any APK whose digest differs from the TST-002-qualified one. If the probe's compiled
inputs change, rebuild it, requalify it on the emulator and update `QUALIFIED_SHA256` deliberately. The
script always force-stops and uninstalls the probe, then checks that the package is gone and that uptime
has increased.

## Open

- On the phone the app's `cancelled` outcome was not observed. A run takes about 10 ms, which is
  shorter than UI input latency. To exercise cooperative stop on the phone, the app needs a longer
  bounded workload, for example several submissions, inside its own deadline. That changes compiled
  inputs, so it needs requalification.
- GPU timing needs timestamp queries; the timestamp period is 39.0625 ns according to GPU-014. GPU
  temperature needs a sensor that the shell user can read.
