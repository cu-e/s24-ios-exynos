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

Source fetch is explicit, SHA-pinned, does not run upstream scripts and does not recurse into submodules. Sources stay in references/. Builds run in artifacts/ copies so reviewed checkouts remain unchanged. Apple userland, SDKs, firmware and private device data are external local inputs, excluded from Git.

## Stage B: bounded experiments while Android runs

GPU-001/002/004 prepare a native Vulkan probe APK, owned fixtures and Metal/AIR translation tests. GPU-003 measures the stock driver after app scope authorization. GPU-005 compares app-local RADV only after the stock baseline and a reviewed custom-driver loading path.

Start with one worker, at most 128 MiB experimental GPU resources, five-second runs, bounded fence waits and a host deadline. Stop requests prevent new submissions. Do not destroy in-use GPU resources as a cancellation shortcut. A blocked kernel driver can outlive a stopped app: process cancellation does not guarantee phone recovery. Stop new runs on DEVICE_LOST.

VM-001 inventories availability using already-authorized read-only access. VM-002 prepares a pinned guest on the host. VM-003 tests the guest only after an accessible interface and appropriate device scope. CONFIG_KVM, an existing device node or ARM64 alone is insufficient. No automatic SELinux, root or kernel changes.

## Stage C: recovery and native control

NAT-001 prepares matching stock images, hashes, backups, host recovery requirements and exact return steps. NAT-002 designs the actual control channel, loss-of-link behavior and manual fallback. A verified restoration is a separately gated native task; documenting it does not establish it. NAT-003 cannot run until that evidence exists and a concrete image/session has separate authorization.

No usable kexec path is established: the captured kernel disables it. No fastboot boot support is established on this Samsung. Mu-Silicium e1s lacks working USB/storage in its published status. Do not promise an autonomous loop or automatic return without testing the independent control path. Backup, Android bootability and user-data preservation are distinct acceptance properties.

## Stage D: minimal native XNU

First: loader entry, early XNU markers, MMU, timer/IRQ, scheduler, RAM root and owned static PID 1, one CPU. Then measure SMP, per-CPU timers/xcall, coherency and the 4+3+2+1 topology. Verify live reserved memory and page-size assumptions before DMA. No inherited address becomes a measured fact because it appears in a source header.

The upstream stage0 /sbin/launchd is an owned test Mach-O. It does not establish Apple launchd, backboardd or SpringBoard. Capture real device logs, not simulated preview screens. Default storage writes remain disabled.

## Stage E: display, input and real iOS userland

Validate framebuffer pixels and touch/HID first, then dyld/shared-cache compatibility, launchd, backboardd, SpringBoard and Settings on the selected iPhone X 16.5 profile. Separate panel scanout, VSYNC, brightness and power from GPU rendering. Start at 60 Hz.

Minimal tests use RAM root. Real userland uses a separate read-only image and experimental writable overlay. Measure memory budget before loading; if it cannot fit with kernel/GPU headroom, implement and verify native USB plus host-backed block transport before proceeding. Do not repurpose Android USERDATA, EFS, super or modem partitions. Internal persistent storage is a separate future decision and authorization.

## Stage F: Xclipse native graphics

```text
CoreAnimation / apps → Metal frontend for the selected OS ABI
 → metal2vulkan → RADV Xclipse → Darwin winsys / kernel backend
 → firmware + GPUVM + command queues + IRQ + power
 → IOSurface sharing → DECON/DSIM scanout
```

GPU-006 specifies ownership and operations for alloc/free, map/unmap, submit, fence completion/error, cache synchronization and fault teardown. GPU-007 implements the host-buildable native backend. GPU-008 is the first native clear/copy/triangle acceptance. GPU-009 adapts Metal registration, ABI and IOSurface ownership; GPU-010 measures multiprocess CoreAnimation and presentation.

Android RADV and a shader translator are not sufficient by themselves. Review per-file licenses and provenance before incorporating donor code. Turnip/Panfrost examples have different hardware command streams. Defer 120 Hz, compression tuning and ray tracing until correct pixels, cleanup, concurrency and thermal behavior pass.

## Stage G: peripherals and power

| Subsystem | Ordered acceptance |
|---|---|
| Wi-Fi | Actual PCI ID/revision and board data → Exynos PCIe/DMA/IRQ → firmware → scan → WPA2 → DHCP/DNS/HTTPS → iOS integration → WPA3/reconnect |
| Bluetooth | Exact controller/transport → firmware/HCI → discovery/pairing → BLE → audio profiles |
| Audio | ABOX firmware/IPC → PCM → codec/amplifier → speaker → microphone → OS routing → call duplex |
| Cameras | Sensor identity → rails/MCLK → CSIS/DMA frame → ISP → OS camera integration |
| Sensors/GNSS | Hub transport and timestamps → readings → OS services |
| Power | Battery/RTC → thermal limits → DVFS → idle → suspend/wake → charging policy |
| Other | Haptics, USB-C/PD, NFC, biometrics, video codecs and external display each require separate work and evidence |

Local Android modules indicate KIWI V2/CNSS for Wi-Fi and CS35L43/ABOX for sound. Do not silently select Broadcom or copy S9/S20 register values. A camera ID is not a frame; battery readings are not charging control; Samsung biometrics are not Apple Secure Enclave.

## Stage H: Samsung modem and telephony

CELL-001 specifies the actual CPIF/shared-memory transport using the captured S5000AP configuration. The hardware path is not Qualcomm QRTR/QMI/IPA. QcomBaseband is a reference for the iOS-side boundary; its tested OS ABI is different and its eSIM provisioning is unverified.

Acceptance is split: CP boot/shutdown → framed control/replies/events → SIM/slot/PIN and network registration → packet data/IPv4 → IPv6/reconnect → CommCenter/CoreTelephony → SMS → IMS/voice with bidirectional audio. A service icon, SIM detection or successful web request does not establish calls.

Carrier identity, test subscription and agreed endpoints are prerequisites for real network tests. Never use a personal number, EID, ICCID, IMSI or activation code in public fixtures. Emergency-service behavior remains an explicit unqualified limitation unless a suitable controlled qualification exists; no automatic live emergency calls.

## Stage I: eSIM

ESIM-001 specifies eUICC access and APDU models. ESIM-002 first tests an already-active test profile with native radio support. ESIM-003 develops profile lifecycle/LPA integration only after transport and test-subscription readiness. Distinguish these outcomes from one another and from an eSIM Settings page.

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
