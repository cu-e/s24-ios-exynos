# IOS-003 — Kernel readiness matrix for Apple launchd / backboardd / SpringBoard

Evidence kind: **source-review**, with two kinds of local observation that are labelled where they are used:
log lines of the one native run that exists (NAT-068, `docs/procedures/nat-068/run-001-kernel-log.txt`, native-device)
and strings read from the built NAT-069 image (`artifacts/nat-069/.../recovery.img`, host inspection).
Written 2026-11-12. Nothing here is a measurement of Apple userland on the S24: no Apple binary has run on the phone.

## 1. What this note is and is not

* It lists what the donor projects needed in the kernel to run the iOS 16.x userland, where the donor source shows
  it, and what the project kernel (xnu-8796.121.2 + HackiOS `redwood.patch` + `files/` overlay + e1s patches) has.
* Donor statements are **claims**. They were made on other hardware (Snapdragon 865 / Adreno 650 for ios-apollo) and
  with another build (iPhone X **16.7.16, 20H392**; the target here is **16.5, 20F66**, IOS-001/002).
* A symbol, a source file or a successful build is not compatibility. The project-state column uses only:
  **in S24 log** (a line of the NAT-068 kernel log), **in image** (string in the built payload, no behaviour implied),
  **in source** (file in the pinned tree, never run on the phone), **absent** (searched for in the reviewed files and
  not found) and **unknown**.
* Not claimed anywhere below: that Apple's `launchd` runs, that a real iOS root mounts, that any frame reaches the panel.

## 2. Pins and licences

Fetched with `tools/sources.py` at the full SHAs in `research/sources.json` (`review_files` extended for this note;
the checkouts are sparse, `verify` is clean). No upstream install, flash or build script was executed.

| Source | Pin | Licence (from `research/sources.json` / file headers) | Role here |
| --- | --- | --- | --- |
| ios-apollo (`aTechGeekDev/ios-apollo`) | `b5ac6999c65b03c432139af99cf47ab84eefd4e8` | MIT (root `LICENSE`, blob `54029555d73c`); per-file licences preserved | Most complete donor for iPhone X 16.7.16 userland on a phone |
| s24-port (`RNDMBG/iOS-On-S24`) | `c8860decc62c6d6180e609036d027a2997972420` | GPL-2.0-only loader; embedded HakiOS APSL-2.0 (`xnu/hackios/LICENSE`, blob `ec73934b05c6`); selected e1s additions have no blanket grant | The project's own kernel base and e1s patches |
| hakios (`oosexgang/hakios-xnu-kernel`) | `87bf4851bcc9cbb24fd79997820aa3661abe4ea5` | APSL / MIT / third-party | Origin of `files/` stand-ins; has a builtin HFS+ (`xnu/files/bsd/hfs/hfs_builtin.c`, blob `666a0980e35a`) |
| y2sios, iosplus10, ios-lemonadep | see `research/sources.json` | per NOTICE / per-file | **Not reviewed for this note** (their `review_files` serve other tasks: Exynos 990, OnePlus 10, Pixel donors); they contribute no row |

Licence consequence: nothing from the donors is copied into the repository by this task. Reuse of any patch needs a
separate task with attribution and the component licence kept (APSL-2.0 for HackiOS parts, MIT for ios-apollo).

## 3. Matrix

Donor paths are relative to the pin of the named source; the blob id (first 12 hex digits) is `git rev-parse <pin>:<path>`.
"Consequence" is what it means for the next step, not a promise.

