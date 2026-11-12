# Stages and transition criteria

The detailed approved sequence, subsystem contracts and stop conditions are in [implementation.md](implementation.md). [CAPABILITIES.md](../CAPABILITIES.md) is the hardware evidence view; [BOARD.md](../BOARD.md) is the task view. A closed task is not a percentage of iOS support.

| Stage | Verifiable outcome | What it does not establish |
|---|---|---|
| 0. Foundation | Registry, sources, tooling tests and instructions | Execution on the phone |
| 1. Inventory | Dated facts from the actual device | Root/KVM access or recovery |
| 2. Host | Reproducible builds and structurally valid images | S24 boot |
| 3. Android GPU | Local measurements and controlled APK termination | XNU driver compatibility |
| 4. Recovery/control | Documented, then tested return procedure | Guaranteed return after every failure |
| 5. Native entry | Real XNU log and Android recovery | iOS userland execution |
| 6. Native services | Separately verified RAM root, input and storage | A complete phone OS |
| 7. Real iOS UI | Apple userland, touch, SpringBoard and Settings on this device | Native GPU acceleration |
| 8. Native peripherals | GPU/Metal, display, Wi-Fi/BT, sound, cameras, sensors and power separately accepted | Working carrier telephony/eSIM |
| 9. Cellular and eSIM | Registration, data, SMS, IMS/duplex calls and test-profile lifecycle | Apple services or iPhone-equivalent security |
| 10. Qualification | Mixed workload, repeated boot/sleep/reconnect and resource/storage checks | Guaranteed daily-driver reliability |

state/lab.json defines the current phase. A written plan or an upstream screenshot does not complete a task.

The registry contains the backlog and dependencies. Continue with RES-001, then RES-002/BLD-001. DEV-001 completed the initial authorized ADB inventory on 2026-11-05. Do not estimate iOS completion percentage from the number of closed tasks.

Current position (2026-11-13, no percentage; updated after NAT-109): the project's XNU mounts the delivered 2.31 GiB APFS root from RAM (`md1`), runs Apple's `launchd` as PID 1, and in `NAT-109` (`loader-diag-xnu-sc1-md1`, decision 0041) ran **Stage C1 (`SpringBoard` + `22 DARWIN_JOBS` + `382 --rest` on-demand plists + `libhakios.sb.dylib` + `fb_diff=1`)** on `SM-S921B/e1s`: full `455,754`-byte `why=2` KL dump returned (`gap=0`, `hole=0`, `drops=0`) before the loader hit Download Mode (`HOLD stage=0x51 code=0x223e`) after ~`118.2 s` of USB return (`chain_row 7`). Pre-registered analysers returned `row C4 springboard-exited`, `row B5 fb-swaps-no-diff`, `row H5 hb-ps-lists`, and `row A2 some-daemons-alive`, while post-hoc inspection established that **`SpringBoard[13]` spawned cleanly with all `libhakios.sb.dylib` hooks and stayed alive through `hb` round 5 (`up=54 s`, `71` live processes)** — missed by `analyze_nat108.py` because `launchd` elided `xpcproxy` and `ps -A` truncated `SpringBoard` to `SpringBoa`. `backboardd[18]` software-rendered twice (`230.581 s` and `231.110 s`, surfaces `2` & `4`, layers `0x0 -> 0x1`) with no swap `>= 5 s` later for `fb_diff` stats (`lsd[29]` burned `10.22 s` CPU / `241` denials; `71` processes on `cpus=1` delayed swaps ~`40 s`). Next: **NAT-110** (`host`, root-cause the `SpringBoard` swap stall / daemon bloat / `lsd` spam, fix the `ps -A` truncation bug in Stage C2 analyser, trim/tune Stage C2 image, and verify `make check` + mutants). Real iOS UI (stage 7) has no confirmed panel frame (`fb_diff > 0`) yet. Shortest path: [strategy/2026-11-12-ios-critical-path.md](strategy/2026-11-12-ios-critical-path.md), section 0j.
