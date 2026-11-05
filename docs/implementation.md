# iOS 16.5 on S24 Exynos: implementation contract

Approved direction: iOS 16 first; preserve daily Android; perform isolated Android experiments before separately authorized native work. Hardware support is the primary objective. Apple services and iPhone-equivalent security are separate research outcomes. Carrier and test subscription are not selected. No purchase, profile change, root request or native run is implied.

The target is SM-S921B/e1s/s5e9945 on S921BXXS9BYH3. The matching upstream targets iPhone X iOS 16.5 / XNU 8796.121.2. A roadmap is not a guarantee that undocumented hardware, closed interfaces or service dependencies can be implemented. A failed gate retains evidence and blocks that branch; independent host work continues.

## Execution environments

| Environment | Entry and hardware owner | Acceptance category |
|---|---|---|
| Host | Explicit pinned source checkout, isolated build, fixtures and protocol models | source-review / host-test |
| Android | Separate app process, Android Vulkan/network/audio services | android-userland; does not establish native compatibility |
| VM | An actually available AVF/KVM interface; Android owns physical hardware | Guest execution; not an Exynos peripheral model |
| Native | Stock boot chain → reviewed loader → XNU → experimental root | native-device; requires recovery and explicit hardware scope |

Un1box/touchHLE target older systems or apps and are optional demonstrations. libhybris assumes a Linux kernel and does not make Android libraries work on XNU. DSU starts an Android GSI, not an arbitrary XNU kernel. No such option substitutes for native driver acceptance.

## Stage A: sources, map and reproducible builds

RES-001 pins the exact S24 source and selected donor documentation. Preserve its embedded HakiOS base d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c; do not replace it with current HakiOS wholesale. RES-002 compares the upstream Android 15/S8 BSP f85e53cfa5497ead5d78821efbac84e51f37a4e1 with actual S9 observations. Mainline BSP snapshots are comparison inputs, not verified firmware matches.

BLD-001 builds the freestanding probe and XNU handoff loader; it must separately report full kernel readiness. TST-001 validates boot headers, ADT/FDT and memory bounds. The upstream check_all_exports failure is a build failure, even when a linked kernel exists. SDK/toolchain absence is an explicit dependency, never an excuse to claim a build.

[RES-008 input analysis](../research/notes/RES-008-xnu-build-inputs.md) distinguishes the selected iOS16.5 runtime from SDK metadata: Apple SDK16.4 and the reviewed Theos16.5 directory are compatible labels in the documented app toolchain, not proof of private/kernel ABI. Use the [component inventory](procedures/xnu-build-inputs.md) instead of treating literal Version16.5 as sufficient or necessary. KRN-002 now supplies [genuine source-built generators and real ld64/TAPI host inputs](../research/notes/KRN-002-host-tools.md), including actual static Mach-O and symbol/text-stub checks; KRN-003 audits the E1S dependency board/compiler profile and generated archives. The original KRN-001 owner retains full-kernel build acceptance.

Source fetch is explicit, SHA-pinned, does not run upstream scripts and does not recurse into submodules. Sources stay in references/. Builds run in artifacts/ copies so reviewed checkouts remain unchanged. Apple userland, SDKs, firmware and private device data are external local inputs, excluded from Git.

## Stage B: bounded experiments while Android runs

GPU-001/002/004 prepare a native Vulkan probe APK, owned fixtures and Metal/AIR translation tests. GPU-003 measures the stock driver after app scope authorization. GPU-005 compares app-local RADV only after the stock baseline and a reviewed custom-driver loading path.

[TST-002 guest evidence](../research/notes/TST-002-runtime-qualification.md) now records exact APK7 readback and16 runtime/error/lifecycle/export cases in an owned API36/SwiftShader emulator. It improves app qualification before GPU-003, not S24 GPU support. The physical phone is Android15; ARM64 JNI, physical-driver behavior and measured phone recovery remain separate. Atomic report commit is verified by reading stored bytes, while power-loss durability is not claimed. Restart UI is a controlled gate-state test, not an induced GPU hang. Use the private filtered ADB launcher for future host guests; never inherit a donor's broad device selection or shared-server reset.

Start with one worker, at most 128 MiB experimental GPU resources, five-second runs, bounded fence waits and a host deadline. Stop requests prevent new submissions. Do not destroy in-use GPU resources as a cancellation shortcut. A blocked kernel driver can outlive a stopped app: process cancellation does not guarantee phone recovery. Stop new runs on DEVICE_LOST.

