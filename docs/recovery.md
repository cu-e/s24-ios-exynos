# Recovery and return to Android for the owner's S24

**Status (2026-11-10, NAT-001):** dated, hash-verified copies of every boot-chain partition exist outside Git, and the bootloader state is now measured. **No restore has been performed or tested.** This document grants no permission. Writing any partition, entering Download Mode or rebooting needs a separate owner decision ([decision 0002](decisions/0002-owner-autonomy-grant-2026-11-10.md) does not grant these).

## Device and boot state (root, read-only, 2026-11-10)

| Item | Value | Source |
|---|---|---|
| Model / device | SM-S921B / `e1s`, hardware `s5e9945` | DEV-001, `androidboot.hardware` |
| Bootloader / firmware | `S921BXXS9BYH3` | `androidboot.bootloader` in `/proc/bootconfig` |
| Verified boot state | `orange` | `androidboot.verifiedbootstate` (written by S-Boot) |
| vbmeta device state | `unlocked` | `androidboot.vbmeta.device_state` |
| Unlock count / warranty bit | `ulcnt=1`, `warranty_bit=1` | bootconfig |
| Kernel | `6.1.93-android14-11`, `kvm-arm.mode=protected` | `uname -r`, `/proc/cmdline` |
| kexec | not configured (no `CONFIG_KEXEC*`, no `/sys/kernel/kexec_loaded`) | `/proc/config.gz` |

The system properties `ro.boot.verifiedbootstate=green`, `ro.boot.vbmeta.device_state=locked` and `ro.boot.warranty_bit=0` contradict bootconfig. They are rewritten in userspace (Magisk is installed) and are not evidence of the bootloader state. This resolves the conflict noted in DEV-001: **the bootloader is unlocked.** `androidboot.kg=0x4` (KnoxGuard) is recorded but its meaning is not established here.

### Verified boot

`vbmeta` is signed `SHA256_RSA4096`, flags 0. It holds hash descriptors for `boot`, `init_boot`, `recovery` and `vendor_boot`, chain descriptors for `dtbo`, `prism` and `optics`, and hashtrees for `odm` and `product`. `vbmeta_system` holds the system, vendor and dlkm hashtrees.

Recomputing each hash descriptor (`sha256(salt || image[:image_size])`) gives:

| Partition | Matches vbmeta | Meaning |
|---|---|---|
| boot | yes | stock |
| recovery | yes | stock (ramdisk build `UP1A.231005.007.S921BXXS9BYH3`, no TWRP) |
| vendor_boot | yes | stock |
| init_boot | **no** | Magisk-patched (`.backup/.magisk` present) |

Android boots with the mismatching `init_boot`. **Observed on this phone:** in the orange state S-Boot boots an image in the normal boot path that fails its vbmeta hash. Whether it does the same for a non-stock `recovery` is an inference, not an observation.

Android also contains `/vendor/recovery-from-boot.p` and `/vendor/bin/install-recovery.sh`. These may rewrite a non-stock `recovery` during a normal Android boot. That behaviour has not been observed.

## Backups

Taken 2026-11-10T05:15Z with `su` + `dd` over `adb exec-out`. Every host copy equals `sha256sum /dev/block/by-name/<p>` computed on the phone.

Location: `devices/recovery/backups/2026-11-10/` in the primary checkout (`/home/egor/dev/pet/s24-ios-exynos`). The directory is ignored by Git and has mode 700; the files have mode 600. `manifest.json` there is produced by [`verify_backups.py`](procedures/recovery/verify_backups.py), which re-checks everything on the host without the phone.

| Partition | Bytes | SHA-256 | State |
|---|---:|---|---|
| boot | 67,108,864 | `a05a3c3b1085ecf9dc7522079a28d196732e0fd6384068aa6f964b71c29a86ab` | stock, header v4, kernel only |
| init_boot | 16,777,216 | `480181ac8480bc2abd22909bbd0dc2669136d7194a6a50d59cda1c0ee7422b8e` | current state, Magisk-patched |
| vendor_boot | 67,108,864 | `7d028e3398a1f3fdf1bd3bb5b990af1b8cfb078930f6e8aec53d289717739129` | stock, header v4, DTB 433,300 bytes |
| recovery | 100,663,296 | `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` | stock, header v2 with its own kernel, ramdisk and DTB |
| dtbo | 8,388,608 | `2afdb40b4be82e2158e863df926a12b2394a6b2361c711e0aa47acc8043f3f9d` | chained in vbmeta; not checked further |
| vbmeta | 65,536 | `063ebf5a98d9584e879e4649ba8033eb8c142ef47e2560533d44d0f135e858e5` | stock signature layout, flags 0 |
| vbmeta_system | 65,536 | `b44d99474c55a6fbfe5071e5098f0638bae194fa6ce9ba581f42285c234087b4` | flags 0 |

Limits:
- There is one copy on one host disk. That is a backup, not an independent one; a second offline copy is the owner's choice.
- The stock `init_boot` is not on hand, only the current Magisk-patched state. Restoring this copy restores the current state, not stock.
- The images are Samsung firmware and are never committed.

## Restore path: available, not tested

If a future authorized session changes a boot partition, the return is to write back the matching image from this backup in Download Mode with Odin. Use an AP tar that contains only that image, for example `tar -H ustar -cf restore-recovery.tar recovery.img`. A raw `.img` inside a tar is the form the pinned `s24-port` upstream documents for BOOT; it has not been tried here.

A change confined to `recovery` leaves `boot`, `init_boot`, `vendor_boot`, `vbmeta` and `userdata` untouched. A normal boot does not read `recovery`.

| Step | State |
|---|---|
| Matching images with hashes | **ready** (table above) |
| Download Mode entry on this phone (power off, hold both volume keys, connect USB) | not observed |
| Odin on the owner's computer, USB permissions | not tested |
| S-Boot boots a non-stock `recovery` in orange state | inferred from `init_boot`, not observed |
| A forced restart (Vol Down + Power) after a recovery boot returns to Android | not observed |
| Android's `install-recovery` and a non-stock `recovery` | not observed |
| Verified restoration of any partition | **not tested** |
| Control channel from XNU, one-shot boot, hardware watchdog | not available |

## Rules that stay in force

Preserving Android partitions, keeping Android bootable and preserving user data are separate properties. A backup does not prove that recovery works. A structurally valid image does not prove that it executes.

The first native session needs the owner's explicit decision for a concrete scope, initial state, image hash, return procedure, manual fallback and stop criteria; record these in NAT-003. Do not run an autonomous native loop before a restore has been verified. Do not repeatedly flash or reboot after losing connectivity. Stopping an agent does not undo hardware actions.
