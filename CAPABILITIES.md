# S24 hardware capabilities

> Generated from state/capabilities.json. Task completion counts are not hardware coverage.

Target: **SM-S921B/e1s/s5e9945**. First OS target: **iOS 16.5**.

Inventory describes running Android. Upstream claims and authored code are separate from this phone's native acceptance.

| Capability | Local implementation | Native on this S24 | Local Android observation | Upstream / next check | Tasks |
|---|---|---|---|---|---|
| Boot and recovery | host-tested | not-tested | Owner reports unlock; Android properties disagree; recovery untested | Exact port authored, no device boot / Supply full-kernel inputs and qualify actual BYH3 recovery; loader format pass is not a boot | [BLD-001](planning/tasks/BLD-001.md), [TST-001](planning/tasks/TST-001.md), [KRN-001](planning/tasks/KRN-001.md), [NAT-001](planning/tasks/NAT-001.md), [NAT-002](planning/tasks/NAT-002.md), [NAT-004](planning/tasks/NAT-004.md), [NAT-003](planning/tasks/NAT-003.md) |
| CPU, memory and interrupts | source-reviewed | not-tested | 10 cores; Android 4 KiB pages; reserved-memory properties unavailable | SMP code exists; S24 hardware execution untested / Compile full E1S kernel, then verify live reserved memory and CPUs under a native gate | [BLD-001](planning/tasks/BLD-001.md), [TST-001](planning/tasks/TST-001.md), [DRV-003](planning/tasks/DRV-003.md), [KRN-001](planning/tasks/KRN-001.md) |
| Isolated XNU guest | planned | not-tested | KVM configured; shell access and execution unverified | Scion reports Pixel AVF PID 1 / Assess accessible S24 VM interfaces | [VM-001](planning/tasks/VM-001.md), [VM-002](planning/tasks/VM-002.md), [VM-003](planning/tasks/VM-003.md) |
| Display and touch | planned | not-tested | 1080x2340; advertised refresh modes; sec_touchscreen 10 slots | S24 framebuffer/touch code untested / Validate presentation and HID contract | [UI-001](planning/tasks/UI-001.md), [UI-002](planning/tasks/UI-002.md), [DRV-001](planning/tasks/DRV-001.md) |
| Xclipse GPU and Metal | host-tested | not-tested | Xclipse 940; stock Vulkan 1.3.279; sgpu loaded | Pinned SGPU/RADV interface reviewed; host ownership oracle and compiled experimental transport; native backend/OS frontend missing / GPU-007 integrate actual XNU backing/VM/IRQ/winsys after KRN-001; TST-002 APK runtime and separately authorized GPU-003 remain independent | [GPU-001](planning/tasks/GPU-001.md), [GPU-002](planning/tasks/GPU-002.md), [GPU-003](planning/tasks/GPU-003.md), [GPU-004](planning/tasks/GPU-004.md), [GPU-005](planning/tasks/GPU-005.md), [GPU-006](planning/tasks/GPU-006.md), [GPU-007](planning/tasks/GPU-007.md), [GPU-008](planning/tasks/GPU-008.md), [GPU-009](planning/tasks/GPU-009.md), [GPU-010](planning/tasks/GPU-010.md), [TST-002](planning/tasks/TST-002.md), [RES-004](planning/tasks/RES-004.md), [GPU-011](planning/tasks/GPU-011.md) |
| Experimental storage and USB | planned | not-tested | Partition sizes known; no partition backup or XNU reads | S24 UFS/MCQ authored, untested / Host-only UFS and memory contract checks | [DRV-002](planning/tasks/DRV-002.md), [USB-001](planning/tasks/USB-001.md), [USB-002](planning/tasks/USB-002.md) |
| Wi-Fi | host-tested | not-tested | kiwi_v2/cnss2 loaded; endpoint ID unavailable | Pinned native ath12k candidate; owned host input/DMA boundary tested; actual Exynos backend, endpoint/firmware and iOS16.5 frontend unqualified / NET-004 actual Exynos/XNU backend build after KRN-001; verify endpoint/firmware and NET-005 iOS16.5 station ABI before native qualification | [NET-001](planning/tasks/NET-001.md), [NET-002](planning/tasks/NET-002.md), [NET-003](planning/tasks/NET-003.md), [NET-004](planning/tasks/NET-004.md), [NET-005](planning/tasks/NET-005.md), [RES-005](planning/tasks/RES-005.md) |
| Bluetooth | planned | not-tested | btpower loaded; exact transport not qualified | Board source available; no S24 XNU port / Identify controller and firmware transport | [BT-001](planning/tasks/BT-001.md), [BT-002](planning/tasks/BT-002.md) |
| Audio | planned | not-tested | ABOX/exynos9945_audio/CS35L43 modules loaded | Older Exynos audio donors differ / Specify ABOX IPC, PCM and codec path | [AUD-001](planning/tasks/AUD-001.md), [AUD-002](planning/tasks/AUD-002.md) |
| Cameras | planned | not-tested | Android camera features; no native capture | S24 ID/presence probe only / Separate CSIS/DMA and ISP requirements | [CAM-001](planning/tasks/CAM-001.md), [CAM-002](planning/tasks/CAM-002.md) |
| Power, thermal and sleep | planned | not-tested | Battery/thermal snapshot and CPU policies captured | S24 read-only PMIC/gauge code; no native DVFS acceptance / Review exact tables and suspend requirements | [PWR-001](planning/tasks/PWR-001.md), [PWR-002](planning/tasks/PWR-002.md) |
| Sensors and GNSS | planned | not-tested | Android sensor identities captured; native hub unknown | BSP interfaces available / Specify hub/GNSS transport and timestamp handling | [SEN-001](planning/tasks/SEN-001.md), [SEN-002](planning/tasks/SEN-002.md) |
| Modem, SIM, data and voice | source-reviewed | not-tested | CPIF/S5000AP/shared memory; SBD and RX/UL PKTPROC configured; DIT disabled; live protocol unknown | Pinned Qualcomm iOS17 donor models pass on host; Samsung wire headers reviewed, vendor commands missing / CELL-009: matching offline RIL schemas; verify live protocol/queue profile before native transport | [CELL-001](planning/tasks/CELL-001.md), [CELL-002](planning/tasks/CELL-002.md), [CELL-003](planning/tasks/CELL-003.md), [CELL-004](planning/tasks/CELL-004.md), [CELL-005](planning/tasks/CELL-005.md), [CELL-006](planning/tasks/CELL-006.md), [CELL-009](planning/tasks/CELL-009.md) |
| eSIM | source-reviewed | not-tested | Android declares eUICC/MEP; no APDU/provisioning test | Pinned lpac/APDU architecture; iOS17 donor provisioning unverified; iPhone X frontend gap / ESIM-004: verify selected iOS16.5 frontend/profile; exact native logical-channel transport remains missing | [ESIM-001](planning/tasks/ESIM-001.md), [ESIM-002](planning/tasks/ESIM-002.md), [ESIM-003](planning/tasks/ESIM-003.md), [ESIM-004](planning/tasks/ESIM-004.md) |
| Other peripherals | planned | not-tested | Android reports NFC/fingerprint; native untested | No equivalent Apple security established / Inventory individual hardware and define native tests | [MISC-001](planning/tasks/MISC-001.md) |