VM-001 inventories availability using already-authorized read-only access. VM-002 prepares a pinned guest on the host. VM-003 tests the guest only after an accessible interface and appropriate device scope. CONFIG_KVM, an existing device node or ARM64 alone is insufficient. No automatic SELinux, root or kernel changes.

The reviewed Scion AVF launcher grants VM permissions and changes hidden-API exemptions before attempting restoration. It is not VM-001 read-only inventory and must not be run as a shortcut around the device gate. Its Pixel PID 1/SMP result is not S24 guest or full iOS acceptance. See [the donor follow-up](../research/notes/RES-003-radio-donors.md).

A future launcher must require an explicit target, record original individual grants/settings and verify their exact restoration. An EXIT trap or unconditional permission revocation does not prove that the previous Android state was restored.

## Stage C: recovery and native control

NAT-001 prepares matching stock images, hashes, backups, host recovery requirements and exact return steps. NAT-002 designs the actual control channel, loss-of-link behavior and manual fallback. A verified restoration is a separately gated native task; documenting it does not establish it. NAT-003 cannot run until that evidence exists and a concrete image/session has separate authorization.

No usable kexec path is established: the captured kernel disables it. No fastboot boot support is established on this Samsung. Mu-Silicium e1s lacks working USB/storage in its published status. Do not promise an autonomous loop or automatic return without testing the independent control path. Backup, Android bootability and user-data preservation are distinct acceptance properties.

## Stage D: minimal native XNU

First: loader entry, early XNU markers, MMU, timer/IRQ, scheduler, RAM root and owned static PID 1, one CPU. Then measure SMP, per-CPU timers/xcall, coherency and the 4+3+2+1 topology. Verify live reserved memory and page-size assumptions before DMA. No inherited address becomes a measured fact because it appears in a source header.

The upstream stage0 /sbin/launchd is an owned test Mach-O. It does not establish Apple launchd, backboardd or SpringBoard. Capture real device logs, not simulated preview screens. Default storage writes remain disabled.

## Stage E: display, input and real iOS userland

Validate framebuffer pixels and touch/HID first, then dyld/shared-cache compatibility, launchd, backboardd, SpringBoard and Settings on the selected iPhone X 16.5 profile. Separate panel scanout, VSYNC, brightness and power from GPU rendering. Start at 60 Hz.

The [display/input audit](../research/notes/RES-007-display-input.md) identifies a reproducible STM X/Y low-nibble bug in the pinned E1S driver; [UI-006](../patches/display-input/README.md) corrects two lines during isolated source preparation and tests the actual extracted decoder. UI-001 supplies [compiled layout/coordinate and proposed input-state contracts](../src/platform/display/README.md). They neither map pixels nor dispatch HID. The donor's boot framebuffer copy, timer VSYNC, unfinished-GPU timeout fallback and success-only power/cancel replies do not establish native display support.

UI-003 must implement actual E1S DECON/DPP/DSIM/panel power, DSC, cache/SysMMU and TE/frame-retirement ownership. The retail 60 Hz panel mode already enables DSC; this is distinct from deferred GPU image-compression tuning. UI-004 implements the actual STM SPI9/IRQ/firmware/power lifecycle after the bounded protocol adapter DRV-001 and source correction. UI-005 implements the selected iOS16.5 surface/framebuffer/HID bridge, authenticated allocation/input access, timebase conversion, loss/cancellation/restart and consistent physical/logical transforms. Selectively review newer donor bounds fixes instead of treating a newer repository as proof the old embedded pin is fixed. UI-002 native pixels/input/Apple-process acceptance now requires all three implementations; no host model or patch application substitutes for it.

Minimal tests use RAM root. Real userland uses a separate read-only image and experimental writable overlay. Measure memory budget before loading; if it cannot fit with kernel/GPU headroom, implement and verify native USB plus host-backed block transport before proceeding. Do not repurpose Android USERDATA, EFS, super or modem partitions. Internal persistent storage is a separate future decision and authorization.

## Stage F: Xclipse native graphics

```text
CoreAnimation / apps → Metal frontend for the selected OS ABI
 → metal2vulkan → RADV Xclipse → Darwin winsys / kernel backend
 → firmware + GPUVM + command queues + IRQ + power
 → IOSurface sharing → DECON/DSIM scanout
```

GPU-006 specifies ownership and operations for alloc/free, map/unmap, submit, fence completion/error, cache synchronization and fault teardown. GPU-007 implements the host-buildable native backend. GPU-008 is the first native clear/copy/triangle acceptance. GPU-009 adapts Metal registration, ABI and IOSurface ownership; GPU-010 measures multiprocess CoreAnimation and presentation.

