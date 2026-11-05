# Power observation input qualification

PWR-003, owner `codex-team-power-host-20261105-bj`. Preparation only for
PWR-001; its kernel/hardware dependencies and ownership remain unchanged.

Plan laboratory experiments before implementation tests. Read pinned Samsung
thermal/clock/ACPM declarations and exact E1S ACPM source. Main references and
existing evidence are read-only with `GIT_NO_LAZY_FETCH=1` and
`GIT_OPTIONAL_LOCKS=0`. Absent public blobs may be fetched only into owned
artifacts at their exact pin, checking the Git blob against pinned tree data.

Implement a bounded host-only observation/admission model for source-confirmed
units, identifiers, message lengths and unavailable/error/stale/Stop behavior.
Compare genuine declarations or extracted calculations. Execute native host
ASan/UBSan and faulty negative controls, then ARM64 compile-only where useful.
One small compiler job, at most 256 MiB new RSS; no heavy build lease.

No device/ADB/MMIO, thermal sensor probing, hardware clock/voltage/reset/power
operation, command submission, firmware load or private Apple service claim.
No guessed safe clock, voltage or temperature limit. Public source tables and
synthetic host input are not calibration, fitted firmware or physical safety.
Keep exact source/tool/command/exit/output hashes and handoff; retain task in
progress until coordinator review/integration/common checks.

Reproduce with a fresh run name and the complete verified source cache:

```sh
python3 src/platform/power/host/check.py --run fresh-name --lab-root /home/egor/dev/pet/s24-ios-exynos --source-cache /home/egor/dev/pet/s24-ios-exynos/worktrees/pwr-003-20261105/artifacts/power-host
```

The runner never fetches or changes references. It verifies exact pinned tree
blob IDs and cache SHA256 before compiling genuine declarations/functions with
explicit synthetic IPC/QoS adapters. Keep source-session1..4 acquisition files:
one interrupted source-session2 HTTP read remains a failed acquisition report;
its two completed verified files remain valid. Source-session3 contains only
subsequent missing files, and source-session4 binds the genuine signed QoS API.
No source or runtime capsule is overwritten.

The compiler defaults to existing NDK27 Clang18 at
`/home/egor/.local/bin/clang`; native Linux ASan/UBSan runtimes are used.
Deliberately faulty heap and signed-overflow controls must exit nonzero with
the expected diagnostics. GNU time records actual resident peaks for each
sequential compiler job and the fixture; the runner rejects peaks over 256 MiB.
Owned input code and independently extracted genuine layouts/prototype compile
to arm64-apple-ios16.5 Mach-O objects without an Apple SDK, native XNU linkage
or ARM/device execution. Main unittest discovery does not automatically run
this source-contained fixture; coordinator integration must invoke it explicitly.