| # | Requirement | What the donor needed (claim) | Donor evidence (path @ blob) | Project state | Project evidence | Consequence |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | **Root content** is the three IPSW disk images, composed | iOS 16.7.16 root = rootfs (UDIF holding APFS) + SystemOS cryptex + AppOS cryptex (raw APFS), merged into one volume: cryptexes under `/private/preboot/Cryptexes/{OS,App}`, shared cache hard-linked to `/System/Library/Caches/com.apple.dyld`, cryptex-only files linked to their root paths because "dyld does not search the cryptexes at ignition level 1" | ios-apollo `tools/mkiosroot.sh` @ `fc9b9f88bc5a`, `tools/build-ios-root.sh` @ `cfc069e8fe0f` | **unknown** for 16.5: IOS-001/002 identified the three images of D22AP (rootfs `096-04088-077.dmg`, SystemOS `096-04666-078.dmg`, AppOS `096-03536-083.dmg`) and hashed them, but no tool on the host can list their files | `docs/procedures/ios-001/ipsw-summary.json` | Where `dyld`, the shared cache and `launchd` are in 16.5 is a hypothesis until a UDIF + APFS reader lists them (new tasks IOS-004/005) |
| R02 | **Root filesystem driver** that can read that root | Donor converts everything to a 16 GiB **HFS+** image (`mkfs.hfsplus`, `apfs-fuse` on a PC) and mounts it with a builtin HFS+ and `rootrw=1` | ios-apollo `xnu/patches/0026-sweet-builtin-hfs.patch` @ `6d5001da7f26`, `0031-sweet-read-write-root.patch` @ `296fb9789ba5`, `0029-sweet-unsealed-root-volume.patch` @ `5acfe048c7c9` | **HFS+ absent**; **APFS read-only driver in source** (9491 lines in the driver directory without `libdeflate`/`libzbitmap`; `apfs_vfsops.c` @ `8f0ed38c080d`, `apfs_lib.c` @ `db383dc5b169`), registered ahead of `mockfs` (`redwood.patch` @ `8f7dd871ff08`, `options APFS`). **In image**: 175 distinct `apfs_*` symbol strings, 28 `mockfs_*`, no "Apple File System" string. The filesystem that mounted `md0` in NAT-068 is **not named in the log** (unknown) | `docs/e1s-userland.md:12` @ `2fb36011eedf` ("HFS+ driver is not present, so APFS is the only filesystem-image root path"); `apfs.h` header ("Read only", "checked against real images on the build machine" — a source comment, not re-run here); log lines 194-195 (`BSD root: md0`) | No Apple APFS (sealed rootfs, compressed files, cryptex graft) has been mounted by this kernel. The donor HFS+ route is a second option but adds a driver the project does not have. Decide after IOS-005 shows what features the real containers use |
| R03 | **Compressed files** | The IPSW images hold LZBITMAP-compressed files; the donor decompresses them on the PC | `tools/mkiosroot.sh` header | **In source**: `apfs_zbitmap.c`, `libzbitmap`, `apfs_deflate.c`; LZFSE decoding in-kernel not confirmed | `redwood.patch` (`bsd/miscfs/apfs/apfs_zbitmap.c optional apfs`) | Host reader needs LZFSE (done: `tools/ios/lzfse_py.py`) and LZBITMAP (not yet in Python) |
| R04 | **Writable root / overlay** (launchd, logd, SpringBoard write to `/private/var`) | `rootrw=1`, `ufsrw=1`: the root in `userdata` is read-write | ios-apollo `0031` above; README cmdline (`README.md` @ `33989154f858`, line 233) | **In source**: APFS mount is read-only by design; `bindfs`, `ramfs` and `mockfs` are in `FILESYS_BASE` (`redwood.patch` line 1489). Never composed into a writable overlay; never run | `apfs.h` ("Read only. Nothing here writes to the device"); `redwood.patch` | A RAM-backed overlay is the only writable layer allowed (Android partitions are off limits). Design = NAT-073 |
| R05 | **AMFI stand-in** (`__mac_syscall("AMFI", …)`): dyld policy 0x5a, boot-arg state 0x60, signatures, entitlements, platform-binary flag | Without an `AMFI` policy dyld and system daemons fail; launchd panics if a system daemon is not a platform binary; entitlements parsed from the signature | ios-apollo `0025` @ `5479d77ce654`, `0035` @ `1be1b051d99f`, `0036` @ `f230ec2ac6f4`, `0124` @ `5ae15876da96` (0x60 answered with 0x86) | **In S24 log**: the policy loads. **In source**: `kern_minimac.c` @ `f65c9793b6da` answers 0x5a (allow all) and 0x60 (0x86), marks every ad-hoc signed binary a platform binary, grants privileges by entitlement table; `miniamfi.c` @ `d270c26928ef` provides the interface; a second file `miniamfi_entitlements.cpp` @ `b13c6e5e004c` sits beside it (name only, not reviewed). **Unrun against Apple binaries** | Log lines 89-90: `Security policy loaded: Apple Mobile File Integrity (stand-in) (AMFI)`; header of `kern_minimac.c` | The stand-in was written from the user side of iOS 16.5 (header comments), which is the target version. Whether Apple's `launchd` and `dyld` accept it is untested; whether entitlements are parsed from signatures the way donor 0035 does is not established here |
| R06 | **Sandbox stand-in** (`__mac_syscall("Sandbox", …)`, container path request 4) | Every query allowed; container paths must come back for app extensions or PlugInKit throws | ios-apollo `0050` @ `70f2f1271f07`, `0161` @ `f49afdf99e4f` | **In S24 log** (policy loads). **In source**: `kern_minimac.c` answers the container question from `CFFIXED_USER_HOME` on the process stack; extension tokens: unknown | Log lines 91-92: `Seatbelt sandbox policy (stand-in) (Sandbox)` | Same caveat as R05; app extensions are a milestone-7 concern, not a launchd blocker |
| R07 | **Trust cache** | None exists; the donor patches the runtime to a NULL state and turns off `enforce_xpc_cache_code_signing` for ExtensionKit | ios-apollo `0015` @ `e383f964f049`; `tools/root-files/files.txt` @ `19956837e2ee` | **In image**: stock `trust_cache*` code (17 distinct strings). No project patch for it in the reviewed files. The kernel reached PID 1 without a trust-cache panic, so the stock path did not trap in NAT-068 | Log shows no trust-cache line; `docs/e1s-userland.md:120` ("no trust cache") | Not a first-launchd blocker on current evidence; whether platform-binary lookup by cdhash matters for Apple binaries is unknown |
| R08 | **AppleKeyStore** (keybagd, securityd, MobileKeyBag) | Built-in keystore for a device without passcode; selector numbering of 16.7; plain-plist `systembag.kb` in `/private/var/keybags` | ios-apollo `0038` @ `ebe463a1b0cf`; `tools/mkiosroot.sh` | **In image** (5 `MiniAppleKeyStore` strings) and **in source** (`MiniAppleKeyStore.cpp` @ `f0e367a74d9a`, selectors derived from iOS 16.5 userland). Not in the S24 log: **no evidence it registered or was ever queried** | `MiniAppleKeyStore.cpp` header | Needed before keybagd/securityd. The donor's selector numbering is labelled "iOS 16.7", the project's was derived from 16.5; whether they differ is unknown |
| R09 | **launchd service-cache handshake** | `launchd_unsecure_cache=1`; `launchd_cache_loader` hands launchd its cache ("Using unsecure cache … Cache sent to launchd successfully"). A rewritten `launchd.plist` was refused and launchd's job panicked: *initproc exited, namespace 7 subcode 0x1 "No service cache handshake structure not initialized"* | ios-apollo `NOTES.md` @ `0f3a477af003`, boot 46/47 paragraph (line 1111) | **Absent**: the string `launchd_unsecure_cache` is not in the image; no project code for it in the reviewed files. Apple's launchd has never run on this kernel | grep of the NAT-069 image; no match in `redwood.patch`/`kern_minimac.c` | Which component consumes the boot-arg is not established here; the donor's reviewed patches do not mention it. Use it in the first Apple-launchd run and do not edit `launchd.plist` (the donor's edit was refused) |
| R10 | **Boot-args / device tree the userland reads** | `unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin launchd_unsecure_cache=1 wdt=-1 rootrw=1`; ADT built from the real `d22ap` DeviceTree with `/product`, haptics, files carried by the boot image | ios-apollo `README.md` line 233; `tools/root-files/files.txt` header | NAT-069 cmdline has none of them (`rd=md0 … cpus=1 … launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 e1sdisp=2`). The ADT is generated by the loader from the S24 DTB, not from the IPSW DeviceTree | `docs/procedures/nat-069/README.md`; IPSW carries `Firmware/all_flash/DeviceTree.d22ap.im4p` (IOS-001) | The IPSW DeviceTree is a free template for the properties MobileGestalt reads; compare it on the host (new task) |
| R11 | **Kernel-side file injection before launchd** | `xnu 0120/0121` write files listed in the boot image into the root before launchd starts (ExtensionKit flag, migration markers, keybag, launchd overrides) | ios-apollo `tools/root-files/files.txt` header; `NOTES.md` line 981 (`/sweet-files`) | **Absent** in the reviewed s24-port files | grep | Useful only if the root stays read-only; with a RAM overlay the host can seed files into the image instead |
| R12 | **Setup finished** (`purplebuddy.sentinel`) | Kernel creates the semaphore on open without `O_CREAT`; Setup is also skipped by preference edits in the root | ios-apollo `0165` @ `e6c038757942` | **Absent** (no `purplebuddy` string in the image or in `kern_minimac.c`) | grep | Needed before SpringBoard/Files; not before launchd |
| R13 | **First-boot data migration** | "The first boot of a new root runs iOS's data migration once (an hour or more)"; an alternative root pre-seeds `datamigrator` sentinel and removes jobs | ios-apollo `README.md` line 172; `NOTES.md` line 1107 | Structural conflict: the project has no persistent data volume, and one session is bounded by the 83 s loader watchdog (see R17) | `docs/e1s-userland.md` (RAM root only); `docs/strategy/2026-11-12-ios-critical-path.md` | The root must be delivered already migrated (host-seeded), or migration must be made unnecessary; this is a design item of NAT-073, not a kernel patch |
| R14 | **IOSurface** | Closed IOSurface.kext replaced; user client selectors and structures worked out from userland | ios-apollo `0046-sweet-iosurface-iomfb.patch` @ `35b320a60737` | **In image** (58 distinct `MiniIOSurface` strings), **in source** (`MiniIOSurface.cpp` @ `5523e8557902`, "worked out from the user-space side of iOS 16.5"). **No S24 log line** | grep of the image | Needed by backboardd (milestone 4-5); not by launchd |
| R15 | **IOMobileFramebuffer / display scan-out** | A stand-in service answers backboardd; the donor's framebuffer driver copies the CoreAnimation surface into the bootloader-configured panel memory (~10 MB `memcpy` per frame into write-combining memory) | ios-apollo `0046`; `NOTES.md` line 691 | **In S24 log**: `MiniIOMobileFramebuffer: display 1125x2436 on a panel of 1080x2340 (4320 bytes per row)` and `e1s-display: framebuffer 1080x2340 depth 32 stride 4320 phys 0xfa200000`. Whether the panel keeps scanning that buffer after S-Boot is **unmeasured**: the read-only DECON/DSIM dump of patch 0010 is built (NAT-069) and unrun | log lines 192, 199-201 | The donor's scan-out was alive because its bootloader left a simple framebuffer; the S24 equivalent is exactly what NAT-070 asks |
| R16 | **GPU / accelerator service** | backboardd matches `IOAcceleratorES`; the donor replaced CoreAnimation's GL backend by an EAGL→Mesa bridge for speed | ios-apollo `userland/README.md` @ `dbab8a6f38b2` (`ca-bridge`, `mesa`); `NOTES.md` line 1305 (boot 1) | **Absent** on e1s: `redwood-touch: e1s platform; redwood hardware drivers are disabled` | log line 208 | See R18: what backboardd does with no accelerator service is unmeasured |
| R17 | **Time, watchdog, CPUs** | `wdt=-1`, `cpumask=0xf1` / `cpus=8`: no watchdog, big cores first | ios-apollo `README.md` line 233; `NOTES.md` line 217 | The loader's CL0 watchdog (83 s, never petted by the loader) resets the phone about 57 s after USB enumeration; the kernel reaches PID 1 at 48.6 s. `cpus=1`, only CPU 0 registered. The timed `loader_return_after=8` path is untested | log lines 101, 224-225; `docs/procedures/nat-068/README.md`; `docs/strategy/2026-11-12-ios-critical-path.md` (83 s watchdog, NAT-046/048) | Apple's launchd cannot even finish a boot in the remaining ~8 s: **a watchdog cap or keepalive is a hard prerequisite** (NAT-071) |
| R18 | **Rendering without a full GPU driver** | `sweetgl=0` "Keep iOS's software renderer"; a known-good boot is described as "software UI, no GPU bridge"; one boot with Metal refused fell back to CPU rendering, "glitchy and slow" | ios-apollo `README.md` line 309; `NOTES.md` lines 258, 732 | **unknown** on the S24 and not demonstrated here. Pre-conditions in the project: R14/R15 only | – | Do not promise software rendering. First test = backboardd with IOSurface + IOMFB stand-ins and no accelerator, observing whether it commits a frame to a surface (new task) |
| R19 | **dyld / shared cache** | Shared cache from the SystemOS cryptex (978 MB for 20H392 per the donor's CI note); dyld must find it at the root path the donor links | ios-apollo `NOTES.md` line 649; `mkiosroot.sh` | **unknown**: 16.5 cache size and location not measured; no host tool lists it | – | The cache alone exceeds the 96 MiB RECOVERY slot by ~10×: see section 4, item 2 |
| R20 | **Syscall / Mach-trap numbering and semantics** | Same XNU family (8796) as the donor kernels | `NOTES.md` line 217 (names "XNU 8796") | **unknown**. The project kernel is xnu-8796.121.2 (`DEVELOPMENT_ARM64_E1S`); the 16.5 kernelcache is `xnu-8796.122.4~1` `RELEASE_ARM64_T8015` (IOS-001). Only 101.5, 121.2, 141.3 are public tags, so the 122.4~1 source is unavailable | `docs/procedures/ios-001/ipsw-summary.json` (`comparison_with_project_kernel`) | Cheap host check once the shared cache is readable: `libsystem_kernel` stubs (`mov x16,#N; svc #0x80`) against the project's `syscalls.master` |
| R21 | **Image-level boot of a Mach-O init** | `/sbin/launchd` from the root, `launchdsuffix=release` | `docs/e1s-userland.md:37-41` | **In S24 log**: `load_init_program: attempting to load /sbin/launchd`, the project's own static probe ran as PID 1, exit 81 returned to the kernel (not Apple's launchd) | log lines 5, 224-225 | M1 reached for a 1 s process; "stable" needs R17 |

