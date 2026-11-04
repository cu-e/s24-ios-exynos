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
