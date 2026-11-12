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

## 0. Status update, 2026-11-12 after NAT-075 (this section replaces sections 2, 5, 6 and 8 where they differ)

Earlier text below was written before the IPSW existed; the rows and statements it makes about IOS-001, root delivery and milestone 1 are historical.

| Item | State | Evidence class |
| --- | --- | --- |
| IPSW (iPhone10,3, 20F66) | present, accepted by the project inspector; Apple files stay under gitignored `artifacts/` | host-test (IOS-001/002) |
| Root image | the donor recipe (hakios @87bf4851, `unpack.sh`, `build.sh`, `mkapfs.py -z`) ran unmodified on the host: `system.apfs` 2,475,712,512 B (2.31 GiB); Apple's own `/sbin/launchd`, dyld and the shared cache are in it | built + host-checked (IOS-009/010); **nothing of it has run on the S24** |
| Static readiness audit | all six programs (dyld, launchd, xpcproxy, amfid, backboardd, SpringBoard) are plain arm64 with their closure resolved; 22 syscalls are unimplemented in our kernel; unknown without a run: dyld commpage offsets +0xd0/+0xd8/+0x10c and the Apple system register `S3_6_C15_C1_5` | source-review (IOS-012) |
| First frame without a GPU | plausible (QuartzCore has a software renderer; the donor reports it working on other phones), **not proven**; 63 IOMobileFramebuffer and 43 IOSurface selectors are asked, the stand-ins handle 16 and 18 | source-review (IOS-013) |
| Root delivery without Android partitions | design chosen (NAT-073): bulk-OUT into a reserved RAM region inside the payload's `kernel_end`, kernel exposes it as `md1`. **Measured on the S24 (NAT-075, decision 0029):** 4096 MiB loader window, XNU with 16 KiB pages (262144 pages), reserve-only `md1` of 2,475,720,704 B registered, probe PID 1 ran (exit 81), watchdog pet kept the run alive to the 150 s cap (Download Mode at +177.9 s, not SEC_UPLOAD at ~+95 s). **No byte was delivered yet.** | native-device (NAT-075) for the listed facts |
| PID 1 | the project's own probe ran as PID 1 (NAT-068, NAT-075); Apple's launchd did not | native-device (probe only) |
| Display | no iOS pixel has been shown; scan-out fork unmeasured (NAT-069/070) | - |

**Shortest justified path from today's PID 1 to the first real SpringBoard/lock-screen frame**, each step with its observable:

