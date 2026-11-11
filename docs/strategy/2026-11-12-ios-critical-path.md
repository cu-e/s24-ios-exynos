# Critical path from the current PID 1 to the first real iOS lock-screen frame (2026-11-12)

Purpose: re-anchor the task chain on the end goal (real Apple userland, launchd, backboardd, SpringBoard, lock screen, home screen, one real app) and stop treating
log transport, display diagnostics or test tooling as goals of their own. Anything below that is not on this path is demoted until it removes a named obstacle.

## Evidence vocabulary (used in every row below)

| Word | Meaning here |
| --- | --- |
| written | code or text exists in the tree; nothing was built or run |
| built | compiled/packaged on the host; no behaviour claimed |
| model-tested | host tests or simulation passed; says nothing about the S24 |
| ran on S24 | executed on this phone and observed through the project's own log chain (native-device evidence) |
| real iOS UI | a frame of Apple's own SpringBoard/lock screen was shown by the phone's panel (nothing has reached this level) |

Claims taken from donor repositories (`references/ios-lemonadep`, `ios-apollo`, `y2sios`, `s24-port`) are **source-review of someone else's README**, not evidence about this phone.
Only `references/s24-port` and `hakios-e1s-tools` are source we build; the other donor checkouts here contain only a README/notes file (and one patch), so their kernel patch series is not available locally for review yet.

## 1. Audit of the selected profile and local components

Selected profile (docs/implementation.md, CAPABILITIES.md): **iPhone X (iPhone10,3, D22AP, t8015) iOS 16.5 (build 20F66)** userland on **XNU 8796.121.2** (HackiOS base d82c64a3) for **SM-S921B/e1s**.

