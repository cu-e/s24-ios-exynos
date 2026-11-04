# S24 iOS / Exynos — Kanban

> Generated from state/lab.json. Use the CLI; do not edit this board or its task cards.

Phase: **device baseline captured; Android-preserving research**. Snapshot: 2026-11-04T23:34:46+00:00.

Registry SHA256: `85059b60226f660121f3da748087717a3c7e2496965cc70f2d98c11dd1bed3e3`. Run `python3 tools/lab.py board --check` to detect stale files.

[Workflow](docs/planning.md) · [All task details](planning/README.md) · [Machine view](state/board.json) · [Status](STATUS.md)

| Ready (11) | In progress (0) | Blocked (2) | Waiting (11) | Needs authorization (23) | Done (15) |
| --- | --- | --- | --- | --- | --- |
| [**TST-002**](planning/tasks/TST-002.md) · P80<br>Qualify the current Android probe on a functioning isolated emulator<br>host · unassigned | — | [**KRN-001**](planning/tasks/KRN-001.md) · P85<br>Build the full E1S XNU kernel with supplied SDK and pinned dependencies<br>host · codex-implementation-20261105<br>No explicit iPhoneOS16.5 SDK or matching pinned XNU dependency/build tool directory is configured; see fixtures/public/build/kernel-preflight.json | [**GPU-007**](planning/tasks/GPU-007.md) · P70<br>Implement and build the Xclipse native kernel backend<br>host · unassigned<br>Dependencies: GPU-006, KRN-001 | [**GPU-003**](planning/tasks/GPU-003.md) · P50<br>Measure stock Vulkan on the S24 inside Android<br>android-app · unassigned<br>Scope not authorized: android-app; Paths reserved by: NAT-001 | [**PLN-001**](planning/tasks/PLN-001.md) · P90<br>Implement the staged hardware roadmap and evidence-backed capability matrix<br>host · codex-implementation-20261105 |
| [**VM-002**](planning/tasks/VM-002.md) · P70<br>Build a pinned minimal XNU guest and host launch harness<br>host · unassigned | — | [**NAT-001**](planning/tasks/NAT-001.md) · P50<br>Prepare a verifiable recovery plan for this exact S24<br>host · codex-implementation-20261105<br>Exact S921BXXS9BYH3 stock images, dated/hash-verified backups and Download Mode/recovery observations are unavailable; no restoration can be qualified | [**GPU-009**](planning/tasks/GPU-009.md) · P70<br>Implement the iOS 16.5 Metal frontend and RADV Darwin winsys<br>host · unassigned<br>Dependencies: GPU-007 | [**GPU-005**](planning/tasks/GPU-005.md) · P50<br>Compare the stock driver and Xclipse RADV in the test APK<br>android-app · unassigned<br>Scope not authorized: android-app; Dependencies: GPU-003 | [**SRC-001**](planning/tasks/SRC-001.md) · P90<br>Implement pinned source checkout and provenance verification<br>host · codex-implementation-20261105 |
| [**UI-001**](planning/tasks/UI-001.md) · P70<br>Implement host-testable display and HID contracts for iOS 16.5<br>host · unassigned | — | — | [**AUD-001**](planning/tasks/AUD-001.md) · P70<br>Specify and build ABOX PCM and CS35L43 audio adapters<br>host · unassigned<br>Dependencies: KRN-001 | [**NAT-003**](planning/tasks/NAT-003.md) · P50<br>Run the first native BOOT session with logs and recovery<br>native · unassigned<br>Scope not authorized: native; Dependencies: NAT-002, NAT-004, KRN-001; Paths reserved by: NAT-001, KRN-001 | [**INT-001**](planning/tasks/INT-001.md) · P90<br>Integrate and verify the first working host research lab<br>host · codex-implementation-20261105 |
| [**USB-001**](planning/tasks/USB-001.md) · P70<br>Implement host-buildable native USB and block-transport adapters<br>host · unassigned | — | — | [**CAM-001**](planning/tasks/CAM-001.md) · P70<br>Specify and build a bounded native camera frame path<br>host · unassigned<br>Dependencies: KRN-001 | [**DRV-003**](planning/tasks/DRV-003.md) · P50<br>Validate minimal XNU drivers on hardware<br>native · unassigned<br>Scope not authorized: native; Dependencies: NAT-003, DRV-001, DRV-002 | [**LAB-001**](planning/tasks/LAB-001.md) · P80<br>Implement a file-based Kanban and agent coordination workflow<br>host · codex-coordination |
| [**GPU-006**](planning/tasks/GPU-006.md) · P70<br>Specify the Xclipse Darwin memory and submission interface<br>host · unassigned | — | — | [**PWR-001**](planning/tasks/PWR-001.md) · P70<br>Specify and build native thermal, clocks and power policy<br>host · unassigned<br>Dependencies: KRN-001 | [**VM-003**](planning/tasks/VM-003.md) · P50<br>Measure an isolated XNU guest on the S24<br>android-app · unassigned<br>Scope not authorized: android-app; Dependencies: VM-001, VM-002 | [**FND-001**](planning/tasks/FND-001.md) · P50<br>Prepare and verify the project foundation<br>host · codex |
| [**NET-001**](planning/tasks/NET-001.md) · P70<br>Specify and build the E1S KIWI Wi-Fi platform adapter<br>host · unassigned | — | — | [**CELL-002**](planning/tasks/CELL-002.md) · P70<br>Implement host-buildable Samsung CP startup and control<br>host · unassigned<br>Dependencies: CELL-001, KRN-001 | [**NAT-004**](planning/tasks/NAT-004.md) · P50<br>Qualify the concrete stock recovery path on the S24<br>native · unassigned<br>Scope not authorized: native; Dependencies: NAT-002 | [**RES-001**](planning/tasks/RES-001.md) · P50<br>Pin S24 upstream and document donor provenance<br>host · codex-implementation-20261105 |
| [**BT-001**](planning/tasks/BT-001.md) · P70<br>Specify and build the exact E1S Bluetooth transport<br>host · unassigned | — | — | [**CELL-004**](planning/tasks/CELL-004.md) · P70<br>Implement packet data and iOS telephony service adapters<br>host · unassigned<br>Dependencies: CELL-001, KRN-001 | [**UI-002**](planning/tasks/UI-002.md) · P50<br>Measure native framebuffer, touch and Apple iOS userland<br>native · unassigned<br>Scope not authorized: native; Dependencies: DRV-003, UI-001 | [**DEV-001**](planning/tasks/DEV-001.md) · P50<br>Collect sanitized read-only S24 inventory<br>android-readonly · codex |
| [**SEN-001**](planning/tasks/SEN-001.md) · P70<br>Specify sensor-hub and GNSS transport adapters<br>host · unassigned | — | — | [**ESIM-001**](planning/tasks/ESIM-001.md) · P70<br>Specify eUICC logical channels and LPA integration<br>host · unassigned<br>Dependencies: CELL-001 | [**USB-002**](planning/tasks/USB-002.md) · P50<br>Qualify native USB logs and host-backed read-only root<br>native · unassigned<br>Scope not authorized: native; Dependencies: DRV-003, USB-001 | [**RES-002**](planning/tasks/RES-002.md) · P50<br>Cross-check the e1s hardware map against primary sources<br>host · codex-implementation-20261105 |
| [**CELL-001**](planning/tasks/CELL-001.md) · P70<br>Specify Samsung CPIF control and packet transports<br>host · unassigned | — | — | [**DRV-001**](planning/tasks/DRV-001.md) · P50<br>Prepare an STM SPI touch driver and host adapter<br>host · unassigned<br>Paths reserved by: KRN-001 | [**GPU-008**](planning/tasks/GPU-008.md) · P50<br>Measure native Xclipse clear, copy and triangle<br>native · unassigned<br>Scope not authorized: native; Dependencies: GPU-007, DRV-003 | [**BLD-001**](planning/tasks/BLD-001.md) · P50<br>Make the host loader and E1S delta build reproducible<br>host · codex-implementation-20261105 |
| [**MISC-001**](planning/tasks/MISC-001.md) · P70<br>Specify haptics, NFC, biometrics, video and external display gaps<br>host · unassigned | — | — | [**DRV-002**](planning/tasks/DRV-002.md) · P50<br>Validate the read-only UFS/MCQ contract on the host<br>host · unassigned<br>Paths reserved by: KRN-001 | [**GPU-010**](planning/tasks/GPU-010.md) · P50<br>Qualify multiprocess native Metal and CoreAnimation<br>native · unassigned<br>Scope not authorized: native; Dependencies: GPU-008, GPU-009, UI-002 | [**TST-001**](planning/tasks/TST-001.md) · P50<br>Validate the boot package, ADT and memory boundaries on the host<br>host · codex-implementation-20261105 |
| [**VM-001**](planning/tasks/VM-001.md) · P50<br>Assess S24 virtualization interfaces without changing device policy<br>android-readonly · unassigned | — | — | [**NAT-002**](planning/tasks/NAT-002.md) · P50<br>Design control and return paths for a native test<br>host · unassigned<br>Dependencies: NAT-001; Paths reserved by: NAT-001, KRN-001 | [**NET-002**](planning/tasks/NET-002.md) · P50<br>Measure native Wi-Fi scan, WPA2 and Internet<br>native · unassigned<br>Scope not authorized: native; Dependencies: NET-001, DRV-003 | [**GPU-001**](planning/tasks/GPU-001.md) · P50<br>Design an Android app for GUI/GPU measurements<br>host · codex-implementation-20261105 |
| — | — | — | — | [**NET-003**](planning/tasks/NET-003.md) · P50<br>Qualify native Wi-Fi security and lifecycle integration<br>native · unassigned<br>Scope not authorized: native; Dependencies: NET-002, UI-002 | [**GPU-002**](planning/tasks/GPU-002.md) · P50<br>Implement a minimal Android Vulkan probe<br>host · codex-implementation-20261105 |
| — | — | — | — | [**BT-002**](planning/tasks/BT-002.md) · P50<br>Qualify native Bluetooth pairing and BLE<br>native · unassigned<br>Scope not authorized: native; Dependencies: BT-001, DRV-003 | [**GPU-004**](planning/tasks/GPU-004.md) · P50<br>Validate a minimal Metal-to-Vulkan path on the host<br>host · codex-implementation-20261105 |
| — | — | — | — | [**AUD-002**](planning/tasks/AUD-002.md) · P50<br>Measure native speaker, microphone and iOS routing<br>native · unassigned<br>Scope not authorized: native; Dependencies: AUD-001, DRV-003 | [**DEV-002**](planning/tasks/DEV-002.md) · P50<br>Prepare an extended read-only technical profile collector<br>host · codex |
| — | — | — | — | [**CAM-002**](planning/tasks/CAM-002.md) · P50<br>Qualify native cameras and OS integration<br>native · unassigned<br>Scope not authorized: native; Dependencies: CAM-001, DRV-003 | [**DOC-001**](planning/tasks/DOC-001.md) · P50<br>Make English the project and agent working language<br>host · codex |
| — | — | — | — | [**PWR-002**](planning/tasks/PWR-002.md) · P50<br>Qualify native thermal, idle, sleep and charging behavior<br>native · unassigned<br>Scope not authorized: native; Dependencies: PWR-001, DRV-003 | — |
| — | — | — | — | [**SEN-002**](planning/tasks/SEN-002.md) · P50<br>Qualify native sensors and GNSS services<br>native · unassigned<br>Scope not authorized: native; Dependencies: SEN-001, DRV-003 | — |
| — | — | — | — | [**CELL-003**](planning/tasks/CELL-003.md) · P50<br>Qualify native CP startup, SIM and registration<br>native · unassigned<br>Scope not authorized: native; Dependencies: CELL-002, DRV-003 | — |
| — | — | — | — | [**CELL-005**](planning/tasks/CELL-005.md) · P50<br>Qualify native mobile data, IPv6 and reconnect<br>native · unassigned<br>Scope not authorized: native; Dependencies: CELL-003, CELL-004 | — |
| — | — | — | — | [**CELL-006**](planning/tasks/CELL-006.md) · P50<br>Qualify SMS, IMS and bidirectional voice calls<br>native · unassigned<br>Scope not authorized: native; Dependencies: CELL-005, AUD-002 | — |
| — | — | — | — | [**ESIM-002**](planning/tasks/ESIM-002.md) · P50<br>Qualify an already-active test eSIM profile<br>native · unassigned<br>Scope not authorized: native; Dependencies: ESIM-001, CELL-003 | — |
| — | — | — | — | [**ESIM-003**](planning/tasks/ESIM-003.md) · P50<br>Implement and qualify test eSIM profile lifecycle<br>native · unassigned<br>Scope not authorized: native; Dependencies: ESIM-002, CELL-005 | — |
| — | — | — | — | [**QUAL-001**](planning/tasks/QUAL-001.md) · P50<br>Run full-system native stability qualification<br>native · unassigned<br>Scope not authorized: native; Dependencies: GPU-010, NET-003, BT-002, AUD-002, CAM-002, PWR-002, SEN-002, CELL-006, ESIM-003 | — |

