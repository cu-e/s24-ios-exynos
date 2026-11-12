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

Current position (2026-11-13, no percentage; updated after NAT-107): the project's XNU mounts the delivered 2.31 GiB APFS root from RAM (`md1`), runs Apple's `launchd` as PID 1, and in `NAT-107` (`loader-diag-xnu-sb2-md1`, decision 0040) returned the complete `149,450`-byte `why=2` dump (`gap=0`, `hole=0`, `drops=0`, `1,754` contiguous records), verifying **Stage B (`row B5 fb-swaps-no-diff`, `row H5 hb-ps-lists`, `row A1 base-daemons-alive`)**: `init` injected donor `libhakios.dylib` into `/usr/libexec/backboardd` (`pid 14`) and `containermanagerd` (`pid 15`), all 8 self-starting Apple jobs (`13` alive total, `18` processes at `hb` round 6) stayed alive cleanly, `MiniIOSurface` created two `1125x2436 'BGRA'` surfaces (`1` and `3`), and `MiniIOMobileFramebuffer` processed `3` swaps (`0` panel pixel diff because `SpringBoard`/UI clients are absent in Stage B). Next: **Stage C (`SpringBoard` + required services + framebuffer/scan-out visibility)**. Real iOS UI (stage 7) has no visible frame evidence yet. Shortest path: [strategy/2026-11-12-ios-critical-path.md](strategy/2026-11-12-ios-critical-path.md), section 0h.
