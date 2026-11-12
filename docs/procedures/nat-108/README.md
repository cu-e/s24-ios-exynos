# NAT-108: Stage C1 + Heartbeat Host Build, Pack, Analyser, Driver, and Mutation Gate (`loader-diag-xnu-sc1-md1`)

Host-only preparation for Stage C1 (`SpringBoard`, full donor `LaunchDaemons`/`LaunchAngels`, `libhakios.sb.dylib`, donor `var/` preference plists, fixed zoneinfo symlinks, `etc/var.skel` entries, and `fb_diff=1` boot-arg) on top of `NAT-106`'s Stage B + heartbeat base (`loader-diag-xnu-sb2-md1`, `512 KiB` return tail, `4096 B` burst, `10x` settle waits). Nothing ran on a phone.

## Artifacts and Changes

1. **Static inspection of donor `libhakios.sb.dylib` and `var/` plists**:
   - Checked out `/prebuilt/userland/libhakios.sb.dylib` (`90,656` B, `sha256 d4f1c6b06b4b016b1a3ea77d741382053efde0093a5a8f77226a215bee87b232`) and `/userland/var/` (`8` plists) from pinned `references/hakios` (`87bf4851bcc9cbb24fd79997820aa3661abe4ea5`).
   - `macho_audit.py` + `inspect_dylib.py` (`artifacts/nat-108/inspection-libhakios-sb.json`, `sha256 96d19597b748a001f3bbd2da88a2ab345c63713f8fb844f1f632a331eade6cb`): `arm64` plain dylib, zero direct `svc` instructions, install name `/redwood/lib/libhakios.sb.dylib`, initializer `_hakios_springboard_init` at `0x4000`, zero destructive/network imports (`unlink`/`rename`/`mount`/`exec`/`socket`).
2. **Stage C1 + heartbeat small root (`build_sc1_hb_root.py` -> `artifacts/nat-108/pid1-sc1-hb/`)**:
   - Wraps `docs/procedures/nat-099/build_stage_b_root.py` on top of pinned `NAT-106` base (`artifacts/nat-106/pid1-sb2-hb/root.apfs`, `sha256 182aead762086a1f322995bd0f05365d7115184d8d775bac3563aa527fa61c56`, `29` files).
   - Runs pinned donor `mkjobs.py --rest` (`22` `DARWIN_JOBS` + `382` on-demand `LaunchDaemons`/`LaunchAngels`, preserving `com.apple.backboardd.plist` and `com.nat085.ps.plist`, `405` plists total), adds `lib/libhakios.sb.dylib` (`0755`), 2-line `etc/inject.conf`, `8` `var/` preference plists (`0644`), fixed zoneinfo symlinks (`zoneinfo.default`, `UTC`), and `etc/var.skel` directory entries (`/private/var/mobile/tmp`, `/private/var/db/hakios-metal-cache`).
   - Total `423` files inside `4,194,304` B (`root.apfs`, `sha256 bb02a20bd9ec5ad87df634adbed93e9936ae24c3c32901ed1369b274850e9725`), verified by `verify.py content --all` and kernel `apfs_lib` (`423/423` files, `0` mismatches).
3. **Image build and packaging (`build.py`, `docs/procedures/nat-044/package.py` -> `artifacts/nat-108/{build-001,package-001}`)**:
   - Builds `loader-diag-xnu-sc1-md1` (`nat_attempt=NAT108-sc1` + `fb_diff=1`, cmdline `246 < 256` bytes), keeping `NAT-106`'s `loader_return_after=60`, `NAT062_TAIL_RETURN=524288u`, `NAT062_BURST=4096u`, and `10x` settle waits (`glue62_impl.h` `sha256 7fa35d764441bca2ce000408a2fea17672c149a45129047224c70880dcc71d60`).
   - `Image`: `385,024` B (`4604b814a09be6f4fc49b8a2b506fcce6d9e9f2331492b8a20de683ef3eec5e5`)
   - `Image.payload`: `26,134,288` B (`67ec6504724b70db21b7eecc1f3c2c837166561e239303a3d3b56f048e3c9524`)
   - `recovery.img`: `100,663,296` B (`90eecfbc45e055d8514639512c56351668f25e2aae7cd0ea6f50241a744fcdbb`, `19,627` differing 4K pages vs stock)
4. **Analyser, Driver & Decision (`analyze_nat108.py`, `derive108.py` -> `session_nat108.py`, `docs/decisions/0041-...`)**:
   - `analyze_nat108.py` adds `--mode stage-c` implementing the `C0`-`C7` ladder (`no-kernel-text` through `panel-pixels-changed`) while preserving `stage-b`, `hb`, `stage-a`, and `chain`.
   - Counted derivation (`9` substitutions from `session_nat106.py`), verified by `derive108.py --check`.
5. **Verification**:
   - `test_nat108.py` (`12/12` passing, including payload byte-diff vs `NAT-106`, root content checks, synthetic refusals, `C0`-`C7` ladder, and `NAT-105` CLI regression).
   - `mutate_nat108.py`: `623` mutants (`584` killed, `4` documented equivalent in `equivalent.json`, `35` invalid, `0` unexplained survivors).