## Native acceptance

- **Boot and recovery:** Real XNU entry and verified return to daily Android
- **CPU, memory and interrupts:** All claimed CPUs, timers, IRQ/xcall and stable memory
- **Isolated XNU guest:** Guest starts and stops; this does not qualify native peripherals
- **Display and touch:** Correct native pixels, touch, brightness and scanout
- **Xclipse GPU and Metal:** Native multiprocess Metal/CoreAnimation, correct pixels and cleanup
- **Experimental storage and USB:** Verified read-only root/overlay with Android data preserved
- **Wi-Fi:** WPA2/WPA3, DHCP/DNS/HTTPS, iOS controls and reconnect
- **Bluetooth:** Pairing, BLE and every claimed profile
- **Audio:** Speaker, microphone, OS routing and duplex
- **Cameras:** Real frames for every claimed sensor and OS integration
- **Power, thermal and sleep:** Thermal limits, DVFS, idle, sleep/wake and charging
- **Sensors and GNSS:** Correct native services for each claimed sensor and GNSS
- **Modem, SIM, data and voice:** Registration, IPv4/IPv6, SMS, IMS and duplex incoming/outgoing calls
- **eSIM:** Active-profile use and each LPA lifecycle operation qualified
- **Other peripherals:** Haptics/NFC/biometrics/codecs/external display individually qualified

Apple services and iPhone-equivalent hardware security are separate research outcomes, with no promised compatibility.

[Implementation sequence](docs/implementation.md) · [Kanban](BOARD.md)