| Item | Needed for | Local state (searched 2026-11-12) | Evidence class | What closes it |
| --- | --- | --- | --- | --- |
| iOS version, arch, kernel match | everything | Target: arm64 (A11, non-arm64e) 16.5/20F66. Our kernel prints `Darwin Kernel Version 22.5.0 ... DEVELOPMENT_ARM64_E1S` (the iOS 16.5 family, xnu-8796). The exact string of the 20F66 kernelcache has not been compared because no IPSW exists here. | kernel line: ran on S24; version equality with the IPSW: unknown | `BuildManifest.plist` + kernelcache of the supplied IPSW |
| Restore image (IPSW) with the OS, SystemOS and AppOS disk images, `DeviceTree.d22ap.im4p`, `BuildManifest.plist` | root file system, dyld, shared cache, launchd, SpringBoard, backboardd, all frameworks | **ABSENT.** No `*.ipsw`, `*.dmg`, `dyld_shared_cache*`, `BuildManifest*`, real `launchd`/`SpringBoard`/`backboardd` anywhere in the repo, `references/`, `artifacts/` or the home directory (depth 4). `references/theos-sdks-ios165` is text stubs (`.tbd`, headers, swiftinterface; no binaries). RES-008 records "No SDK or Apple userspace has been acquired". | none | external input, see section 4 (IOS-001) |
| dyld + dyld shared cache compatibility | milestone 2 | Not available. In iOS 16 the cache and `/usr/lib/dyld` come from the OS/SystemOS images, not from the SDK. A11 userland is plain arm64 (no PAC). Donor claim: the same cache runs on non-Apple cores (Snapdragon 865/888, Exynos 990). The Cortex-X4/A720/A520 cluster of the S24 is untested (EL0 cache maintenance, counters, JIT paths are the known risk areas in the donors' notes). | donor claim | run a dynamic Mach-O from the real root (milestone 2) |
| Mach-O exec and PID 1 | milestone 1 | Project's own static Mach-O was exec'd by the kernel as PID 1 on the S24; `open`, `write`, `getpid`, `select`, `exit` worked; console text reached the host (NAT-068). It exited by design after ~1 s and the kernel panicked at "initproc failed to start" as predicted. `cpus=1`. Touch and battery drivers had to be switched off by boot-arg (touch driver GPIO defect is still in the source). | ran on S24 | stay-alive PID 1 + timed return (milestone 1 remainder) |
| Apple `launchd` start-up | milestone 3 | Nothing of Apple's ran. Kernel policy modules are **stand-ins**: the log prints `Security policy loaded: Apple Mobile File Integrity (stand-in)` and `Seatbelt sandbox policy (stand-in)`. Donors needed further kernel work for launchd (boot-args `launchd_unsecure_cache=1`, `unentitled_ios_sim_launch=1`, `ignition_level=1`, `wdt_test=no_user_checkin`, a permissive sandbox, AppleKeyStore selectors, SHA/MD5, an HFS+ or APFS root). Which of these our tree needs is **not measured**; the donor patch series is not checked out. | donor claim | IOS-003 (gap matrix) then milestone-3 runs |
| Services, syscalls, IPC, configuration | milestone 3-5 | Unknown by design: the list must come from launchd's own failures under our kernel (job cache, plist patching as in `s24-port/tools/e1s/patch-launchd-plist.py`, `/product` tree in the ADT). The ADT already carries an iPhone X `/product` tree (14008 bytes; MobileGestalt needs it). | partly model-tested (ADT), rest unknown | milestone 3 runs |
| Graphics stack dependencies | milestones 4-5 | `MiniIOMobileFramebuffer` exists in our kernel and ran on the S24 (`display 1125x2436 on a panel of 1080x2340 (4320 bytes per row)`, NAT-068 log). IOSurface root service, AppleCLCD selectors and the render path that backboardd takes on 16.5 without a GPU are **not verified**. | partial: ran on S24 for the framebuffer service only | milestone 4 |
| Separate system image + temporary writable overlay, no Android partitions | milestone 2 on | Constraints, all measured/recorded: RAM visible to Android 7.06 GiB (DEV-001); the RECOVERY test slot is 96 MiB and is the only authorized writable partition (decision 0019); no Android partition may be used; the project's USB log channel is control-transfer only, high speed, no bulk endpoints, loader-time only (NAT-041); the loader's own watchdog (CL0 at 0x10040000, 83 s, `s5e_wdt_pet/disarm` exist in the loader library) bounds every run. Donors put the iOS root in `userdata` or the tail of `super` - **not allowed here**. A trimmed donor root is reported at about 2.3 GiB, which would fit RAM. Therefore the root must be delivered into RAM from the host (or served by a kernel USB block driver), and the writable overlay must live in RAM. | recorded constraints; delivery path written nowhere yet | NAT-073 (delivery design), then implementation |

## 2. Milestones and their state

| # | Milestone | State now | Earliest blocker |
| --- | --- | --- | --- |
| 1 | Stable minimal XNU with a live user process and diagnostics | **Partly ran on S24** (NAT-068): kernel to `bsd_init: done`, PID 1 executed, text reached the host. **Not met:** PID 1 does not stay alive; the host sees the kernel log only at return; the timed `loader_return_after` return never ran (every run returned through the panic path); every run is capped by the 83 s watchdog / ~57 s loader deadline. | no kernel-side watchdog keepalive with a deadline, untested timed return |
| 2 | Compatible dyld + a dynamically linked program from the chosen iOS | nothing | **no Apple userland on the host** (IOS-001); then delivery of a ~GiB root into RAM (NAT-073) |
| 3 | Apple `launchd` and the minimum services | nothing | milestone 2; kernel gap list (IOS-003) |
| 4 | User process to physical display: buffers, interfaces, frame presentation, panel update | `MiniIOMobileFramebuffer` present and reporting; the kernel console paints the loader's framebuffer (1080x2340, stride 4320, phys 0xfa200000). Which buffer the panel scans out and whether the panel follows CPU writes there is **unmeasured** (NAT-069/NAT-070 asks exactly this). No user-space presentation path exists. | the scan-out fork (see section 3) |
| 5 | backboardd + real SpringBoard | nothing | milestones 2-4 |
| 6 | Real lock screen, input, home screen | nothing; touch driver has a known GPIO defect | milestone 5; UI-004 |
| 7 | Home screen with icons, one real app, home, relock | nothing | milestone 6 |
| 8 | Stability, GPU, smoothness, power, other devices | out of scope until 7 | - |

## 3. Can the graphics stack produce a first frame without a GPU driver?

**Not proven for this phone.** What exists is donor testimony only: `ios-lemonadep` says CoreAnimation renders in software and the frames are copied into the bootloader's framebuffer, presented to iOS as an iPhone X panel
(1125x2436) through kernel `IOSurface` + `IOMobileFramebuffer` services, with backboardd, SpringBoard and lock screen reported working on iOS 16.7.16; `y2sios` (Exynos 990, XNU 8796.121.2, iOS 16.5 - the same kernel base and iOS version as ours) lists a
"CPU copy with tear control" display path and an OpenGL ES fallback for CoreAnimation, but its headline rendering is Metal on the Mali. No claim here that software rendering is available until a real 16.5 `backboardd` produces a frame under our kernel.
If the first test shows `backboardd` refuses to start without a Metal/GL device, the minimal GPU path (kernel Xclipse backend + Metal frontend: GPU-007/GPU-009) joins the critical chain at that point; it is not scheduled before that fact.

The scan-out fork (milestone 4) that can be decided on the host plus one run:

| Observation (NAT-070, from NAT-069's `e1sdisp=2` dump of DECON/RDMA/DSIM registers) | Decision |
| --- | --- |
| an enabled RDMA reads from the loader's framebuffer address, DECON runs, DSIM link is up | S-Boot's scan-out can be reused: milestone 4 = CPU/IOSurface copy into that buffer through `MiniIOMobileFramebuffer` (donor method); UI-003 (full DECON/DSIM bring-up) stays off the critical path |
| the pipeline is idle or reads another buffer | milestone 4 needs a real display driver (UI-003) before any iOS frame can appear; schedule it ahead of milestone 5 |
| a register read faults or hangs | the display block is not reachable in the loader's power/clock state; the fix is a loader-side power-domain step (separate task) |

## 4. External inputs (the only items the owner has to supply)

| ID | File / data set | Purpose | Lawful way to obtain | Completion check |
| --- | --- | --- | --- | --- |
| IOS-001 | The iPhone X (iPhone10,3 / D22AP) iOS 16.5 build 20F66 restore image (`*_Restore.ipsw`, several GB) | the only source of the real OS/SystemOS/AppOS disk images (rootfs, dyld, shared cache, launchd, SpringBoard, backboardd, all frameworks), the D22AP DeviceTree `/product` tree and the matching kernelcache version string | Apple publishes IPSW files on its own update CDN without authentication; the owner downloads their copy from Apple (the installer licence restricts use to Apple-branded hardware - the owner's decision and responsibility, recorded here without a legal conclusion). Place it at `artifacts/apple-inputs/` (git-ignored). Do not commit it; do not run donor install scripts. | `tools/ios/ipsw_inspect.py` reports `ProductBuildVersion 20F66`, `iPhone10,3` in the supported product types and the SHA-256 of each image (IOS-002) |

Nothing else is requested. Firmware from the phone and every other input already exists or is produced by the host.

## 5. Shortest justified path from today's PID 1

1. **Close milestone 1** (no Apple files needed): kernel-side watchdog keepalive until a boot-arg deadline, so a run can last minutes with a verified stop (the keepalive stops at the deadline and the loader's watchdog then resets); first exercise of the timed `loader_return_after` return; a PID 1 that stays alive and prints a heartbeat (the s24-port stage-0 init already does). One run, three separable log signatures (NAT-071 host, NAT-072 native).
2. **Fork milestone 4** with the display register dump (NAT-069 host, NAT-070 native) - already built, cheapest run that decides whether UI-003 is on the critical path.
3. **Root delivery design** (NAT-073): host-only. Chooses between (a) a loader-staged RAM root received over a new DWC3 bulk-OUT endpoint with the watchdog kept alive during the transfer, and (b) a kernel USB block device. Measures RAM budget from the live DTB/kernel log first. Default recommendation: (a), because it needs no kernel USB driver and the loader already owns the DWC3 bring-up; the root size limit (about 3 GiB of RAM) is acceptable for iPhone X userland (3 GB device) and is re-checked when IOS-001 yields real sizes.
4. **When the IPSW exists:** inspect it (IOS-002), build a trimmed read-only root (APFS image via the pinned `mkapfs.py`, or HFS+ from the pinned apple-hfs source if our kernel gets that driver - decided by IOS-003), run milestone 2 (real `dyld` + shared cache + a dynamically linked program), then launchd with daemons added one job at a time, then backboardd, then SpringBoard.

**Earliest unresolved blockers:** (a) *external*: no Apple userland on the host (IOS-001); (b) *engineering, available now*: milestone 1 is not closed - PID 1 does not stay alive and the run length is capped by the 83 s watchdog, so no multi-minute launchd bring-up can be observed. The work started below is (b), plus the already-built display question.

## 6. Immediate blockers (what / observed by / minimal change / done when / prepare without the phone)

| Blocker | What is missing | Confirmed by | Minimal change or input | Ready when | Without the phone |
| --- | --- | --- | --- | --- | --- |
| IOS-001 | Apple userland | repo/home search above; RES-008 | owner supplies the IPSW | inspector accepts it | inspector tool + synthetic-zip tests (IOS-002) |
| M1 length cap | multi-minute runs; stay-alive PID 1; timed return | NAT-068: PID 1 exit at +1.0 s, panic return; 83 s watchdog (NAT-046/048) | kernel keepalive thread bounded by a boot-arg deadline; heartbeat init | one run: heartbeat lines >= 2 spaced 5 s, `loader_return_after` return reason in the loader note, host receives the log | patch + host tests + decision draft (NAT-071) |
| Scan-out fork | which buffer the panel shows | no measurement exists | `e1sdisp=2` (read-only DECON/RDMA/DSIM/DCPHY dump) | analyser prints parsed pipeline state and the fork decision above | build, tests, decision draft (NAT-069) |
| Root delivery | a way to hold a ~GiB root without Android partitions | RECOVERY slot 96 MiB; control-only USB; RAM 7.06 GiB | decision between loader bulk-OUT staging and a kernel USB block device | written design with RAM/throughput/watchdog numbers and a host test plan | all of it (NAT-073) |
| Kernel gaps for launchd | list of kernel features Apple launchd/backboardd need | donors report AMFI/sandbox/keystore/HFS+/IOSurface work; our log shows AMFI and Sandbox as stand-ins | fetch and pin the donor patch series, map each item to our tree | matrix with present/missing/unknown per item | all of it (IOS-003) |

## 7. Experiments on the phone: question, observable, decision (fixed in advance)

| Task | Question | Observable | Decision |
| --- | --- | --- | --- |
| NAT-070 | Does the display engine scan out the loader's framebuffer? | parsed `e1s-display:` pipeline lines vs `phys 0xfa200000`; chain verdict PASS | section 3 table |
| NAT-072 | Can a run last minutes with a verified stop, and does the timed return work? | heartbeat lines with kernel stamps >= 5 s apart; loader return reason; keepalive stop and no watchdog reset before the deadline | if yes: milestone 1 closed, launchd bring-up uses N-minute runs; if the keepalive does not hold the watchdog: stay with bounded < 57 s runs and put the USB-in-kernel log task on the path |

## 8. Task map

IOS-001 (blocked, external) - IOS-002 (inspector, host) - IOS-003 (kernel gap matrix, host) - NAT-069/070 (display fork) - NAT-071/072 (milestone 1) - NAT-073 (root delivery, host).
Not on the path now: UI-003/GPU-007/GPU-008/GPU-009 (wait for the fork and the first backboardd result), eSIM/Wi-Fi/Bluetooth/cellular tasks, any further log-transport work beyond what milestone 1 needs.
