> **Historical, sanitized copy integrated into main on 2026-11-10.**
> Original: `worktrees/nat-006-recovery-image-20261110/docs/procedures/nat-006/handoff.md`
> at `d20cc17742a2b6f8c2aeb1273e702c98d5f41934` (see NAT-018 report for exact source SHA).
> Device serial literals are redacted in this copy; the original is preserved.
> Statements below describe an earlier host-build checkpoint, before the later
> experimental RECOVERY flash and boot loop. They are not current phone status
> or proof of a working XNU boot. The historical Android 14 wording is incorrect;
> the measured firmware runs Android 15. NAT-012 subsequently restored stock
> RECOVERY and verified Android boot/user unlock and the full RECOVERY hash.
> See `docs/procedures/nat-012/handoff.md` and `docs/procedures/nat-014/README.md`.
> No new native test is authorized by this integration.

# NAT-006 Verifiable Status Package, Build Verification, and Pre-Flash Safety Gate Handoff

- **Task**: `NAT-006`
- **Owner**: `agy-nat006-20261110-aca2` (transferred from stopped executor `claude-takeover-20261110-6c8f` under decisions `0002`, `0003`, and `0004`)
- **Worktree**: `/home/egor/dev/pet/s24-ios-exynos/worktrees/nat-006-recovery-image-20261110`
- **Branch**: `team/nat-006-recovery-image-20261110`
- **Previous Saved Commit**: `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` (`NAT-006: WIP loader FDT/framebuffer patch and RECOVERY builder`)
- **Recorded Date**: `2026-11-10`

---

## 1. Executive Summary & Mandatory Pre-Flash Gate Outcome

