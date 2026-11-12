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

Current position (2026-11-13, no percentage; updated after NAT-108): the project's XNU mounts the delivered 2.31 GiB APFS root from RAM (`md1`), runs Apple's `launchd` as PID 1, and in `NAT-107` (`loader-diag-xnu-sb2-md1`, decision 0040) verified **Stage B (`row B5 fb-swaps-no-diff`, `row H5 hb-ps-lists`, `row A1 base-daemons-alive`)** with `libhakios.dylib` injected into `backboardd` and `containermanagerd` and `3` `MiniIOMobileFramebuffer` swaps (`0` panel diff without `SpringBoard`). `NAT-108` (`host-test`, `pass`) has now built, verified (`12/12` tests, `623` mutants with `0` unexplained survivors), and drafted decision `0041` for the **Stage C1 + `hb`** image (`loader-diag-xnu-sc1-md1`): `423`-file `4 MiB` `md0` small root adding full donor `22 DARWIN_JOBS` + `382 --rest` on-demand `LaunchDaemons`/`LaunchAngels` (`405` plists), pinned prebuilt `libhakios.sb.dylib` (`0755`), 2-line `etc/inject.conf`, `8` `var/` preference plists (`0644`), fixed `zoneinfo`/`var.skel`, and boot-arg `fb_diff=1`. Next: **NAT-109** (`native`, single run of `loader-diag-xnu-sc1-md1` under decision `0041` using `analyze_nat108.py --mode stage-c` rows `C0`-`C7`) to test whether `SpringBoard` launches and produces `fb_diff > 0`. Real iOS UI (stage 7) has no visible frame evidence yet. Shortest path: [strategy/2026-11-12-ios-critical-path.md](strategy/2026-11-12-ios-critical-path.md), section 0i.