## Claimed work and agent reports

Owner names identify cooperating agents, not authenticated processes. A recent report is not proof that an agent is running. Reports older than 30 minutes are marked stale at snapshot time; claims never expire automatically.

| Owner | Task | State | Last heartbeat (UTC) | Report | Progress / next step | Context |
|---|---|---|---|---|---|---|
| codex-implementation-20261105 | KRN-001 | blocked | 2026-11-04T23:25:13+00:00 | recent | Exact XNU patch preparation passes; full kernel not compiled because SDK/build-tool inputs are unconfigured / Provide and verify explicit iPhoneOS16.5 SDK and pinned dependency-tool paths, then resume this claim | branch: main; handoff: research/notes/implementation-handoff.md |
| codex-implementation-20261105 | NAT-001 | blocked | 2026-11-04T23:25:13+00:00 | recent | Recovery template records unavailable matching BYH3 images, hashed backups and measured restore; no phone operation performed / Establish matching local image/backup provenance and separately scoped recovery qualification | branch: main; handoff: research/notes/implementation-handoff.md |

## Recent activity

- 2026-11-04T23:16:19+00:00 · codex-implementation-20261105 · task.add:INT-001
  - INT-001: pending
- 2026-11-04T23:16:20+00:00 · codex-implementation-20261105 · task.claim:INT-001
  - INT-001: in_progress