1. *Deliver the root (earliest unsolved blocker).* NAT-076 (bulk-OUT receive engine + host sender, host-test) and NAT-077 (probe PID 1 that hashes `/dev/rmd1` with the MMU on, host-test), then NAT-078 (one native run: send 2.31 GiB, the probe prints the SHA-256 and elapsed time; pass = digest equals the host's and the transfer fits the cap). Open numbers: the USB rate (2.31 GiB in under about 120 s needs at least 20 MB/s; USB 2.0 high speed bulk gives about 30-40 MB/s on a good host, unmeasured here); whether anything feeds the 83 s watchdog while the kernel runs (NAT-071); 1.61 GiB of free RAM after the reserve.
2. *Mount the APFS root from md1 and run Apple's dyld with a dynamically linked program* (milestone 2): the kernel's root mount of an APFS image from `md1` (what the kernel needs is listed in the IOS-003 matrix; not yet tried), the 22 missing syscalls and the three dyld commpage offsets are the expected stops; the first observable is dyld's own exit/log text on the host chain.
3. *Apple launchd with a pruned job set* (milestone 3), then daemons one at a time; the kernel stand-ins (AMFI, sandbox) and keystore selectors are the likely stops.
4. *Graphics path* (milestones 4-5): decide the scan-out fork (NAT-070), then a dynamically linked test program that opens `IOMobileFramebuffer`/`IOSurface` (IOS-013 step 3), then backboardd with the donor's injected library, then SpringBoard.

Nothing in steps 2-4 has any evidence on this phone. The earliest blocker is step 1; everything after it is blocked behind root delivery, not behind graphics.

## 0b. Status update, 2026-11-12 after NAT-078 and NAT-083 (this section replaces section 0 where they differ)

What changed since section 0: the root is **delivered** (NAT-078, native-device) and a **bootable** variant of it exists on the host (NAT-083, built + host-checked). Everything below separates the five evidence words of the vocabulary above.

| Item | written | built | model-tested | ran on S24 | real iOS UI |
| --- | --- | --- | --- | --- | --- |
| Project XNU payload kernel to `bsd_init`, PID 1 (own probe) | yes | yes | yes | **yes** (NAT-068/075/078) | no |
| Bulk-OUT receive engine, loader variant, host sender | yes | yes | yes (NAT-076/079/080) | **yes** (NAT-078: 2,475,720,704 B in 152.98 s, 16.18 MB/s, 0 errors) | no |
| DWC3 DMA into RAM above 4 GiB (NAT-040 U5) | - | - | - | **yes** (PA 0x902d7c000) | no |
| Root readable through `/dev/rmd1` with the MMU on | yes | yes | yes | **partly**: 59.6% (1,476,395,008 B) hashed, 11 digests equal the host's; the other 40.4% unread | no |
| APFS root image (Apple's launchd, dyld, shared cache, backboardd, SpringBoard inside) | donor recipe | yes (`system.apfs` 2.31 GiB, `apfsck` clean, 62,258 entries read back) | host-checked | **no** (never mounted by the S24 kernel) | no |
| Stage0 + init + small root for `rd=md1` (NAT-083, `/dev/md1`→`/dev/md0`) | yes | yes | host-checked (`apfsck`) | no | no |
| Apple dyld, Apple launchd, backboardd, SpringBoard | - | present in the image | static audit only (IOS-012) | **no** | no |
| Display scan-out registers (read-only dump) | yes | yes | yes (39 tests, 63/65 mutants) | **yes** (NAT-070, decision 0031: 7 windows read, no abort; fork label `decon-running-no-enabled-rdma`, re-read below) | no |
| A frame from a user process on the panel | - | - | - | **no** | no |

Nothing in the table has put an Apple instruction on the S24 yet; the highest rung reached is "our own static Mach-O ran as PID 1 and the host read its text".

### Audit of the selected profile (what is known, from what, and what stays unknown)

| Question | Answer | Class | Unknown / next check |
| --- | --- | --- | --- |
| Exact version, architecture, kernel match | iPhone X (iPhone10,3, D22AP, t8015) iOS 16.5 (20F66), arm64 without pointer authentication; project kernel `xnu-8796.121.2` `DEVELOPMENT_ARM64_E1S` (Darwin 22.5.0 = the iOS 16.5 family) | host-test (IOS-002), ran on S24 (kernel banner) | kernel-vs-userland interface is only exercised by running the userland (milestones 2-3) |
| Userland files and libraries | six programs audited: `dyld`, `launchd`, `xpcproxy`, `amfid`, `backboardd`, `SpringBoard`; all plain arm64; the closure of each resolves inside the 43-file, 2,710-image shared cache; 0 required libraries missing; `backboardd` links 46 libraries directly (299 images in the closure) | source-review of the IPSW (IOS-012) | symbol presence is not compatibility; only a run shows that |
| dyld / shared cache | the cache is mapped by dyld from the OS cryptex; the shared region (address range, size) fits our kernel's `vm_map` setup; commpage fields at offsets +0xd0, +0xd8, +0x10c, +0x105 are read by Apple's dyld/libsystem but undefined in the open `cpu_capabilities` header | source-review (IOS-012) | whether Apple code reads them before anything prints; first observable = dyld exit/log text |
| Apple launchd compatibility | not run; the kernel's AMFI and Seatbelt are stand-ins (the log says so); donors set `launchd_unsecure_cache=1`, `cs_enforcement_disable=1` (already in our command line), `wdt_test=no_user_checkin` | donor claim + kernel log | which of the donor kernel deltas our tree lacks is measured by running launchd (milestone 3) |
| Syscalls, system registers, IPC | 22 syscalls the userland may call are unimplemented (`nosys`): 251-256, 258-265, 293, 337, 418, 419, 483, 493, 519, 535; Apple system registers `S3_6_C15_C1_5` and `S3_4_C15_C10_6` appear in the cache | source-review (IOS-012) | which of them is hit before the first launchd job: unknown until the run |
| Services / configuration | launchd needs a job set, `/product` in the ADT (the ADT carries the iPhone X tree, 14,008 B), keystore selectors, `/private/var` | partly model-tested | milestone 3 runs, one job at a time |
| Graphics: backboardd | links `IOMobileFramebuffer`, `QuartzCore`, `Metal`, `IOSurface`, `IOKit`, `BackBoardServices`, `CoreBrightness`, `CoreGraphics`, `CoreMotion` and the HID libraries directly; `SpringBoard.app` is a thin launcher for `SpringBoard.framework` | source-review (IOS-013 + `otool -L`) | whether `backboardd` runs without a `MTLDevice` is **not known** |
| Graphics: kernel side | `MiniIOMobileFramebuffer` answers 16 of the 63 constant selectors the userland asks (4 named, 43 unnamed); the IOSurface service answers 18 of 43 (4 named, 21 unknown); the framebuffer reports 1125x2436 on a 1080x2340 panel | source-review (IOS-013), partial run on S24 (framebuffer report) | selectors that fail show up as the first user-visible errors; the 1125x2436 vs 1080x2340 mismatch needs a scaling decision |
| First frame without a full GPU driver | **plausible, not proven**: QuartzCore has a software renderer path and the donors report frames this way on other SoCs; if `backboardd` or SpringBoard demands a Metal device, the minimum GPU path (GPU-007/GPU-009) joins the critical chain at that point. No software-rendering promise is made | donor claim only | first observable: `backboardd` stays alive and creates an IOSurface-backed layer tree |
| Separate system image + temporary writable overlay, no Android partition | the root is a read-only APFS container delivered into the 2.31 GiB `md1` reserve (RAM only, nothing written to flash); the donor's `init` gives `/private/var` a **memory filesystem** when no `var_hfs=` device is given, so the writable part is also RAM. 16 KiB pages, 4 GiB window: after the reserve ~1.61 GiB (105,775 pages) is free for the kernel, `launchd`, `backboardd`, SpringBoard and the overlay. An iPhone X has 3 GB, so the budget is tight, not impossible; the levers are a larger loader window (the phone has 7.06 GiB visible), a trimmed root (apps removed) and `fs.compressed` (the root is already built with `mkapfs.py -z`) | native-device (memory and delivery), source-review (donor init) | the real working set of `backboardd` + SpringBoard on this kernel is unmeasured |

**Missing components: none that the owner has to supply.** The IPSW (IOS-001) is in place and accepted. The things that could still be missing are *measurements and project code*, not files: the S24-specific display tables come from the phone itself (own device, read-only register reads over the project's log chain); donor repositories are public and pinned (`research/sources.json`); no Apple file is ever committed. If a later run proves a specific file absent (for example a second IPSW for a different build, or a firmware blob for a peripheral), the entry goes into section 4 with its purpose, the lawful route (Apple's public CDN for the IPSW, the owner's own handset for S24 firmware) and the completion check, before anyone waits for it.

### NAT-070: what the display registers say (native-device, one read at kernel time 40.5 s; decision 0031)

Question asked in advance: do DECON, the DECON0 windows, the RDMA channels, DSIM0/1, DCPHY0 and DPU_MIPI_PHY_CON describe a running pipeline that reads the loader's framebuffer? Observable: the `e1s-display:` lines parsed by `analyze_nat069.py`. The run read all seven windows without an abort or hang; the kernel then ran the project's probe as PID 1 (exit 81, as in NAT-068) and returned its text to the host; the phone went to Download Mode at +79.8 s and was restored (stock RECOVERY hash, Android booted, `assess` pass).

| Register group (as printed) | Value | Reading |
| --- | --- | --- |
| framebuffer | 1080x2340, 32 bpp, stride 4320, phys `0xfa200000`; first words `0xffffffff` | same as NAT-068 |
| DECON0 | `GLOBAL_CON` 0x133 (bit 8 command mode, bit 4 running, bits 1/0 enable), frame counter 1,686; DECON1-3 `GLOBAL_CON` 0x20, counter 0 | DECON0 is running in **MIPI command mode** and has sent frames |
| DECON0 windows | win2 `0x1` and win3 `0x11` on, both (0,0)-(1079,2339), win0/1 off | two full-screen windows, mapped to channels 0 and 1 (CHMAP = bits 7:4) |
| RDMA0, RDMA1 | frame 1080x2340, format 0, base `0xfa200000`; RDMA2/3: all zero | both active channels are set up on exactly the console framebuffer |
| RDMA "enable" word | `0x40000000` on all four channels, including the empty ones | the analyser decodes bit 0 as "on" (UI-007 assumption); the donor's S9 driver (`hakios.exynos_dpu.c`, from Samsung's dpu_9810) defines only bit 2 = busy and bit 4 = SFR update force for this word, so bit 0 is not shown to be an enable bit and bit 30 is not explained |
| DSIM0/1 | link in stop state, no video mode, PLL/HS clock not running | consistent with a command-mode link between updates (the S9 donor's panel is command-mode; this panel's mode is inferred from DECON0 `GLOBAL_CON` bit 8 only); the status-bit decode is also the patch's assumption |
| DCPHY0 / DPU_MIPI_PHY_CON | PLL lock 1, ready 1, enable 1 / 1 | the D-PHY is powered |

**Formal result (pre-registered, analyser unchanged): `display.fork = decon-running-no-enabled-rdma`**; the decision text for that label was "revisit the dump window or channel choice before any decision". **Reading of the same numbers against the donor** (source-review, not a new measurement): the structure matches what the S9 donor documents for S-Boot's hand-over (DECON0 in command mode, frames started by the panel's TE, windows on DMA channels that read the boot framebuffer), and the label comes from a bit decode that the Samsung-derived sources do not support. This makes "S-Boot's scan-out can be reused" the working assumption for milestone 4: the baseline is to draw into the boot framebuffer through `MiniIOMobileFramebuffer` (the donor's method, accepting tearing), and the tear-free refinement is to write the new buffer's address into the channel's base-address register and request a shadow update. **Not established:** that the panel shows what the CPU writes there. A command-mode panel updates when a frame is triggered, and only a view of the panel (or the registers that the dump did not include: `HW_SW_TRIG_CONTROL`, `SHADOW_REG_UPDATE_REQ`, `DATA_PATH_CONTROL_0/1`, the IDMA interrupt word, and a second read of the frame counter) can decide it. UI-003 (a full DECON/DSIM bring-up) is therefore off the critical path **provisionally**, and a failed visibility check moves it back.

### Shortest justified path from today's PID 1 to the first real SpringBoard/lock-screen frame

1. **Make the delivered root the kernel's root and read it through the real filesystem** (NAT-083, earliest unsolved blocker). The kernel must mount the 2.31 GiB APFS from `md1` (`rd=md1`, the donor `apfs` VFS is already in `kernel.no-storage`), exec stage0 as `/sbin/launchd`, which mounts the small image on `/redwood` and runs `init`. Observable on the host: stage0 lines, the `/redwood` mount, init's check lines. This is the first moment an Apple-built binary (the dyld or launchd file inside the image) can be opened by our kernel.
2. **A PID 1 that stays alive** (NAT-071/072): every run to date has been cut at 45-150 s by `loader_return_after` or the 83 s watchdog; Apple's boot takes longer than that. Needs the kernel-side keepalive with a deadline and a verified stop.
3. **Apple dyld + a dynamically linked program, then Apple launchd** (milestones 2-3): expected stops are the 22 `nosys` syscalls, the commpage fields and the two system registers; each stop is read from the host chain and fixed in the kernel.
4. **A graphics path** (milestone 4): the NAT-070 fork (below), then a dynamically linked test program that opens `IOMobileFramebuffer`/`IOSurface` (IOS-013 step 3), then `backboardd` with the donor's injected library, then SpringBoard.

The earliest unresolved blocker is step 1 (the APFS root has never been mounted by this kernel). Work on it starts with the NAT-083 loader/payload variant.

### Blocker blocks (a: missing/broken, b: confirming observation, c: minimal change or input, d: ready when, e: prepared without the phone)

| Blocker | a. Missing / broken | b. Confirming observation | c. Minimal change / external input | d. Ready when | e. Without the phone |
| --- | --- | --- | --- | --- | --- |
| **B1 APFS root from md1** (NAT-083) | the kernel has never mounted the big APFS as root; the project's `md0` is the small payload ramdisk and `md1` the delivered reserve, the opposite of the donor; stage0 hardcoded `/dev/md1` | NAT-078 read `/dev/rmd1` with the MMU on (59.6% matched); `mockfs_mountroot` has no mount point (read in source) so `mockfs` cannot mount it | `rd=md1` + stage0 `/dev/md1`→`/dev/md0` (done on the host: 3 counted substitutions, `apfsck` clean); loader/payload variant with the 4 MiB small root as `md0`; the same delivery loader (NAT-079) | one run: the kernel log shows the APFS root mounted and stage0 printing its lines on the host chain; the whole-image digest matches the host's (NAT-081 probe fix) | root image, stage0, loader variant, packaging, decision file, analyser, tests |
| **B2 PID 1 that stays alive** (NAT-071/072) | the kernel returns after a timeout or on panic; the 83 s watchdog is fed only by the loader; kernel text reaches the host only at return | NAT-068/075/078: returns at 45-150 s; NAT-078: unpetted kernel ran 45 s without SEC_UPLOAD | kernel-side watchdog pet with a boot-arg deadline; heartbeat PID 1 | one run: heartbeat lines ≥2 spaced 5 s, the loader's return reason in its note, host receives the text, no watchdog reset before the deadline | patch against the pinned kernel, host tests, decision draft |
| **B3 dyld/launchd kernel gaps** | 22 `nosys` syscalls, 3 commpage offsets, 2 Apple system registers, stand-in AMFI/Seatbelt | IOS-012 static list; first run of Apple's `dyld` will name the actual first stop | implement or stub exactly the entries the first stops name; no wholesale clone of the donor series | `dyld` runs a dynamically linked test program to `exit(0)` and prints, on the S24 | donor-delta matrix per syscall/sysreg (IOS-003), unit tests of each stub against Apple's call sites |
| **B4 scan-out** (NAT-070 done, see the reading below) | whether a CPU write to `0xfa200000` reaches the panel; the exact trigger/shadow-update registers on the S24 (the dump had no `HW_SW_TRIG_CONTROL`, `SHADOW_REG_UPDATE_REQ`, `DATA_PATH_CONTROL`, IDMA IRQ words) | NAT-070 (native-device): DECON0 in command mode and running (`GLOBAL_CON` 0x133, frame counter 1,686), windows 2 and 3 on, full-screen, mapped to channels 0 and 1; RDMA0/1 are set to 1080x2340 at 0xfa200000, the console framebuffer; DSIM0/1 in stop state (no video mode) - the same structure the donor documents for the S9 (S-Boot leaves a command-mode DECON0 reading the boot framebuffer) | take the donor's baseline: draw into the boot framebuffer; later the tear-free flip (IDMA base address + `SHADOW_REG_UPDATE_REQ`) after a second dump that adds those registers | a user-process frame visible on the panel (needs one look at the panel or a second observable; see below) | donor-driver comparison, register-decode fix in the dump, next dump variant |
| **B5 userland graphics path** | selector coverage (63/16 and 43/18), 1125x2436 vs 1080x2340 scaling, backboardd's Metal dependency | IOS-013 counts; a dynamic test program's first failing selector | extend the stand-in services only for selectors the test program/backboardd actually fails on; scale or crop decision | `backboardd` alive with a layer tree; one IOSurface frame copied to the scanned-out buffer | selector tables, a pure-C test program for the copy path |
| **B6 memory budget** | ~1.61 GiB free after the 2.31 GiB reserve; the working set of SpringBoard on this kernel is unmeasured | NAT-078 kernel text: 105,775 free + 156,369 wired pages of 16 KiB | measure; if needed raise the loader window above 4 GiB or trim the root | `vm_stat`-equivalent from a running userland shows ≥300 MiB free with SpringBoard up | loader window analysis; root trim list (apps not needed for the lock screen) |

### Milestones against the vocabulary

| # | Milestone | highest rung reached | Not reached |
| --- | --- | --- | --- |
| 1 | stable minimal XNU, user process, diagnostics | ran on S24 (own PID 1, text on the host) | PID 1 stays alive; timed return (B2) |
| 2 | compatible dyld + dynamically linked program | built (the files exist in the image) | mounted, run (B1, B3) |
| 3 | Apple launchd + minimal services | built | run (B1-B3) |
| 4 | user process → S24 panel (buffers, interfaces, presentation) | ran on S24: registers read (NAT-070); written: stand-in `MiniIOMobileFramebuffer` | whether the panel shows CPU writes (B4); user-space path (B5) |
| 5 | backboardd + real SpringBoard | none | milestones 2-4 |
| 6 | real lock screen, input, home screen | none | milestone 5; touch driver GPIO defect |
| 7 | icons, one real app, home, re-lock | none | milestone 6 |
| 8 | stability, GPU, smoothness, power, other devices | none | milestone 7 |

## 0c. Status update, 2026-11-12 after NAT-084/086/088/089/090 (this section replaces 0b where they differ)

What changed since 0b (every row names its highest rung with the five words of the vocabulary):

| Item | written | built | model-tested | ran on S24 | real iOS UI |
| --- | --- | --- | --- | --- | --- |
| Delivered 2.31 GiB APFS root mounted by the kernel as root from RAM (donor `apfs` VFS) | yes | yes | yes | **yes** (NAT-084, decision 0032) | no |
| stage0/init, then Apple's own `df`, `mount`, `ps`, `vm_stat` (IPSW programs, run through Apple's dyld and the shared cache) | yes | yes | yes | **yes** (NAT-084) | no |
| Apple's `launchd.darwin` as PID 1: boot tasks `fsck` .. `fips` (corecrypto FIPS self-test 18 of 18 passed), the keybag task died on the missing SEP-owned keybag | - | - | - | **yes** (NAT-084) | no |
| `ephemeral-storage=1` from the ADT: keybagd skipped, 11 more boot tasks, then `launchd_cache_loader` aborted (no `xpc/launchd.plist`) and XNU panicked by design | yes | yes | yes | **yes** (NAT-086) | no |
| Restore-mode launchd (last cmdline token ` xrd=md0`): 20 of 23 boot tasks skipped, 3 ran, one job (`ps -A` heartbeat) respawned every 10 s to kernel 244 s, timed return with a **live PID 1**, no panic | yes | yes | yes | **yes** (NAT-088; ladder row R9 = inconclusive, read by hand beyond the ladder) | no |
| Reader without the replay refusal, launchd boot-task analyser rows A1-A8, Stage A small root (19 Apple plists + heartbeat) | yes | yes | **yes** (NAT-089: 60 tests, mutation 535 candidates; the real NAT-088 text reads 3 ran / 20 skipped) | no | no |
| Stage A image `loader-diag-xnu-sa-md1` + session driver + decision 0035 | yes | yes | **yes** (NAT-090: byte-for-byte against NAT-087, 34 tests, mutation 105) | **no** (NAT-091 not run: the phone left the USB bus at 16:02Z, no write and no reboot, attempt unspent) | no |
| backboardd, SpringBoard, any Apple daemon but the heartbeat | present in the image | - | static audit only | **no** | no |
| Graphics: IOMobileFramebuffer/IOSurface stand-ins, a frame on the panel | yes | yes | host tests | registers read (NAT-070); **no frame** | no |

Milestones now: 1 reached (stable minimal XNU, user processes; a PID 1 that stays alive for the 63 s window); 2 reached for the four Apple programs that ran (dyld + shared cache + libSystem; whether any of the 22 `nosys` syscalls was called by them is not recorded, so this says nothing about daemons); 3 started: Apple launchd runs in restore mode with one job, no Apple daemon has run; 4-8 not reached.

**The earliest unsolved blocker is B7: no Apple daemon has ever run under this launchd.** Stage A (NAT-091) is the experiment that measures it; it was prepared and gated (preflight `ready-read-only`) and stopped before any write only because the phone left the bus.

What the image tells us about what is *not* there (host check of the IPSW root tree, `sbin/`, `bin/`, `usr/bin`): `/bin` holds only `df` and `ps`; there is **no shell, no `cat`, no `grep`, no `tail`, no `launchctl`** in the root. So no job can print a file or filter a log: every daemon's stderr (the plists send it to `/dev/console`) and launchd's own lines are the only reporters, and `ps -A` is the only state query. `backboardd`, `hidd`, `thermalmonitord`, `configd`, `lockdownd`, `SpringBoard.app` and the frameworks BackBoardServices, FrontBoard, IOMobileFramebuffer, IOSurfaceAccelerator and SpringBoard* are present; AGX frameworks are present as files, but the S24 has a different GPU (no AGX hardware), so nothing may be claimed about rendering through them.

### Blocker blocks, new rows (a: missing/broken, b: confirming observation, c: minimal change or input, d: ready when, e: prepared without the phone)

| Blocker | a | b | c | d | e |
| --- | --- | --- | --- | --- | --- |
| **B7 Apple daemons under restore-mode launchd** (earliest) | unknown whether the plists load at all: `LimitLoadToSessionType` on 8 plists vs the `user/501` domain seen in NAT-088; `Unable to find persona with type 6` (PERSONA_SYSTEM_PROXY: the project's XNU creates no persona); 22 `nosys` syscalls, AMFI/sandbox stand-ins | NAT-091: per-label spawns, exit lines with launchd's wording, domains, the last `ps -A` list, read by analyser rows A1-A8 | by the row: A2/A3 -> the earliest exit's cause is the next kernel/stub change; A4 -> create the persona or the session type before any daemon; A1 -> Stage B | A1: the seven self-starting daemons are in the last complete `ps -A` list, no panic | NAT-089/090, decision 0035, driver, gates (all done) |
| **B8 log window** | head 8 KiB + tail 32 KiB of the kernel buffer, run window ~63 s; donor reports ~1 MB of SpringBoard output in half a minute; no `cat`/`tail`/`grep` in the root | A8 rows (holes and gap sizes) in a real Stage A/B text | before Stage B: either per-daemon `StandardErrorPath` into a RAM file system plus a project-owned tiny reader job (own code, a confirmed gap: the root has no `cat`), or a larger return path; decide from NAT-091's measured volume | a Stage B text with the first backboardd lines without holes | measure Stage A output volume per label from NAT-091; design the reader job as a static Mach-O (NAT-077's mkstatic pattern) |
| **B9 graphics, still unproven** | no frame on the panel; whether a CPU write reaches it (B4); IOMobileFramebuffer 63 selectors / IOSurface 43 asked, 16 / 18 handled; AGX absent | a dynamically linked test program's first failing selector (needs an iPhoneOS SDK **or** an Apple-signed test program from the IPSW) | `hello_dyn` needs the iPhoneOS SDK, absent here: lawful routes are the owner's Apple Developer download of Xcode's iPhoneOS SDK (Apple's licence, stays under gitignored `artifacts/`), or reading backboardd's own first failing call instead of building a program | one frame of anything on the panel, observed by one look or a second observable | selector tables; a pure-C copy path to the boot framebuffer |
| **B10 Stage B injection library** (`libhakios.dylib`) | the donor starts backboardd with `DYLD_INSERT_LIBRARIES=/redwood/lib/libhakios.dylib` (`references/hakios/userland/src/inject.c`, 1,234 lines; source-review of the donor, **not evidence for this phone**): it forces CoreAnimation's software rasterizer, feeds a virtual HID touch service, skips the ambient-light wait, and tells containermanagerd that personas are unsupported (the same family as launchd's `persona type 6` line). The kernel side exists: the built payload carries `kern.exec_inject` and the `DYLD_INSERT_LIBRARIES=` environment code (strings of `Image.payload`, 7 hits), the AMFI stand-in lets dyld honour it. **The dylib itself does not exist here**: the donor builds it with `xnu-clang -isysroot theos/sdks/iPhoneOS16.5.sdk` + `ld64`, and neither the SDK nor `xnu-clang`/`ld64` is on this host; the donor's `prebuilt/userland` is tracked at the pinned commit but was outside the sparse checkout (this row said it was absent: wrong; IOS-014 fetched it, `research/notes/IOS-014-libhakios-prebuilt.md`: a donor-built binary older than the pinned source, static inspection only, not run) | the first backboardd lines with and without the library (Stage B text); whether the addresses the library patches inside the shared cache (checked by the library against expected bytes) match 20F66 | **external input, lawful routes:** (1) the owner downloads Xcode / the iPhoneOS 16.5 SDK from Apple Developer under Apple's licence and puts it under gitignored `artifacts/apple-inputs/`; (2) assemble the headers from Apple's open-source drops (CF-Lite, libdispatch, objc4, IOKitUser: APSL, pinned by SHA) plus `.tbd` stubs generated from the IPSW's shared cache; (2) is more work and can fail on private headers. A Darwin `ld64` (cctools-port, open source) is needed either way | `libhakios.dylib` built, its sha256 in the evidence, an image with the plist and `etc/inject.conf` host-checked; Stage B is run only after NAT-091's A1/A2 | header inventory done (host read of `inject.c`): it includes only public headers (`unistd`, `sys/*`, `mach/*`, `objc/runtime`+`message`, `notify`, `IOKit/IOKitLib`, `dispatch`, `CoreFoundation`, `dlfcn`, `pthread`) plus the donor's own `hakios.input.h` and `hakios.gl.h`; the private IOHID calls (`IOHIDVirtualServiceClientCreateWithCallbacks`, `IOHIDEventCreateDigitizerEvent`, ...) are declared `extern` inside the file, so route (2) does not need Apple's private headers, and the link can use `-undefined dynamic_lookup` instead of `.tbd` stubs (a proposal, not tried). Still to do: pin cctools-port (Darwin `ld64`) and the open-source header drops by SHA, and try a compile-only pass |

