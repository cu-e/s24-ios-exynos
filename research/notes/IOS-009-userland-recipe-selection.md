# IOS-009: which route prepares the iOS 16.5 userland (reuse before own tools)

Date: 2026-11-12. Owner: claude-nat065-20261112-ramdisk. Evidence categories used below: **source-review** (donor files read), **host-test** (a donor script run on this host, on the owner's IPSW). Nothing here ran on the S24 and nothing here shows iOS UI.

## 1. Decision

The project does not write its own DMG/APFS extraction or an own root-file-system composer. The route is the one the HackiOS tree already pins (`references/hakios` @ `87bf4851bcc9cbb24fd79997820aa3661abe4ea5`, built for this very IPSW, 6,165,698,198 bytes, iPhone10,3 16.5 20F66):

1. `sysimage/unpack.sh` (stock 7-Zip + `ipsw-member.py` + `select-system.py` + `mkvarskel.py` + `font_trim.py` + `unzbm`) -> `rootfs/`, `system.manifest`, `var.skel`, OS and App cryptex trees, the dyld shared cache.
2. `userland/` init chain (`stage0.c` as `/sbin/launchd`, `init.c`, `etc/rc`, `mkjobs.py`) -> small `root.apfs` (the second RAM disk, `/dev/md1`).
3. `tools/apfs/mkapfs.py -z` -> `system.apfs` (the resident root, `/dev/md0`), checked with `tools/apfs/check-image.sh` (`apfsck` of linux-apfs/apfsprogs plus the kernel's own `apfs_lib`).
4. Delivery into RAM, kernel mount, then the real `/sbin/launchd.darwin` (`rc.launchd`: `exec /sbin/launchd.darwin`).

Own code is written only for gaps the donor tools do not close (section 6). The earlier own code stays in the tree: `tools/ios/udif.py` (29 host tests) is now a cross-check reader, not a dependency.

## 2. Variants checked

| # | Variant | How it was checked | Result | Verdict |
|---|---------|--------------------|--------|---------|
| V1 | Own UDIF reader (IOS-004) and own APFS reader (IOS-005) | UDIF written and tested (`tools/ios/udif.py`, `tests/test_udif.py`); APFS reader not started | UDIF works on synthetic images; an own APFS reader would repeat 7-Zip and `hakios/tools/apfs/apfs.py` | superseded; UDIF kept as an independent cross-check only |
| V2 | Stock 7-Zip 26.04 (Fedora `7zip-26.04-1.fc43.x86_64`, `rpm -V` clean) | listed and extracted the rootfs, the OS cryptex and the App cryptex of the owner's IPSW | reads the DMG (zero/raw/zlib/LZFSE chunks) and the APFS inside it; extracts the whole rootfs tree in about 49 s. Limits: it refuses symlinks whose target contains `..` (exit 2) and leaves LZBITMAP-compressed files empty with a `*:com.apple.decmpfs` attribute file | adopted, exactly as the donor uses it (the donor selection avoids the refused links and `unzbm` finishes the LZBITMAP files) |
| V3 | HackiOS `sysimage/` recipe | read `unpack.sh`, `select-system.py`, `ipsw-member.py`, `mkvarskel.py`; ran `unpack.sh` unmodified from a staged copy of the pinned files (`tools/ios/stage_hakios_recipe.py`) | exit 0; numbers in section 4 | adopted |
| V4 | HackiOS `tools/apfs/mkapfs.py` and `check-image.sh` | read (938-line writer, no third-party Python imports; the checker clones `linux-apfs/apfsprogs` at a pinned commit and builds it) | not yet run on this host | adopted for the root image (task IOS-010) |
| V5 | y2sios (`dmg.py`, `mkapfs.py`, `userland.exclude`, `mkjobs.py`) | read; same xnu-8796.121.2, same lineage | its `select-system.py` is not in the pinned tree; its root lives in the tail of the `super` partition (not an option here) | reference only |
| V6 | ios-lemonadep RAM staging | read README/FINDINGS | ~2.5 GB staged in RAM in ~90 s over fastboot `stage`, on a different phone and loader | reference for the delivery size and time, not reusable code |
| V7 | ios-apollo (HFS+ route, 16.7.16) | read | needs an HFS+ driver and a `launchd_unsecure_cache` handshake; this project's kernel has neither in its image (IOS-003 R-rows) | not chosen |
| V8 | dmg2img, apfs-fuse, libfsapfs/pyfsapfs, blacktop `ipsw`, lief/capstone/macholib | not installed on this host; not evaluated beyond name (dmg2img does not read LZFSE) | not needed for the chosen path | may be installed later for the Mach-O closure check (task IOS-012) |

## 3. Provenance and licences

* 7-Zip 26.04, Fedora RPM, `rpm -V 7zip` clean (no modified file).
* HackiOS tools: MIT (`LICENSE`), kernel/driver parts APSL (`LICENSE.APSL`, `NOTICE`). `libzbitmap` is APSL. The staged files (29) and their SHA-256 are in `docs/procedures/ios-009/recipe-manifest.json`; `tools/ios/stage_hakios_recipe.py` copies only blobs of the pinned checkout and refuses to run when the checkout is not clean.
* `check-image.sh` would build `linux-apfs/apfsprogs` (GPL-2.0, not distributed here; run as a checker only) at commit `1bd1c1c2140d13d1b6d2e03379316572bee70aa3`. It is not a pinned project source yet (task IOS-010 adds it).
* No Apple file is committed. Everything extracted is under the gitignored `artifacts/ios-root/` and `artifacts/apple-inputs/`.

## 4. What the donor run produced (host-test, 2026-11-12)

Command: `KEEP=1 bash sysimage/unpack.sh artifacts/apple-inputs/iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw` in `artifacts/ios-root/recipe/` (staged copy; the pinned checkout stayed clean). Exit 0; the script's own end-of-run checks passed (43 dyld cache files, no `:com.apple.*` leftovers, `webbookmarksd` present).

* `select-system.py`: 43,230 files, 2,881 MB, 59,644 manifest entries (a budget made for the 4 GB RAM donors).
* Results: rootfs 2.9 GB, OS cryptex tree 24 MB (without the cache), App cryptex 11 MB, dyld shared cache 2.6 GB in 43 files (`.symbols` left out), `DeviceTree.d22ap.im4p` 33,694 bytes.
* Present in the selected tree: `/sbin/launchd` (Mach-O arm64, 525,088 B), `/usr/lib/dyld` (922,912 B), `/usr/libexec/backboardd` (1,182,960 B), `SpringBoard.app/SpringBoard` (112,048 B).
* The donor comment in `build.sh` says these files come to 2.5 GB in `system.apfs` with zlib; that figure is the donor's claim and is **not yet reproduced** here.

A file being present is not compatibility: dyld/launchd/syscall equality with the project kernel is untested (section 7).

## 5. Shortest path from here to the first real SpringBoard frame

| Step | What | Status |
|------|------|--------|
| 1 | extract the IPSW userland | done on host (section 4) |
| 2 | build `system.apfs` with `mkapfs.py -z`, check it with apfsck + apfs_lib | next (IOS-010) |
| 3 | PID 1 chain: `stage0` as `/sbin/launchd`, `init`, `etc/rc`, `mkjobs.py` jobs, small `root.apfs` as `md1` | sources pinned, build needs a toolchain (G1, task IOS-011) |
| 4 | put ~2.5 GB in RAM without an Android partition | earliest unsolved blocker (G2; NAT-073 and NAT-071) |
| 5 | kernel mounts the APFS and runs `launchd.darwin` | unknown (G3, G4) |
| 6 | window server first frame without a full GPU | IOS-013 |

## 6. Confirmed gaps where own code is justified

* **G1 build of stage0/init.** The donor builds with `xnu-clang` and a Theos SDK, which this host does not have. The project already owns a freestanding arm64 toolchain (compiler and Mach-O linker built under `artifacts/`, used by `tools/build/avf_guest_pid1_build.py`). Needed: `userland/libmini` added to the pinned review files and a build of `stage0.c`/`init.c` with the project toolchain. Evidence of the gap: `xnu-clang`, `ld64`, `ldid` are not on PATH.
* **G2 delivery into RAM.** The recovery slot is 96 MiB; the project loader has USB control requests only (no host-to-device bulk path), a software deadline of about 57 s after enumeration and a hardware watchdog of 83 s (NAT-068/069 logs). A ~2.5 GB root needs a bulk receive in the loader (about 28 MB/s is the donor figure: ~90 s) and a longer run window (NAT-071), or a smaller root. The donor's own loader (`xnuloader/`, `xl ramdisk`) targets other hardware.
* **G3 mount.** The project kernel has a read-only APFS driver in source (zlib/zbitmap), never run on the S24. Host check: `apfs-tool` from `check-image.sh` runs the kernel's `apfs_lib` on the host; the real answer needs the S24.
* **G4 launchd handshake.** The image scan found 0 occurrences of `launchd_unsecure_cache` and `ignition_level` (IOS-003 `image-scan.json`); what Apple's launchd asks of the kernel is unknown until it runs.
* **G5 graphics** (backboardd/SpringBoard first frame): IOS-013.

## 7. Not established

* That the 16.5 userland (kernelcache xnu-8796.122.4~1 for t8015) works on the project kernel (xnu-8796.121.2): syscall and Mach trap tables not compared.
* The size of `system.apfs` for this selection and whether it fits the delivery budget.
* That the S24 can mount an `mkapfs` image, run `launchd.darwin`, or show any iOS UI. Only the project's own PID 1 probe has run on the phone (NAT-068, exit 81).