## 4. Ordered kernel/root items

Order = what must be true before the *next* thing can even be observed; evidence in parentheses.

**Blocks the first run of Apple's `launchd` (milestone 3):**

1. **A listable Apple root on the host** (R01, R19). Nothing in the repository can enumerate the rootfs or cryptex images;
   `/sbin/launchd`, `dyld`, the shared cache and every library path are unverified. (IOS-001/002 stopped at the container level.)
2. **A way to get a root of unknown but certainly gigabyte size into the phone without an Android partition** (R19, R04). The only authorised writable
   region is the RECOVERY slot, 100 663 296 B; the donor's shared cache alone was 978 MB. S24 RAM is 7.06 GiB
   (`research/notes/DEV-001-profile.md`). Compressed, pruned, host-composed APFS in RAM delivered by the loader over USB
   is the only in-scope route found; its throughput has never been measured. This is the largest non-kernel item.
3. **A session longer than ~8 s** (R17). USB delivery, a launchd boot and any log chain all exceed the current watchdog
   budget, so the loader must stop the reset (cap/keepalive) before anything beyond a probe can run.
4. **The kernel mounting that root** (R02, R03). The APFS driver exists and its symbols are in the image, but it has not
   been exercised on a real Apple container on this kernel; host-side parsing of the same containers comes first.