First frame **without** a full GPU driver: still *plausible, not proven* (QuartzCore's software renderer is reported working by the donor for other phones; here nothing ran). No software-rendering promise is made until backboardd or a test program shows it.

## 0d. Status update, 2026-11-12 after NAT-091/092/093 (this section replaces 0c where they differ)

NAT-091 ran the Stage A image once and the delivery stopped at the 240 s cap (91.82% at 10.10 MB/s, host load ~30), so launchd never executed. NAT-092 built the documented re-run image (byte-for-byte NAT-090's payload except name and tag). **NAT-093 ran it once** (decision 0036, 2026-11-12 16:59Z, host load 3.89): the whole root arrived (179.5 s, 13.79 MB/s). Pre-registered ladder rows: chain row 9, Stage A row **A8** (outcome *inconclusive*; the task stays open).

| Item | written | built | model-tested | ran on S24 | real iOS UI |
| --- | --- | --- | --- | --- | --- |
| Whole 2,475,720,704 B root delivered inside the 240 s cap | yes | yes | yes | **yes** (NAT-093; NAT-091's shortfall coincided with host load ~30, cause not proven) | no |
| Kernel mounts the delivered root; stage0/init 35/35 checks; Apple's `df`, `mount`, `ps`, `vm_stat` print (no EIO, unlike NAT-091) | yes | yes | yes | **yes** (NAT-093, head of the dump) | no |
| An Apple daemon other than launchd runs: `lsd` as pid 21, seen only as the kernel's CPU-monitor message (osfmk/kern/task_policy.c `task_set_cpuusage`) | plist in the image | yes | static only | **yes** (first Apple daemon observed; launchd's own spawn line for it was not seen) | no |
| The seven self-starting jobs, the `ps -A` lists, PID 1 survival to the end | yes | yes | yes | **not observed** (log window) | no |
| backboardd, SpringBoard, graphics | as in 0c | - | - | **no** | no |

What the surviving text shows (post-hoc reading, `docs/procedures/nat-093/`, written after the pre-registered analysers returned A8, not a ladder row): the collector's second boot kept 345 of 428 records, including 83 lost to ring-overrun drops with the `KL begin` record (NAT-089's reader needs it, hence A8). The dump is 170,097 bytes = an 8 KiB head (ends inside rc's `vm_stat` output, before launchd's first line) + a 32 KiB tail, with 129,137 bytes between them not sent. The tail (kernel clock 254.1-276.7 s) is 235 repeats of `process lsd[21] denied attempt to escape CPU monitor (missing required entitlement).` (about 10 per second) plus memorystatus lines for pids 26 and 27. No panic line and no PID 1 exit line is in the surviving 25 KiB; that is an absence in a window with holes, not a negative.

**The earliest unsolved blocker is still B7, now narrower: whether the seven self-starting Apple daemons stay up under restore-mode launchd.** One daemon is known to run. It is not known which others do, or whether PID 1 survives to the timed return in this configuration. The binding constraint on knowing is B8, not B7's cause.

| Blocker | a. Missing / broken | b. Confirming observation | c. Minimal change / input | d. Ready when | e. Without the phone |
| --- | --- | --- | --- | --- | --- |
| **B8 log window** (now binding) | head 8 KiB + tail 32 KiB of a 170 KB log; one chatty daemon (`lsd`, ~1 KB/s) fills the tail; the dump drops records when the producer overruns (collector start failures 205, timeouts 1280); the reader refuses a dump whose `begin` record is lost | NAT-093: 235 of 243 timestamped tail lines are one message; 83 of 428 records lost | (1) NAT-096: a Stage A small root without the `com.apple.lsd` job (deterministic for `lsd`; if another daemon floods the same way the row says so); (2) reader v2 (NAT-097) that analyses a begin-less dump from the end line's geometry instead of discarding it (host-only); (3) later, per-daemon `StandardErrorPath` into a RAM file system plus a project-owned reader job | a text whose tail holds launchd's last lines and a `ps -A` list, no flood | NAT-096 build + tests, reader v2 |
| **B11 kernel privilege provider (hypothesis)** | the message means `priv_check_cred(PRIV_PROC_CPUMON_OVERRIDE)` (bsd/kern/process_policy.c `handle_cpuuse`) failed for the caller; on a real device AMFI grants it from an entitlement. The project's kernel loads an AMFI *stand-in* (log line in NAT-068). If the stand-in grants nothing, every entitlement-gated check in Apple's daemons fails the same way | the repeated message itself (consistent, not a proof: `lsd` may genuinely lack the entitlement, and the request might be the unconditional "disable monitor" path, which warns whatever the cap) | read what the stand-in's `mac_priv_check` and entitlement lookups return; decide per later failing daemon; raising `max_cpumon_*` caps through the ADT `/defaults` node (the pinned ADT has one; the command line has 19 spare bytes of 255) helps only if the request is over-cap, not if it is a disable request | the first daemon that exits on an entitlement check names the needed grant | source review of the stand-in policy module and of `csproc_get_entitlements` in the built payload |
| **B7** | see 0c | NAT-093 row A8: no ladder row | NAT-096 | A1: the seven self-starting daemons in a last complete `ps -A` list | NAT-096 |
| **B9, B10** | unchanged from 0c: no frame on the panel; `libhakios.dylib` not built (needs the iPhoneOS 16.5 SDK + a Darwin `ld64`, or assembly from open-source headers with `-undefined dynamic_lookup`) | - | owner download of the SDK (Apple's licence) or the open-source route | - | header/`ld64` pinning, compile-only pass |

Shortest justified path from the current PID 1 to the first real lock-screen/SpringBoard frame (each step is *planned* unless a rung is named):
1. **Make the Stage A text readable** (NAT-096 image without the `lsd` job under a new decision; NAT-097 reader v2). Outcome by row: A1 -> step 2; A2/A3 -> the earliest exit's cause is the next kernel/stub change (probably B11); A4 -> persona/session type first.
2. **Stage B**: backboardd (+ `libhakios.dylib` once it exists, B10) under the same launchd; first backboardd lines, first failing selector (B9).
3. **A frame on the panel** (B4/B9): scan-out reuse (NAT-070 reading is provisional) with the first-frame-without-GPU question answered by backboardd itself.
4. **SpringBoard**, then lock screen. Touch (driver GPIO defect) is after the first frame.

Rung status of this path today: steps 1-4 are *written/built/model-tested* in parts (images, analysers, stand-ins); *ran on S24*: PID 1, Apple launchd, one Apple daemon; *showed real iOS UI*: nothing. No date is promised.

## 0e. Status update, 2026-11-12 after NAT-098/099/101/102 (this section replaces 0d where they differ)

NAT-098 ran `loader-diag-xnu-sq-md1` (Stage A without the `lsd` job) once under decision 0037: RECOVERY only, restored from the pinned stock, Android checked, host load 3.47; the whole root arrived at 13.81 MB/s. Pre-registered rows: chain row 9, Stage A **A8** (outcome *inconclusive*; no launchd console-form line in the returned text, so no ladder row above A8 could apply). Post-hoc reading (written after the analysers, not a ladder row, `docs/procedures/nat-098/`): the `lsd` CPU-monitor flood is gone (0 of 304 timestamped lines), the surviving kernel text is continuous from 215.1 s to 268.5 s, launchd ran NAT-088's three boot tasks, pids 9-25 were created, `logd[16]` and `containermanagerd[12]` are named by the minisandbox lines, no panic line. **What NAT-088's run had and this one lacks: launchd's own console lines and the `ps` lists of the heartbeat job** (`com.nat085.ps`). Hypothesis **H-logd** (untested): once Apple's `logd` runs, the output that launchd and its jobs write to `/dev/console` no longer reaches the kernel log the project returns. The window does not explain the absence: from 215.1 s on the text is continuous (the unsent middle and both holes lie before 216 s, `docs/procedures/nat-098/README.md`), so the missing lines are missing from the kernel log itself. pids 22-25 appeared 10.0 s apart, which matches the heartbeat job's `ThrottleInterval 10`: the job was respawned, so either its `ps` died before printing (a launch-time kill or denial of an Apple binary started by launchd, a B11-type cause) or its output no longer reaches the console (H-logd). Only an observer that does not depend on launchd, and that records how its own child ended, separates the two.

| Item | written | built | model-tested | ran on S24 | real iOS UI |
| --- | --- | --- | --- | --- | --- |
| Flood removed by leaving `lsd` out of the small root | yes | yes | yes | **yes** (NAT-098: 0 of 304 lines) | no |
| Apple `logd` and `containermanagerd` run under restore-mode launchd (minisandbox lines name them; pids 9-25 exist) | plists in the image | yes | static only | **yes** (named, not shown to be healthy) | no |
| launchd's console lines and `ps` lists after `logd` started | yes | yes | yes | **not observed** (H-logd untested) | no |
| `hb`, a launchd-independent heartbeat (NAT-101): freestanding arm64 Mach-O, raw Darwin system calls, started from `/etc/rc` before `exec launchd`, writes `SWEET hb:` lines and Apple's `/bin/ps` output to `/dev/console` every 10 s | yes | yes (16,635 B, NAT-077's clang + lld + mkstatic pipeline) | **yes, in a model**: control flow through a libc model (NAT-101) and the real Mach-O executed under Unicorn with a multi-process fake Darwin kernel in three scheduling orders (NAT-102 `hb_vm.py`); ABI-breaking mutants of `hb.c` detected or shown equivalent with the XNU source | **no** | no |
| Image `loader-diag-xnu-hb-md1` (NAT-102): NAT-096's image plus `hb` and one rc line | yes | yes (RECOVERY sha256 `e938cb4a...ba94`) | yes (byte comparison with NAT-096's payload: only the tag bytes and the md0 region differ) | **no** (native run NAT-103, decision 0038) | no |
| Stage B small root (NAT-099: Stage A root + backboardd plist + donor prebuilt `libhakios.dylib` + `etc/inject.conf`) | yes | yes (readback by the kernel's apfs_lib) | yes (19 tests) | **no** | no |

The model is not the payload kernel. It checks that the machine code of `hb` is consistent with the Darwin arm64 system-call conventions as the project's XNU source states them (number in x16, carry = error with errno in x0, the fork child flag in x1, `select(0,0,0,0,&tv)` as the sleep, `wait4` status layout); where the phone's kernel differs, the native run is the test. One model fact is cited to the source: on an error the kernel stores `x[1] = 0` (`bsd/dev/arm/systemcalls.c`, `arm_prepare_u64_syscall_return`).

**The earliest unsolved blocker is still B7: which of Apple's daemons stay up under restore-mode launchd.** Partly answered: `logd` and `containermanagerd` start. Unknown: whether they stay up, what launchd does after, and whether PID 1 survives. The binding constraint is again **B8, in a new form**: not the volume of one daemon's message but the loss of the routing from launchd and its jobs to the readable log. `hb` goes around launchd; its result decides which of three readings holds:

* **H5 (ps lists after `hb` markers):** the console path works after `logd` started, so the lost launchd lines are a launchd/`logd` routing or window matter; the lists give the process table (B7 in the process-name sense) at about 10 s intervals; only 4-6 rounds fall inside the ~60 s window.
* **H3 or H2 (markers without lists, or the start line only):** `hb` ran and its console writes work (its own lines are in the log) but its `ps` printed nothing: the `ps` status line (wait status: a signal number means a kill, 32512 means the exec failed, `timeout-killed` means it hung) says why. A kill or a failed exec of Apple's `/bin/ps` points at the kernel's launch-time checks (B11), not at the console path.
* **H1 (no `hb` line):** either `hb` did not start (the rc echo `$ /redwood/bin/hb` is in the head window) or its console writes are lost after `logd` starts; the next step is a reader that does not use the console (a file in the RAM file system read by a project program at the end, or a USB channel from a project process).

Shortest justified path from the current PID 1 to the first real lock-screen/SpringBoard frame (steps are *planned* unless a rung is named; the order is by blocker, earliest first):
1. **Observe launchd-independently** (NAT-103: the `hb` image under decision 0038). By row: H5 -> step 2 with the process list; H3/H2 -> the `ps` status lines; H1 -> a non-console reader first.
2. **Stage A pass (B7)**: the seven self-starting daemons in a last complete `ps` list; a daemon that exits names the next kernel or stub change (B11 is the leading hypothesis: the AMFI stand-in grants nothing).
3. **Stage B (B9, B10)**: backboardd and the donor's `libhakios.dylib` (prebuilt, inspected statically in IOS-014, not run) as one removable, bounded step; first backboardd lines, first failing selector.
4. **A frame on the panel**: scan-out reuse from NAT-070 (DECON0 and RDMA0/1 are running; panel visibility was not observed) and the question whether a first frame without a GPU driver is possible. **Plausible, not proven**; no software-rendering promise.
5. **SpringBoard**, then the lock screen; touch after the first frame.

Rung status of this path today: steps 1-5 are *written/built/model-tested* in parts; *ran on the S24*: PID 1 probe, delivery of the 2.31 GiB root, Apple's launchd and, by name, `logd` and `containermanagerd`; *showed real iOS UI*: nothing. No date is promised.

## 0f. Status update, 2026-11-12 after NAT-103 (this section replaces 0e where they differ)

NAT-103 ran `loader-diag-xnu-hb-md1` (`loader_log`-based quiet Stage A + `/redwood/bin/hb` started in `/etc/rc` before `exec /sbin/launchd.darwin`) once under decision 0038 (RECOVERY only, restored from pinned stock, Android checked, host load 1.91 at launch). Full root arrived (`2,475,720,704` B in `172.04s`, `14.39 MB/s`, `0` retries/errors). Pre-registered analysers (run after watcher and collector exited): chain row **9** (`PARTIAL`), Stage A **A8** (`not-evaluated`), and heartbeat ladder **H1** (`no-hb-line`); `NAT-103` stays open (`inconclusive`).

Post-hoc inspection of `boot 000002` vs NAT-098 and `loader_return.c` / `glue62_impl.h` reveals the **binding B8 mechanism**:

* `loader_return.c` (`loader_log_append_msgbuf()`) appends the kernel `msgbufp` (`~30.5 KiB`) **after** the userland console ring (`~85.5 KiB` in NAT-103 vs `~81.3 KiB` in NAT-098; `+4,588` B total length, `116,430` vs `111,842`).
* `docs/procedures/nat-062/src/glue62_impl.h` transmits only `NAT062_HEAD_RETURN = 8,192` (`0x0..0x2000`, stopping inside `/etc/rc` `vm_stat`) and `NAT062_TAIL_RETURN = 32,768` (`0x146ce..0x1c6ce`), dropping `75,470` bytes (`gap`) in the middle.
* After the initial `4,896`-byte ring-overrun hole at `tail_start` (`0x146ce..0x159ee`), **100% of surviving tail bytes (`0x159ee..0x1c6ce`) lie inside the kernel message buffer (`216.673s .. 269.309s`)**. Thus, unlike NAT-088 (`len = 57,665`), zero bytes of console output past `8,192` reached the returned tail in either NAT-098 or NAT-103.
* Circumstantial indicators of `hb` running: `launchd` self-start spawns shifted `+2` PIDs (`11..18` vs `9..16` in NAT-098) and periodic `10.04s` spawns stepped `+2` (`25, 27, 29, 31` with `22, 26, 28, 30` absent from memorystatus), with `memory: free 998, files 552, programs 10` at `266.728s`, plus `+4,588` bytes before `tail`.

**Immediate next blocker is still B8 (unsent 75 KiB console ring inside `loader_log`), NOT userland/daemon code:** before changing `hb` or daemons, return the missing console window (either widen `glue62_impl.h` / stream `loader_log` without the `75 KiB` gap and `4.8 KiB` initial overrun, OR add a non-console reader that sends console/RAMFS output cleanly after boot). Then re-run Stage A observability once cleanly to read `SWEET hb:` and `ps -A`/`ps -Ao` lists and answer **B7**.

## 0g. Status update, 2026-11-13 after NAT-104/105 (this section replaces 0f where they differ)

NAT-104 built `loader-diag-xnu-hb2-md1` (`glue62_impl.h`: `NAT062_BURST=4096u`, `NAT062_TAIL_RETURN=262144u`, `5s` USB settle wait at `why=2`; 20 tests, 254 mutants with 0 unexplained survivors). **NAT-105 ran it once** under decision 0039 (`SM-S921B/e1s`, RECOVERY only, restored from pinned stock `96620b8b...babf67`, Android & readback pass, host load 3.10 at launch). Full root arrived (`2,475,720,704` B in `196.925s`, `12.572 MB/s`, `0` retries/errors). Pre-registered analysers (`analyze_nat104.py`) reached **row H5 `hb-ps-lists`** (`hb_marks=6`, `ps_lists=13`, `rounds_with_logd=[2,3,4,5,6]`, `gap=0`, `hole=0`) and **row A1 `base-daemons-alive`** (`all 7 self-starting jobs are in the last complete ps list; alive in total: 11`). `NAT-105` is **`done` (`pass`, native-device)**.

| Item | written | built | model-tested | ran on S24 | real iOS UI |
| --- | --- | --- | --- | --- | --- |
| Complete `loader_log` return (`116,093` B, `gap=0`, `hole=0`, `drops=0`, `1,405` contiguous frames) | yes | yes | yes (NAT-104) | **yes** (NAT-105) | no |
| Apple `launchd` (`pid 1`) + all 7 self-starting + 4 on-demand/system Apple daemons (`11` alive at `up=51s`) | yes | yes | yes | **yes** (NAT-105: `runningboardd`, `powerd`, `containermanagerd`, `distnoted`, `usermanagerd`, `fseventsd`, `logd`, `notifyd`, `logd_helper`, `cfprefsd`, plus `datamigrator[24]` clean `exit(0)`) | no |
| `/redwood/bin/hb` independent `SWEET hb:` + `ps -A`/`ps -Ao` observer | yes | yes | yes | **yes** (NAT-105, rounds `1..6`) | no |
| Stage B (`backboardd` + donor `libhakios.dylib` + `etc/inject.conf`) | yes (`NAT-099` without `hb`) | yes (`pid1-sb2`) | host readback (NAT-099) | **no** | no |
| Graphics / frame on panel (`MiniIOMobileFramebuffer` swaps -> `0xfa200000`) | yes | yes | selector scan (IOS-013) | scan-out registers only (NAT-070); **no swap/frame** | no |

**Blockers B7 and B8 are closed.** All base Stage A Apple daemons run simultaneously and stay alive under restore-mode `launchd` with `998` MB free (`1,550` MB available) and zero panics over the 60s window.

**Earliest remaining blockers on the path to the first real iOS UI frame:**
1. **Stage B (`backboardd` + `libhakios.dylib` + `hb` observability, NAT-106 -> NAT-107):** combine `NAT-101`'s `pid1-hb` small root (`hb` independent observer) with `NAT-099`'s 3 Stage B additions (`com.apple.backboardd.plist`, prebuilt `libhakios.dylib`, `etc/inject.conf`) and widen `NAT062_TAIL_RETURN` (`524288u`, `512 KiB`, `% 96 = 32`) on `NAT-104`'s `glue62_impl.h` settle fix. Observe on hardware (`NAT-107`): whether `init` configures `kern.exec_inject`, whether `dyld` injects `libhakios.dylib` into `containermanagerd` and `backboardd`, whether `libhakios.dylib`'s 20F66 shared-cache offsets match at run time, what `backboardd` needs (`UserName=mobile`, HID/ALS/Mach lookups), and whether `MiniIOMobileFramebuffer` receives first `swap` / pixel changes (`B9`).
2. **Graphics / scan-out (`B4`/`B9`):** decided directly by Stage B's `MiniIOMobileFramebuffer` swap/diff telemetry and a panel update check once `backboardd` runs.
3. **`SpringBoard` + lock screen + touch (`UI-004`):** follows `backboardd` swap confirmation.

## 0h. Status update, 2026-11-13 after NAT-106/107 (this section replaces 0g where they differ)

NAT-106 built `loader-diag-xnu-sb2-md1` (29-file Stage B + `hb` `md0` root combining `pid1-hb` with `com.apple.backboardd.plist`, donor `libhakios.dylib`, and `etc/inject.conf`; `glue62_impl.h` `NAT062_TAIL_RETURN=524288u`, `NAT062_BURST=4096u`; `11/11` tests, `480` mutants with `0` unexplained survivors). **NAT-107 ran it once** under decision 0040 (`SM-S921B/e1s`, RECOVERY only, restored from pinned stock `96620b8b...babf67`, Android & readback pass, host load `2.81` at launch). Full root arrived (`2,475,720,704` B in `210.711 s`, `11.749 MB/s`, `0` retries/errors). Pre-registered analysers (`analyze_nat106.py`) reached **row B5 `fb-swaps-no-diff`**, **row H5 `hb-ps-lists`**, and **row A1 `base-daemons-alive`**; `NAT-107` is **`done` (`pass`, native-device)**.

| Item | written | built | model-tested | ran on S24 | real iOS UI |
| --- | --- | --- | --- | --- | --- |
| Complete `why=2` dump (`149,450` B, `gap=0`, `hole=0`, `drops=0`, `1,754` contiguous records) | yes | yes | yes (NAT-106) | **yes** (NAT-107) | no |
| `init` `DYLD_INSERT_LIBRARIES` (`/redwood/lib/libhakios.dylib`) into `backboardd` & `containermanagerd` | yes | yes | static only | **yes** (NAT-107) | no |
| `backboardd` (`pid 14`) + `containermanagerd` (`pid 15`) + all Stage A jobs alive through `hb` round 6 (`13` Apple jobs alive, `18` PIDs) | yes | yes | yes | **yes** (NAT-107: `hakios: container manager: no personas`, `hakios: window server hooks installed`, `no accelerated renderer; the software one will draw`) | no |
| `MiniIOSurface` + `MiniIOMobileFramebuffer` swaps (`surfaces 1, 3` `1125x2436 'BGRA'`, `3` swaps, layers `0x0 -> 0x1`) | yes | yes | selector scan (IOS-013) | **yes, `0` diff** (NAT-107: `B5`, expected without `SpringBoard`) | **no** (`0` diff / empty scene) |
| `SpringBoard` + UI scene clients + panel pixel change (`B6`) | partial (donor plist recipe) | no | no | **no** | no |

**Stage B is closed (`B10` donor injection + `backboardd` stability + `IOSurface` + `IOMobileFramebuffer` software-render swap pipeline all verified on hardware with `867` MB free / `1,504` MB available RAM).**

## 0i. Status update, 2026-11-13 after NAT-108 host build (Stage C1 prepared)

**NAT-108** (`host-test`, `pass`) statically audited donor `libhakios.sb.dylib` (`90,656` B, `sha256 d4f1c6b0...b232`, `arm64`, `0` direct `svc`, initializer `_hakios_springboard_init` at `0x4000`, zero `unlink/rename/mount/exec/socket` imports) and built `loader-diag-xnu-sc1-md1` (`recovery.img` `sha256 90eecfbc...cdbb`) with `fb_diff=1` (`246`-byte cmdline) and a `423`-file `4 MiB` `md0` root (`bb02a20b...9725`, `423/423` kernel `apfs_lib` readback `ok`): `NAT-106` `pid1-sb2-hb` + full donor `22 DARWIN_JOBS` + `382 --rest` on-demand `LaunchDaemons`/`LaunchAngels` (`405` plists) + `lib/libhakios.sb.dylib` (`0755`) + 2-line `etc/inject.conf` (`backboardd` + `SpringBoard`) + `8` `var/` preference plists (`0644`, `SetupDone=True`, `BKNoWatchdogs=True`, `FBLaunchWatchdogScale=20.0`) + fixed `zoneinfo.default`/`UTC` and `var.skel` dirs. Verified via `derive108.py --check` (`9` substitutions), `test_nat108.py` (`12/12` passing), and `mutate_nat108.py` (`623` mutants: `584` killed, `4` equivalent in `equivalent.json`, `35` invalid, `0` unexplained survivors), with single-run decision `docs/decisions/0041-nat108-loader-diag-xnu-sc1-md1-single-run-2026-11-13.md`.

**Immediate next step on the path to the first real iOS UI frame:**
1. **Run Stage C1 once (`NAT-109`, `native`):** execute `loader-diag-xnu-sc1-md1` under decision `0041` and classify with `analyze_nat108.py --mode stage-c` (`C0`-`C7`), checking whether `SpringBoard` stays alive (`C5`), drives `MiniIOMobileFramebuffer` swaps (`C6`), and flips `fb_diff > 0` (`C7`, proving `SpringBoard` renders non-empty pixels into the framebuffer before `e1s-display` scan-out verification).
2. **Touch input (`e1s-touch` GPIO defect / `devfs` node alignment with `libhakios.dylib`)**: after the first real `SpringBoard` lock screen frame.

## 1. Audit of the selected profile and local components

Selected profile (docs/implementation.md, CAPABILITIES.md): **iPhone X (iPhone10,3, D22AP, t8015) iOS 16.5 (build 20F66)** userland on **XNU 8796.121.2** (HackiOS base d82c64a3) for **SM-S921B/e1s**.

| Item | Needed for | Local state (searched 2026-11-12) | Evidence class | What closes it |
| --- | --- | --- | --- | --- |
| iOS version, arch, kernel match | everything | Target: arm64 (A11, non-arm64e) 16.5/20F66. Our kernel prints `Darwin Kernel Version 22.5.0 ... DEVELOPMENT_ARM64_E1S` (the iOS 16.5 family, xnu-8796). The IPSW is now present and accepted (IOS-001/002: build 20F66, iPhone10,3 supported, D22AP); the kernelcache banner of the IPSW is read by `tools/ios/ipsw_inspect.py`. | kernel line: ran on S24; IPSW identity: host-test (IOS-002) | done (IOS-001/002) |
| Restore image (IPSW) with the OS, SystemOS and AppOS disk images, `DeviceTree.d22ap.im4p`, `BuildManifest.plist` | root file system, dyld, shared cache, launchd, SpringBoard, backboardd, all frameworks | **PRESENT since the owner's placement under `artifacts/apple-inputs/` (git-ignored, never committed).** Original text of this row (written before the IPSW existed) said ABSENT; it was true on the morning of 2026-11-12 and is kept only as history. Real `launchd`, `backboardd`, `SpringBoard`, dyld and the shared cache now exist on the host in the unpacked tree made by the donor recipe (IOS-009/010). | host-test (IOS-001/002/009/010) | done |
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

**Result (NAT-070, 2026-11-12, native-device):** no read faulted or hung; the formal label was `decon-running-no-enabled-rdma`, and the reading of the same numbers against the S9 donor supports the first row provisionally. See section 0b for the numbers, what is not established, and the visibility check that can reverse it.

## 4. External inputs (the only items the owner has to supply)

| ID | File / data set | Purpose | Lawful way to obtain | Completion check |
| --- | --- | --- | --- | --- |
| IOS-001 (DONE 2026-11-12) | The iPhone X (iPhone10,3 / D22AP) iOS 16.5 build 20F66 restore image (`*_Restore.ipsw`, several GB) | the only source of the real OS/SystemOS/AppOS disk images (rootfs, dyld, shared cache, launchd, SpringBoard, backboardd, all frameworks), the D22AP DeviceTree `/product` tree and the matching kernelcache version string | Apple publishes IPSW files on its own update CDN without authentication; the owner downloads their copy from Apple (the installer licence restricts use to Apple-branded hardware - the owner's decision and responsibility, recorded here without a legal conclusion). Place it at `artifacts/apple-inputs/` (git-ignored). Do not commit it; do not run donor install scripts. | `tools/ios/ipsw_inspect.py` reports `ProductBuildVersion 20F66`, `iPhone10,3` in the supported product types and the SHA-256 of each image (IOS-002) |

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
| NAT-070 (DONE, native-device pass) | Does the display engine scan out the loader's framebuffer? | parsed `e1s-display:` pipeline lines vs `phys 0xfa200000`; chain verdict PASS | section 3 table; result in section 0b |
| NAT-072 | Can a run last minutes with a verified stop, and does the timed return work? | heartbeat lines with kernel stamps >= 5 s apart; loader return reason; keepalive stop and no watchdog reset before the deadline | if yes: milestone 1 closed, launchd bring-up uses N-minute runs; if the keepalive does not hold the watchdog: stay with bounded < 57 s runs and put the USB-in-kernel log task on the path |

## 8. Task map

IOS-001 (blocked, external) - IOS-002 (inspector, host) - IOS-003 (kernel gap matrix, host) - NAT-069/070 (display fork) - NAT-071/072 (milestone 1) - NAT-073 (root delivery, host).
Not on the path now: UI-003/GPU-007/GPU-008/GPU-009 (wait for the fork and the first backboardd result), eSIM/Wi-Fi/Bluetooth/cellular tasks, any further log-transport work beyond what milestone 1 needs.