- 2026-11-04T23:19:43+00:00 · codex-implementation-20261105 · experiment.record:EMULATOR-004
- 2026-11-04T23:19:43+00:00 · codex-implementation-20261105 · experiment.plan:EMULATOR-005
- 2026-11-04T23:20:20+00:00 · codex-implementation-20261105 · experiment.record:METAL-001
- 2026-11-04T23:20:21+00:00 · codex-implementation-20261105 · experiment.record:BOOTCHECK-001
- 2026-11-04T23:20:21+00:00 · codex-implementation-20261105 · experiment.record:VULKANHOST-001
- 2026-11-04T23:20:22+00:00 · codex-implementation-20261105 · task.done:GPU-004
  - GPU-004: Pinned translator compiled with Rust 1.98.1; owned AIR fixture translated and initial host compute returned exact marker with guard words intact
- 2026-11-04T23:20:22+00:00 · codex-implementation-20261105 · task.done:TST-001
  - TST-001: done
- 2026-11-04T23:22:51+00:00 · codex-implementation-20261105 · experiment.record:EMULATOR-005
- 2026-11-04T23:22:52+00:00 · codex-implementation-20261105 · experiment.plan:EMULATOR-006
- 2026-11-04T23:23:32+00:00 · codex-implementation-20261105 · task.update:INT-001
  - INT-001: 62 full checks passed; graphics translation, exact native-core host readback and boot validation recorded; integrating actual capabilities and missing kernel/recovery inputs
