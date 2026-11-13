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

Current position (2026-11-13, no percentage; updated after NAT-113): the project's XNU mounts the delivered 2.31 GiB APFS root from RAM (`md1`) and runs Apple's `launchd`, `backboardd` and `SpringBoard` on `SM-S921B/e1s`. In **NAT-113** (`loader-diag-xnu-sc3-md1`, decision 0043, native-device pass) `backboardd` swapped three software-rendered frames (kernel time 229.03-229.18 s) and the loader, at the kernel's own return, read **27,517 non-black pixels forming the Apple boot logo** from the panel memory the display scans (`0xfa200000`); the kernel's recording of the swapped surfaces matches that count. Stock RECOVERY was restored and Android verified.

Established: first iOS frame in the scanned panel memory (software rendering, CoreAnimation on the CPU). Not established: that the panel lit it (nobody looked); any frame after the logo (none in the last ~21 s of the 63 s window); the lock screen; touch; any GPU acceleration; any frame rate. That more time alone reaches the lock screen is a **hypothesis**. Done on the host since: KRN-044 (rebuild loop for the running kernel), NAT-071 (kernel-side watchdog feed, window beyond 63 s), NAT-115 (post-logo hypotheses H1-H4 and the image `loader-diag-xnu-sc4-md1` that separates them). Next: NAT-116, one native run of that image, which needs its own owner decision. Stage 7 is not reached. Section 0k of [strategy/2026-11-12-ios-critical-path.md](strategy/2026-11-12-ios-critical-path.md) has the details; the GPU chain is in [research/notes/GPU-chain-2026-11-13.md](../research/notes/GPU-chain-2026-11-13.md).