1. **Was `RECOVERY` flashed to the device?** **NO.** Execution stopped at the mandatory pre-flash recovery gate (`Step 4` of the owner's `2026-11-10` directive, recorded in `docs/decisions/0004-nat006-continuation-and-recovery-gate-2026-11-10.md`) before any write to `/dev/block/by-name/recovery`.
2. **Did a native XNU boot attempt occur on hardware?** **NO.** All `NAT-006` builds and verifications (`build-001` and `build-002`) were completed on the host only (`flashed: false`, `device_used: false`, `hardware_execution: false`).
3. **Did an image appear on the phone screen?** **NO.** The phone screen remains on the normal running Android 14 system.
4. **Is Android accessible and intact?** **YES.** Connected device `[redacted-device-serial]` (`SM-S921B` / `e1s`, firmware `S921BXXS9BYH3`, `sys.boot_completed=1`) is running normal Android 14 with all 7 measured critical partitions (`recovery`, `boot`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `vbmeta_system`) byte-for-byte identical to the saved backups in `devices/recovery/backups/2026-11-10/` and `artifacts/device-backup/2026-11-10-session1/`.
5. **What specifically blocked writing `RECOVERY`?**
   - **Blocker 1 (`NAT-008` / `NAT-004` — Missing host Download Mode flashing tool)**: Neither `odin4` nor `heimdall` is installed anywhere on this Linux host (`PATH`, `/usr`, `/opt`, `/home/egor`). Samsung S-Boot Download Mode uses the Odin/LOKE protocol rather than Fastboot. While `/vendor/bin/install-recovery.sh` (`vendor_flash_recovery` init service) or `su -c dd` can restore `/dev/block/by-name/recovery` *after* Android boots, if a `RECOVERY` test leaves the phone in a Recovery loop or Download Mode without booting Android userland, the host currently has no tool to flash `restore/recovery-stock-odin.tar`.
   - **Blocker 2 (`NAT-009` / `NAT-007` — Unarmed hardware watchdog and sticky `SEC_RESET_REASON_RECOVERY`)**: Entering `RECOVERY` via `adb reboot recovery` writes `SEC_RESET_REASON_RECOVERY` (`0x12345604`) into PMU `panic_inform` (`drivers/samsung/debug/sec_reboot.c`). Neither the `NAT-006` loader (`halt: wfe; b halt`) nor the `STR-041` XNU image (`SweetWatchdog` stub: `"accepts check-ins, never fires"`) arms the S5E9945 hardware watchdog (`NAT-007` is still `pending`). Any hang requires a manual PMIC hard-reset (`Volume Down + Power > 7 s`), and whether `panic_inform` is cleared before jumping to `RECOVERY` (preventing a recovery bootloop) is unverified.
   - **Blocker 3 (`NAT-010` — Unverified EL1 MMU/cache state during high-DRAM `0x9de400000` window copy)**: `shim/e1s-xnu/start.S` calls `loader_main()` before clearing `SCTLR_EL1.M` and `SCTLR_EL1.C`. `loader_main()` zeroes and copies XNU into `0x9de400000..0x9fe400000` (in the high DRAM bank `0x880000000..0x9ffffffff`), and only cleans D-cache lines for copied Mach-O segments and `ADT`/`boot_args`, not the remaining zeroed pages in the 512 MiB window.
   - **Fixed during this session (`0002-loader-ui-pc-relative-string-tables.patch`)**: Auditing `build-001` revealed that `shim/e1s-xnu/ui.c.o` contained **37 `R_AARCH64_ABS64` relocations** in `.rodata` (link-time `0x000000000000cxxx` pointers in `stage_names`, `device_labels`, `device_values`, `boot_labels`, `kernel_labels`, `colour_bars.names`, and the `ui_set_stage` switch lookup table). Because the freestanding loader links at `0x0` with no relocation fixup loop and runs at `0x80080000`/`0x800f0000`, enabling the `0xfa200000` framebuffer in `0001` caused `ui_begin()` to dereference `0x000000000000c7ac` (BootROM/unmapped memory on S5E9945) before copying XNU. Patch `0002-loader-ui-pc-relative-string-tables.patch` converts those tables to PC-relative 2D `char` arrays, reducing C object `R_AARCH64_ABS*` relocations to **0** in `build-002`.

---

## 2. Full File & Artifact Inventory (Path, Size, SHA-256, Provenance, Commit)

### 2.1. Pre-Existing Saved Files at Commit `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` (`worktrees/nat-006-recovery-image-20261110`)

| Path (relative to worktree / repo) | Size (B) | SHA-256 | Provenance | Associated Commit |
|---|---:|---|---|---|
| `tools/build/e1s_recovery.py` (at `ac22ef5`) | 18,094 | `35f76508ee6d35d5f6d7dc869fe5b5476ccf1577a680baa29c7fbb3ae71b4eb3` | Authored by prior stopped session (`claude-nat006-20261110-1r6m`); never executed prior to `ac22ef5` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `docs/procedures/nat-006/verify_image.py` (at `ac22ef5`) | 1,723 | `efa16a92ce2c70bdc704fdd0c76d19c568de9272c0bac289266dfeb1727649b2` | Interrupted write (truncated at line 48) saved in WIP commit | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `docs/procedures/nat-006/check_loader.py` | 5,869 | `bb44b13c9beeae27eb128d3efa04e96855ffd0d9ba32550b7788b9617c459188` | Host FDT window/framebuffer harness runner; executed for `window-001` & `window-002` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `docs/procedures/nat-006/window_harness.c` | 4,126 | `35162854c1f9ae30343cb0f2116076a0fa76d7372b20981fe61025d282696dff` | C harness compiled with `clang -fsanitize=address,undefined` against `fdt.c` + `loader.c` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `docs/procedures/nat-006/patches/0001-loader-sboot-dynamic-reservations-and-framebuffer.patch` | 7,655 | `dbfb5c3ac316b0b02b501be399cd3cb584699a24a8b58842b6612d7799a2643f` | Patch against `s24-port` (`ffb8ce72172f4d43299e6d88149ab0f605d5c66e` + `STR-002`/`STR-005`/`STR-019`) | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `tests/test_e1s_recovery.py` (at `ac22ef5`) | *MISSING* | *ABSENT* | Reserved in `NAT-006`, not created prior to `ac22ef5` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |

### 2.2. Pre-Existing Host Artifacts & Scratchpad Files (Uncommitted, Outside Git)

| Path | Size (B) | SHA-256 | Provenance | Associated Commit |
|---|---:|---|---|---|
| `artifacts/nat-006/window-001/report.json` | 5,545 | `cc4f4e6fe3e08ff558051a21c0dbf482dcf9702bc6c1c187484e28ecf990a06d` | `check_loader.py` on unpatched `STR-019` loader (`outcome: fail`, `reserved_ranges=-1`, `window.found=0`) | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `artifacts/nat-006/window-001/window_extract.inc` | 2,991 | `493a92482b7ecd4d215e2e831ca90d34346f6ec28f9672c36d19e52b1c1aa958` | Extracted `loader.c` functions from `STR-019` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `artifacts/nat-006/window-001/window_harness` | 782,120 | `909b26e3e7ad1cf8d57a8290df6d6c8ecab1861c4ff2ee0015b58ac207334594` | Compiled ASan/UBSan ELF binary for `window-001` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `artifacts/nat-006/window-002/report.json` | 13,576 | `c1a3f4126b35e31d2a06b24ad849543f363be29a295845285e0987661f74095a` | `check_loader.py` on `0001`-patched loader (`outcome: pass`, `0x9de400000+0x20000000`, FB `0xfa200000`) | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `artifacts/nat-006/window-002/window_extract.inc` | 3,446 | `797450c58d65047b8e59a128ebd54235eefb369b024b1ea938f9b64f12358dd5` | Extracted `loader.c` functions with `0001` patch | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `artifacts/nat-006/window-002/window_harness` | 791,480 | `7bb7b991a414a9ec9e72e35e55e933d78b5a6af1374c96aa9aebeed8f00313f6` | Compiled ASan/UBSan ELF binary for `window-002` | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `/tmp/claude-1000/-home-egor-dev-pet-s24-ios-exynos/1bd73f06-6e15-484a-a21b-57031c96b28b/scratchpad/payloadtest/payload.bin` | 21,554,784 | `9726b649cda09f296b012e6ad9f6fe94a4e8e36bd1681103ea45e185e4c5fa29` | Trial `mkpayload.py` output in Claude scratchpad using `STR-041` `kernel.unstripped` | Uncommitted (`/tmp` scratchpad) |
| `/tmp/claude-1000/-home-egor-dev-pet-s24-ios-exynos/1bd73f06-6e15-484a-a21b-57031c96b28b/scratchpad/payloadtest/e1s.adt` | 13,956 | `b3e7c85d373552b607db8973b6e3b7ccd08104a63903661bd26344f913b3483c` | Trial `mkadt.py` output in Claude scratchpad (no Apple donor `/product` node) | Uncommitted (`/tmp` scratchpad) |
| `/tmp/claude-1000/-home-egor-dev-pet-s24-ios-exynos/1bd73f06-6e15-484a-a21b-57031c96b28b/scratchpad/loaderpatch/shim/e1s-xnu/fdt.c` | 17,460 | `3d18546d9b30ba3bd89392ae3eef42b448d7cda1cdc4e1fce240f0c4836b7647` | Scratchpad patched `fdt.c` (postimage of `0001` patch) | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `/tmp/claude-1000/-home-egor-dev-pet-s24-ios-exynos/1bd73f06-6e15-484a-a21b-57031c96b28b/scratchpad/loaderpatch/shim/e1s-xnu/fdt.h` | 886 | `50a8744fba244d405bf0b8323d86535b63a3944ed8def58e03eeae90464ec0a2` | Scratchpad patched `fdt.h` (postimage of `0001` patch) | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |
| `/tmp/claude-1000/-home-egor-dev-pet-s24-ios-exynos/1bd73f06-6e15-484a-a21b-57031c96b28b/scratchpad/loaderpatch/shim/e1s-xnu/loader.c` | 20,065 | `961f15a2b5cc92ce0d0fa78fac207b90b37bfdab6e4827d8006fc021f4c9b276` | Scratchpad patched `loader.c` (postimage of `0001` patch) | `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` |

### 2.3. Pinned Inputs & Verified Device Partition Backups (Matched Against Live Phone `[redacted-device-serial]` on `2026-11-10`)

| Path | Size (B) | SHA-256 | Live Phone `/dev/block/by-name/*` Match | Provenance |
|---|---:|---|---|---|
| `devices/recovery/backups/2026-11-10/recovery.img` (`artifacts/device-backup/2026-11-10-session1/recovery.img`) | 100,663,296 | `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` | **EXACT MATCH** (`recovery` / `sda20`, SHA-1 `9771215e66a147fc4dac8111af85c0935a96f31f`) | `NAT-001` backup, re-verified on live phone |
| `devices/recovery/backups/2026-11-10/boot.img` (`artifacts/device-backup/2026-11-10-session1/boot.img`) | 67,108,864 | `d8da9edda2aa2efba4ecabac32cadebe2edefba6a3e38ab0b2ffba9d92bf7558` | **EXACT MATCH** (`boot` / `sda18`, SHA-1 `e4d62b38f87fc6d2800e2fe34f76e29635e02acd`) | `NAT-001` backup, re-verified on live phone |
| `devices/recovery/backups/2026-11-10/init_boot.img` (`artifacts/device-backup/2026-11-10-session1/init_boot.img`) | 8,388,608 | `92b6c0ed702b7b5752dd3357142ab16197b18e763fb658d2bf0e305fb8654ab3` | **EXACT MATCH** (`init_boot` / `sda19`, Magisk-patched) | `NAT-001` backup, re-verified on live phone |
| `devices/recovery/backups/2026-11-10/vendor_boot.img` (`artifacts/device-backup/2026-11-10-session1/vendor_boot.img`) | 67,108,864 | `cf4c3a4c3e266ca5e5ce5c7a7a3e67580684bc6062c4d6ab0dc329047eb4dc5c` | **EXACT MATCH** (`vendor_boot` / `sda21`) | `NAT-001` backup, re-verified on live phone |
| `devices/recovery/backups/2026-11-10/dtbo.img` (`artifacts/device-backup/2026-11-10-session1/dtbo.img`) | 8,388,608 | `e1ca9a1c3f1fa148e7655aa8f22059c39b0fd0bc9210248318a913a0fc29fc5e` | **EXACT MATCH** (`dtbo` / `sda22`) | `NAT-001` backup, re-verified on live phone |
| `devices/recovery/backups/2026-11-10/vbmeta.img` (`artifacts/device-backup/2026-11-10-session1/vbmeta.img`) | 65,536 | `c216e1fc39be8c2a53762520e37bf62b695ff0634e6d23aaed2a0d3861b90226` | **EXACT MATCH** (`vbmeta` / `sda23`) | `NAT-001` backup, re-verified on live phone |
| `devices/recovery/backups/2026-11-10/vbmeta_system.img` (`artifacts/device-backup/2026-11-10-session1/vbmeta_system.img`) | 65,536 | `61ec4c99b18f3858a5be9c3c40d28b5b920442514875e4bf28a21cb322be112b` | **EXACT MATCH** (`vbmeta_system` / `sda25`) | `NAT-001` backup, re-verified on live phone |
| `devices/e1s-fdt/2026-11-10/runtime.dtb` | 375,385 | `95fa811abca3f5f8889705add485f94c4490c57a853bded10539d4631bef46c3` | Extracted from `/sys/firmware/fdt` on `[redacted-device-serial]` (`NAT-005`) | `5b24cf3144a2ee3616b850fb48d88cb4a9d8fb42` |
| `worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001/kernel/kernel.unstripped` | 22,526,184 | `4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f` | Linked 1042-body E1S XNU `MH_EXECUTE` (`STR-041`) | `STR-041` (`a2f54f13b43a11f6...`) |

### 2.4. Completed & Verified `NAT-006` Worktree Files and `build-002` Artifacts (This Session)

| Path | Size (B) | SHA-256 | Provenance | Status |
|---|---:|---|---|---|
| `worktrees/nat-006-recovery-image-20261110/tools/build/e1s_recovery.py` | 19,462 | `648a351cc0f38feeb2ca7846c318e33a7e3ce9255054d62792522a14961ec25e` | Fixed silent `git apply` worktree skip (`--git-dir=/dev/null`), enforced postimage hashes, added `0002` UI relocation patch | Executed & Verified (`exit_code: 0`) |
| `worktrees/nat-006-recovery-image-20261110/docs/procedures/nat-006/verify_image.py` | 28,590 | `913e401832c2bb6821005741b72e874f494c8cc38b14507034b61ab627f9bb33` | Completed independent byte-level verifier (20 checks across header v2, AVB/vbmeta, loader, Mach-O fixups, ADT, FDT window, C relocations, restore package) | Executed & Verified (`exit_code: 0`) |
| `worktrees/nat-006-recovery-image-20261110/docs/procedures/nat-006/patches/0002-loader-ui-pc-relative-string-tables.patch` | 3,677 | `31c62fa7443d9b5650e99158bed90b8e3f8f93f26a9db66ef98c0033e5320c40` | Eliminates all 37 `R_AARCH64_ABS64` relocations in `shim/e1s-xnu/ui.c.o` | Applied & Verified in `build-002` |
| `worktrees/nat-006-recovery-image-20261110/tests/test_e1s_recovery.py` | 7,739 | `c074f1e0ba9d8d3aa2789b5c8150d71a75a8335cb6a355dd475286762fad9910` | 4 unit test suites (synthetic build, cpio/tar round-trip, negative/corruption cases, `build-002` verification) | Executed & Verified (`4/4 OK`) |
| `artifacts/nat-006/build-002/recovery-nat006.img` | 100,663,296 | `c632d77c19c3bd73869da808fba793040c4279208882f261c61308fa3f069376` | Built `RECOVERY`-format image (`0001` + `0002` loader patches + `STR-041` XNU + synthesized ADT) | Verified on host (`verify.json` `ok: true`) |
| `artifacts/nat-006/build-002/loader/Image` | 204,800 | `0a90ec8b77df0138b095429391f95ac4fb9badd9ed57151b7a10c09cdfeb1067` | Patched ARM64 Linux `Image`-header loader (`0` C object `R_AARCH64_ABS*` relocations) | Verified on host |
| `artifacts/nat-006/build-002/Image.payload` | 21,759,584 | `e25ff22d5c1cd1a2874a9153ec8208f28efb54edbe99391fa083b6b80bc21f3a` | `loader/Image` (204,800 B) + `payload.bin` (21,554,784 B) | Verified on host |
| `artifacts/nat-006/build-002/payload.bin` | 21,554,784 | `346ea74c2a5ad13a8d532286920c1eddd901a706e6de16a2968318bdaf2fa670` | `SWEETXNU` v1 payload (`10` segments, `entry_va=0xfffffff00743b4a8`, `cmdline="e1s.hold=10 debug=0xc serial=3 cpus=1 keepsyms=1 -v"`) | Verified on host |
| `artifacts/nat-006/build-002/e1s.adt` | 13,956 | `1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e` | Synthesized 20-node Apple DeviceTree (no Apple donor `/product` node) | Verified on host |
| `artifacts/nat-006/build-002/restore/recovery.img` | 100,663,296 | `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` | Byte-identical copy of verified stock `RECOVERY` | Verified against live phone & backup |
| `artifacts/nat-006/build-002/restore/recovery-stock-odin.tar` | 100,669,440 | `2787aa3e07d1f09d5f2c808166e0640719f111a618105ceed1ef67ea721fe84e` | USTAR archive containing `recovery.img` (`100,663,296` B) for Odin/Download Mode restore | Verified on host |
| `artifacts/nat-006/build-002/report.json` | 34,283 | `60ea8dfa5a6b78b173f37373bb75338d94858e28cf638b8690455ccb6206b04a` | Full build command log and hash manifest (`outcome: pass`) | Verified on host |
| `artifacts/nat-006/build-002/verify.json` | 7,929 | `78873522a7d24d6f9d58ce9d045d8331fe845cd62f072fe114278b5799cf7339` | Independent verification report (`20/20` checks `ok: true`) | Verified on host |
| `artifacts/nat-006/build-002/window-check/report.json` | 13,530 | `efc51826e9764eb88d9901f0e70f20cd4db719435cef9545ae384868309a6208` | ASan/UBSan runtime FDT window & framebuffer harness report (`3/3` scenarios `ok: true`) | Verified on host |

---

## 3. Comparison of Claimed Results vs. Existing Reports & 5-Way Fact Separation

### 3.1. State at `ac22ef5` (Before This Session) vs. Current Verified State (`build-002`)

| Item / Claim | Status at Commit `ac22ef5` (Prior Session) | Status After Current Session (`build-002`) |
|---|---|---|
| Loader FDT/FB patch (`0001-loader-sboot-dynamic-reservations-and-framebuffer.patch`) | **Source saved** (`7,655` B, `dbfb5c3a...`); **command executed** & **result verified** in `artifacts/nat-006/window-002/report.json` (`c1a3f412...`) | Preserved unchanged; supplemented by `0002-loader-ui-pc-relative-string-tables.patch` (`31c62fa7...`) fixing 37 `R_AARCH64_ABS64` relocations in `ui.c.o` |
| Host FDT window & framebuffer check (`check_loader.py` + `window_harness.c`) | **Command executed** & **result verified**: `window-001/report.json` proved unpatched loader failed (`reserved_ranges=-1`); `window-002/report.json` proved patched loader selects `0x9de400000+0x20000000` and FB `0xfa200000` (`source=2`) | Re-executed and verified during `build-002` in `artifacts/nat-006/build-002/window-check/report.json` (`efc51826...`) |
| Trial payload with `STR-041` kernel in scratchpad | **Command executed** in `/tmp/.../scratchpad/payloadtest/payload.bin` (`21,554,784` B, `9726b649...`), uncommitted outside repo | Formally built inside repo artifacts (`artifacts/nat-006/build-002/payload.bin`, `346ea74c...`) and verified segment-by-segment against `STR-041` `kernel.unstripped` |
| Image builder `tools/build/e1s_recovery.py` | **Source saved** (`18,094` B, `35f76508...`), **never executed**; contained a latent bug where `git apply` inside `artifacts/nat-006/<run>/source` silently skipped `0001` patch | Bug fixed (`git --git-dir=/dev/null apply` + postimage hash assertion); **command executed** (`build-001`, `build-002`) & **result verified** (`report.json` `60ea8dfa...`) |
| Independent verifier `docs/procedures/nat-006/verify_image.py` | **Execution interrupted** while writing file at `2026-11-10T05:46:02Z` (`1,723` B, 48 lines, `efa16a92...`) | Completed (`28,590` B, `913e4018...`); **command executed** & **result verified** (`20/20` checks pass in `artifacts/nat-006/build-002/verify.json`) |
| Unit tests `tests/test_e1s_recovery.py` | **Result absent** (file did not exist at `ac22ef5`) | Created (`7,739` B, `c074f1e0...`); **command executed** & **result verified** (`Ran 4 tests in 0.002s - OK`) |
| Built and verified `RECOVERY` image (`recovery-nat006.img`) | **Result absent** (no image existed at `ac22ef5`) | **Command executed** & **result verified on host** (`artifacts/nat-006/build-002/recovery-nat006.img`, `100,663,296` B, `c632d77c...`) |
| Native hardware boot via `RECOVERY` on `SM-S921B` | **Result absent / unknown** | **Result absent / unknown** (intentionally stopped at Step 4 pre-flash recovery safety gate; `RECOVERY` partition untouched) |

### 3.2. Five-Way Fact Classification Summary

1. **Source saved (`исходник сохранён`)**:
   - `docs/procedures/nat-006/patches/0001-loader-sboot-dynamic-reservations-and-framebuffer.patch` (`dbfb5c3a...`)
   - `docs/procedures/nat-006/patches/0002-loader-ui-pc-relative-string-tables.patch` (`31c62fa7...`)
   - `docs/procedures/nat-006/check_loader.py` (`bb44b13c...`) and `docs/procedures/nat-006/window_harness.c` (`35162854...`)
   - `tools/build/e1s_recovery.py` (`648a351c...`, updated from `ac22ef5` `35f76508...`)
   - `docs/procedures/nat-006/verify_image.py` (`913e4018...`, completed from interrupted `ac22ef5` `efa16a92...`)
   - `tests/test_e1s_recovery.py` (`c074f1e0...`)
2. **Command actually executed (`команда действительно выполнялась`)**:
   - Prior session: `check_loader.py` for `window-001` and `window-002`; scratchpad `mkadt.py` and `mkpayload.py`.
   - Current session: ADB/root live partition hash verification against `devices/recovery/backups/2026-11-10/` and `artifacts/device-backup/2026-11-10-session1/`; `e1s_recovery.py --run build-001` and `--run build-002`; `verify_image.py`; `unittest discover -s worktrees/nat-006-recovery-image-20261110/tests -p "test_e1s_recovery.py" -v`.
3. **Result verified (`результат проверен`)**:
   - Host FDT memory window selection (`0x9de400000+0x20000000`) and framebuffer discovery (`0xfa200000+0x9a3f80`, `source=2`) on the phone's measured `runtime.dtb` across all 3 placement scenarios (`window-002/report.json` and `build-002/window-check/report.json`).
   - Host build and byte-level verification of `artifacts/nat-006/build-002/recovery-nat006.img` (`100,663,296` B, `20/20` checks in `verify.json`), including zero `R_AARCH64_ABS*` relocations across all C objects (`loader.c.o`, `ui.c.o`, `adt_patch.c.o`, `gic.c.o`, `fdt.c.o`) and exact stock `RECOVERY` restore package (`restore/recovery.img` and `restore/recovery-stock-odin.tar`).
   - Live phone (`[redacted-device-serial]`) health (`sys.boot_completed=1`), unlocked bootloader token (`androidboot.verifiedbootstate = "orange"`, `androidboot.vbmeta.device_state = "unlocked"`), and byte-identical match of all 7 backed-up partitions.
4. **Execution interrupted (`выполнение прервано`)**:
   - In the prior session (`ac22ef5`), writing `docs/procedures/nat-006/verify_image.py` was interrupted at line 48 (`1,723` B) before `e1s_recovery.py` could be run. (Resolved in this session.)
5. **Result absent or unknown (`результат отсутствует или неизвестен`)**:
   - Whether S-Boot on `SM-S921B` (`S921BXXS9BYH3`) accepts a modified `RECOVERY` image with an updated in-partition `AVB0` hash descriptor size and stale signature when `androidboot.vbmeta.device_state = "unlocked"`.
   - Exact physical addresses where S-Boot places `kernel`, `ramdisk`, and `DTB` during a `RECOVERY`-mode boot (only normal-boot placement `0x80080000` / `0x88000000` / `0x89f00000` is measured in `NAT-005`).
   - Whether S-Boot enters the `RECOVERY` kernel at EL1 with `SCTLR_EL1.M=0` or with `SCTLR_EL1.M=1` and whether `0x9de400000` is accessible before `SCTLR_EL1.M` is cleared (`NAT-010`).
   - Whether DECON/DPP continues scanning out `0xfa200000` in packed 32bpp (`stride=4320`) during `RECOVERY` entry without DPU clock/power teardown.
   - Whether `STR-041` XNU reaches `arm_init` / `pe_init_platform` on S5E9945 hardware without faulting.

---

## 4. Follow-Up Tasks Registered in `state/lab.json`

To resolve the pre-flash blockers cleanly before any `RECOVERY` write is attempted, the following tasks were registered in `state/lab.json` with dependencies on `NAT-006`:

- **`NAT-008`** (`depends_on: ["NAT-006"]`): *Install and verify host Download Mode flashing tool (`odin4`/`heimdall`) for stock `RECOVERY` restore*.
- **`NAT-009`** (`depends_on: ["NAT-006", "NAT-007"]`): *Integrate S5E9945 hardware watchdog arming and one-shot PMU recovery-reason clearing into the E1S `RECOVERY` loader*.
- **`NAT-010`** (`depends_on: ["NAT-006"]`): *Harden E1S loader EL1 MMU/cache state before high-DRAM (`0x9de400000`) window zeroing and segment copy*.
