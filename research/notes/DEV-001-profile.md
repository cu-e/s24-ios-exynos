# Measured S24 profile — 2026-11-05

Origin: local-device, kind: android-userland. Collected through already-authorized USB ADB; shell uid 2000, SELinux Enforcing. Filename dates use Asia/Yekaterinburg; actual UTC timestamps are in manifests (2026-11-04T21:44–21:53Z). No installations, setting changes, su requests, reboots or raw partition reads were performed.

| Component | Observation |
|---|---|
| Device | Samsung SM-S921B, e1s; SoC s5e9945, board erd9945 |
| OS | Android 15, API 35, One UI property 70000 |
| Firmware | S921BXXS9BYH3, security patch 2025-08-01 |
| Kernel | 6.1.93-android14-11, page size 4096 bytes |
| CPU | 10 online cores, clusters 4+3+2+1; policy maxima 1.959/2.592/2.900/3.207 GHz |
| RAM | MemTotal 7 401 772 KiB ≈ 7.06 GiB available to the kernel; physical capacity not separately measured |
| Swap / CMA | 3 145 724 / 372 736 KiB |
| GPU | Samsung Xclipse 940, Vulkan 1.3.279, Samsung Proprietary driver 24.3.9, 153 device extensions |
| GLES | ANGLE over Vulkan, OpenGL ES 3.2; GLES and Vulkan driver version strings differ |
| Display | 1080×2340, density 480 with override 450; advertised 120/80/60/48/30/24/10 Hz, active 60 Hz in the snapshot |
| Storage | sda 255 890 292 736 bytes; by-name map and sizes saved |
| Partitions | boot 64 MiB, init_boot 16 MiB, vendor_boot 64 MiB, recovery 96 MiB, dtbo 8 MiB, super 12 380 MiB |
| Touch | sec_touchscreen, ABS X/Y 0–4095, 10 multitouch slots |
| Sensors | LSM6DSVTR accel/gyro, AK09918C magnetometer, STK33F11 light/proximity, LPS22DFTR barometer; HAL inventory saved |
| Battery | Snapshot: 80%, 4216 mV, 28.1°C; not a wear/capacity assessment |

## Boot, root and virtualization

The owner reports unlock. Android reports ro.boot.flash.locked=1, ro.boot.vbmeta.device_state=locked, ro.boot.verifiedbootstate=green, warranty_bit=0 and sys.oem_unlock_allowed=0. /system_ext/bin/su → ./magisk is present; Magisk version is 96221b69-alpha:MAGISK:R. Properties may be overridden: this is a discrepancy, not proof of a locked bootloader. ADB root access was not tested; Download Mode was not entered.

The captured kernel.config has **CONFIG_KEXEC and CONFIG_KEXEC_FILE disabled**. Ordinary kexec cannot be treated as an available XNU launch path on this kernel. CONFIG_KVM=y and /dev/kvm exists, but shell readable/writable checks did not succeed. Opening the node, ioctl and VM execution were not tested. Usable virtualization cannot be promised from this evidence.

## Saved files and limitations

Local, outside Git:

- `devices/local-2026-11-05-session1.json` — original narrow inventory.
- `devices/local-2026-11-05-session1.en.md` — English report and file index; the original `.md` remains unchanged.
- `artifacts/device-profile/2026-11-05-session1/` — 28 sections, manifest, hardware-summary.json, partition-map.json and validation.json.
- `artifacts/device-profile/2026-11-05-session1-extra/` — 7 additional sections and manifest.

SHA256 was verified for all 35 original capture files; statuses: 25 collected, 9 partial-or-unavailable, 1 unavailable. For partial files, read diagnostics rather than treating every line as a hardware fact. Some DT paths can be listed, but SELinux denies property reads. /proc/iomem is unavailable: native MMIO addresses, reserved-memory and IRQ routing were not recovered. Parts of sysfs and audio metadata are unavailable. A complete DTB and BOOT/recovery images were not extracted. A captured kernel config does not establish individual feature operation.

A collector defect was fixed: a nonempty JSON wrapper around an empty tree was initially reported as successful. The original session manifest retains original_status and explains reclassification to unavailable. The current collector rejects empty trees and has a regression test. The historical capture file was not rewritten.

IMEI, ADB serial, MAC, Vulkan UUID/LUID, accounts and personal files were not saved. Full getprop/logcat/dumpsys output was not saved. The raw device-tree tar was processed only in memory. This is technical inventory, not a backup or an XNU test.

## Handoff

DEV-001 covers inventory; DEV-002 covers collector code and host tests. `make check` passed 29 tests, including privacy filters, unavailable trees and timeout. Filter tests are synthetic; hardware values above came from separate actual ADB captures. Metadata collection was not preregistered as an experiment; do not invent a retrospective plan.

Next: pin upstream under RES-001 and compare SM-S921B configuration with donors. Use the captured Vulkan profile for GUI work; APK installation remains a separate stage. A native loader and automatic recovery are not implemented by this project. Do not repeat all captures without a new reason; use existing manifests and fresh names for subsequent observations.

This maintained note was translated under DOC-001. Immutable original evidence and hashes remain unchanged; see state/evidence/DEV-001.en.json for the English evidence view and its source digest. The original version of this note is available in Git commit 70f32ee.