The [GPU-006 contract](../src/graphics/contracts/README.md) has a synthetic ownership oracle, with 4/16 KiB CPU backing, 4 KiB GPU ranges, shared-budget checks and reference retention after Stop/timeout/fault. The [GPU-011 transport](../src/platform/gpu/abi/README.md) now supplies pointer-free version 1.0 messages, a compiled C validator and an explicitly synthetic peer. Host sanitizer checks and compile-only AArch64 ELF/arm64 Mach-O objects pass independently of the missing Apple SDK. GPU-007 must still integrate it with the selected XNU and implement authenticated clients, actual cache/TLB maintenance, firmware/power/IRQ and validated queue ownership. Mock completion/quiescence inputs must never become client-controlled retirement assertions; the wire protocol provides no such client operation.

The [pinned interface audit](../research/notes/RES-004-xclipse-interfaces.md) identifies power-sensitive MMR queries, an unbounded RADV VM-update wait and a memory guard that can fall back to process-local accounting. CPU hardware granule and advertised XNU VM page size differ in the source policy and depend on build flags plus loader memory size. Verify both in the compiled/runtime profile. Account separately for constrained memory pools and imported/presented surfaces; an aggregate RAM limit or low CmaFree alone does not establish safe allocation behavior.

Android RADV and a shader translator are not sufficient by themselves. Review per-file licenses and provenance before incorporating donor code. Turnip/Panfrost examples have different hardware command streams. Defer 120 Hz, compression tuning and ray tracing until correct pixels, cleanup, concurrency and thermal behavior pass.

## Stage G: peripherals and power

| Subsystem | Ordered acceptance |
|---|---|
| Wi-Fi | Actual PCI ID/revision and board data → Exynos PCIe/DMA/IRQ → firmware → scan → WPA2 → DHCP/DNS/HTTPS → iOS integration → WPA3/reconnect |
| Bluetooth | E1S provenance/host framing → verified controller/ROM and native UART/power/firmware → selected iOS16.5 frontend → secure BR/EDR/LE pairing/BLE → audio/coexistence |
| Audio | ABOX firmware/IPC → PCM → codec/amplifier → speaker → microphone → OS routing → call duplex |
| Cameras | Sensor identity → rails/MCLK → CSIS/DMA frame → ISP → OS camera integration |
| Sensors/GNSS | Hub transport and timestamps → readings → OS services |
| Power | Battery/RTC → thermal limits → DVFS → idle → suspend/wake → charging policy |

The [Wi-Fi donor audit](../research/notes/RES-005-wifi-donors.md) identifies current Ath12kWifi as a conditional native-stack candidate and retains its older catalog pin separately. Its callback/event ABI changed; current documentation cannot validate an old binary/header pair. [NET-001](../src/platform/wifi/README.md) now compiles a structural-input/callback and checked DMA-range boundary, with live endpoint/firmware/profile fields still unknown. It performs no hardware operation.

NET-004 must implement and link the real Exynos PCIe/power/PHY/SysMMU/cache/MSI backend with one matched donor runtime before NET-002 hardware tests. NET-005 must compile the selected iOS16.5 station frontend before NET-003 OS/security/lifecycle qualification. Do not inherit sheng's rails, SPI 141, 128 MiB arena, no-op cache callback, firmware hashes or OS27 association layouts. The exact endpoint, chip revision, matching local firmware/board/regulatory data and actual DMA/IRQ behavior remain explicit gates. Basic upstream WPA2 reports do not establish WPA3, enterprise, privacy, roaming or sleep/wake acceptance.
The [Bluetooth donor review](../research/notes/RES-006-bluetooth-donors.md) corroborates UART1/11040000.uart and wake routing against an old Android IRQ capture, while retaining unknown ROM/board/firmware/baud/IBS inputs. [BT-001](../src/platform/bluetooth/README.md) supplies only bounded host H4 and exclusive initialization-command models. Credits/raw errors, timeout quarantine and Stop do not establish UART drain, power-off or pairing. Some donors fabricate vendor success to advance daemon initialization; do not inherit those capability claims.

BT-003 implements actual Samsung UART/clocks/pins/IRQ or DMA, shared rail/wake ownership and controller-versioned patch/NVM initialization, linked against selected XNU. BT-004 separately recovers and implements the selected iOS16.5 control-socket/registry/BlueTool contract; donor 16.7.16 instruction offsets or Skywalk endpoint layouts are not validated 16.5 interfaces. BT-002 native discovery, secure bonds and BLE qualification requires both implementations. BT-005 further gates final acceptance on actual A2DP/AVRCP/HFP, audio routing, reconnect/sleep and Wi-Fi coexistence. Existing daily Android bonds and credentials are not test fixtures.