- 2026-11-04T23:25:13+00:00 · codex-implementation-20261105 · task.update:KRN-001
  - KRN-001: Exact XNU patch preparation passes; full kernel not compiled because SDK/build-tool inputs are unconfigured
- 2026-11-04T23:25:13+00:00 · codex-implementation-20261105 · task.update:NAT-001
  - NAT-001: Recovery template records unavailable matching BYH3 images, hashed backups and measured restore; no phone operation performed
- 2026-11-04T23:26:05+00:00 · codex-implementation-20261105 · experiment.record:EMULATOR-006
- 2026-11-04T23:26:06+00:00 · codex-implementation-20261105 · experiment.plan:EMULATOR-007
- 2026-11-04T23:31:02+00:00 · codex-implementation-20261105 · experiment.record:EMULATOR-007
- 2026-11-04T23:31:52+00:00 · codex-implementation-20261105 · task.add:TST-002
  - TST-002: pending
- 2026-11-04T23:33:23+00:00 · codex-implementation-20261105 · task.done:GPU-002
  - GPU-002: ARM64/x86_64 APK built and signed; host Vulkan exact-pixel, pre-submit cancellation and injected fence-timeout checks passed; isolated emulator now authorized
- 2026-11-04T23:34:25+00:00 · codex-implementation-20261105 · task.done:INT-001
  - INT-001: 62 full checks passed; graphics translation, exact native-core host readback and boot validation recorded; integrating actual capabilities and missing kernel/recovery inputs

Use a unique owner per agent session. Atomically take ready work:

```sh
python3 tools/lab.py task claim-next --owner agent-your-session --scope host
```