5. **Stand-ins answering Apple's launchd** (R05, R06, R08, R09, R10). These are in source or the log as policies that load; how
   Apple's launchd reacts is the first thing the first Apple run will show, so no further kernel work should precede it.

**Can wait until after launchd runs:**

* IOSurface / IOMobileFramebuffer behaviour with backboardd, scan-out ownership, GPU (R14-R16, R18): needed for milestones 4-5.
  The scan-out question has a prepared read-only run (NAT-069/070).
* Setup sentinel, trust-cache fidelity, extension containers, migration markers (R06, R07, R12, R13): needed for SpringBoard,
  not for launchd.
* SMP (R17): launchd runs on one CPU; speed matters later.
* Syscall-table comparison (R20): needs item 1 first, then is cheap; do it before the first Apple run so that a mismatch is
  not mistaken for a stand-in problem.

## 5. What this note does not establish

* Whether the project kernel's APFS driver reads Apple's rootfs or cryptex containers (never mounted).
* Whether Apple's `launchd`, `dyld` or any Apple daemon accepts the AMFI/Sandbox/keystore stand-ins.
* Whether any panel pixel is controlled by the kernel after S-Boot, and whether backboardd renders without an accelerator.
* Whether the 16.7.16 observations of the donor carry over to 16.5 (20F66).
* The donors' own claims of a working lock screen/home screen on their phone (not reproduced; a different SoC and bootloader).

## 6. Tasks this note produces

* **IOS-004** — UDIF (`koly`) container reader for the IPSW rootfs image, host-test + real-image smoke check.
* **IOS-005** — read-only APFS reader (Python, from the public specification and `apfs_format.h` as cross-reference) and
  inventory of rootfs + SystemOS + AppOS: `launchd`, `dyld`, shared cache, `backboardd`, `SpringBoard`, size per directory;
  syscall-stub comparison for R20 as a follow-on.
* **IOS-006** — first frame without a full GPU driver: identify, from the real `backboardd`/`QuartzCore` binaries, the code path
  taken when no accelerator service matches, and the minimal contract (IOSurface/IOMFB) needed to commit a frame. Host analysis
  first; nothing is promised.
* **NAT-073** (exists) — root delivery without Android partitions; this note supplies its size constraints.
* **NAT-070/071/072** (exist) — scan-out dump; watchdog cap and heartbeat PID 1; native heartbeat run.