Other subsystems: haptics, USB-C/PD, NFC, biometrics, video codecs and external display each require separate work and evidence.

Local Android modules indicate KIWI V2/CNSS for Wi-Fi and CS35L43/ABOX for sound. Do not silently select Broadcom or copy S9/S20 register values. A camera ID is not a frame; battery readings are not charging control; Samsung biometrics are not Apple Secure Enclave.

## Stage H: Samsung modem and telephony

CELL-001 specifies the actual CPIF/shared-memory transport using the captured S5000AP configuration. The hardware path is not Qualcomm QRTR/QMI/IPA. QcomBaseband is a reference for the iOS-side boundary; its tested OS ABI is different and its eSIM provisioning is unverified.

The captured configuration also selects SBD and RX/UL PKTPROC; DIT is disabled. The public CPIF source supports separate SIPC5 and SIT layouts selected through `mif,protocol`. The exact live BYH3 protocol, queue/channel map and secure-monitor ABI remain unverified. The bounded host framing model requires explicit selection and does not interpret vendor payloads. CELL-009 recovers matching command schemas offline from explicitly supplied local RIL inputs; CELL-004 depends on that evidence. No inferred command is automatically replayed against the daily phone.

Acceptance is split: CP boot/shutdown → framed control/replies/events → SIM/slot/PIN and network registration → packet data/IPv4 → IPv6/reconnect → CommCenter/CoreTelephony → SMS → IMS/voice with bidirectional audio. A service icon, SIM detection or successful web request does not establish calls.

Carrier identity, test subscription and agreed endpoints are prerequisites for real network tests. Never use a personal number, EID, ICCID, IMSI or activation code in public fixtures. Emergency-service behavior remains an explicit unqualified limitation unless a suitable controlled qualification exists; no automatic live emergency calls.

## Stage I: eSIM

ESIM-001 specifies eUICC access and APDU models. ESIM-002 first tests an already-active test profile with native radio support. ESIM-003 develops profile lifecycle/LPA integration only after transport and test-subscription readiness. Distinguish these outcomes from one another and from an eSIM Settings page.

ESIM-004 additionally qualifies the selected iOS frontend/profile before ESIM-003 can pass. The first iPhone X reference is nano-SIM hardware; Apple's eSIM requirements start with XS/XR. This raises an unverified frontend/ABI compatibility question, not proof that adaptation is impossible. Inspect actual locally supplied components and record the adaptation/profile decision; do not silently replace the approved first OS. Android's ordinary-app APIs and lpac linkage do not establish system-LPA privileges or an XNU eUICC transport.

The [selected frontend investigation](procedures/esim-profile/README.md) adds pinned Intel ARI/libARI extraction as an alternative to assuming the Qualcomm donor's interface. Determine the actual iPhone image's modem-facing libraries/plugins before selecting ARI or QMI; neither replaces Samsung vendor command recovery. Current ARIstoteles documentation/tables span later OS versions and do not qualify16.5. Its real offline parser required corrections for sequence bits, nonempty TLVs, length encoding, complete-packet bounds and mutable-byte ownership; seven test groups pass after small attributed patches. No actual Apple image was supplied or inspected, so the selected frontend decision remains open. Public carrier-app API entitlements do not establish a system LPA or private ABI.

Use lpac only after pin/license review and a working logical-channel transport. Existing production profiles must not be automatically downloaded, deleted, switched or reset. Android's eUICC features and system APIs do not grant an ordinary app equivalent privileges.

## Coordination and final qualification

state/lab.json remains the task registry. New work has narrow file boundaries, dependencies, evidence kind, unique ownership and a handoff. No agents launch automatically. state/capabilities.json separates observations, implementation and native acceptance; tools/capabilities.py validates and renders CAPABILITIES.md. Task count is not a completion percentage.

A complete hardware result requires correct graphics and UI, networking, agreed SIM/eSIM capabilities, sound, cameras, input, sensors, power/sleep and storage across the full matrix. Before daily-use consideration, run a 24-hour mixed workload, repeated boots and sleep/wake, reconnects, process failures, resource cleanup and storage consistency checks. Retain unresolved limitations; a single successful run does not establish reliability.

## First commands

```sh
python3 tools/lab.py board
python3 tools/capabilities.py --check
python3 tools/sources.py verify s24-port
make check
```

Build and run commands are documented in each implementation procedure. None of the host tools installs, flashes or reboots a phone.
