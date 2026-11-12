# NAT-110: Stage C2 + heartbeat RECOVERY build & analyzer (`loader-diag-xnu-sc2-md1`)

Host-only preparation for Stage C2 (`SpringBoard` CPU headroom + quiet `launchd` return log); nothing here ran on a phone.

## Artifacts built and pinned

1. `build_sc2_hb_root.py` derives `artifacts/nat-110/pid1-sc2-hb/root.apfs` (`4,194,304` B, `396` files, `377` LaunchDaemons, `kernel_apfs_lib_readback` `396` files / `0` mismatches, `sha256 6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c`) from pinned `NAT-108` `pid1-sc1-hb` (`423` files, `bb02a20bd9ec5ad87df634adbed93e9936ae24c3c32901ed1369b274850e9725`), adding empty `etc/quiet` (`0644`) to suppress synchronous console `launchd` stderr (`2,086` lines / `279,524 B` in `NAT-109`) and pruning `com.nat085.ps.plist` plus `27` non-UI wireless/cloud/telemetry/sharing/speech/widget plists (`PRUNE_PLISTS`).
2. `build.py` + `docs/procedures/nat-044/package.py` build `loader-diag-xnu-sc2-md1` (`nat_attempt=NAT110-sc2`, `fb_diff=1`, `loader_return_after=63`, cmdline `246 < 256` bytes, `--deadline-s 365`, keeping `NAT062_TAIL_RETURN=524288u`, `NAT062_BURST=4096u`, `10x` settle waits, `glue62_impl.h` `7fa35d764441bca2ce000408a2fea17672c149a45129047224c70880dcc71d60`):
   - `Image`: `385,024` B, `sha256 954aef2c80da0d326cb63574422ac5be2420effcd892cd7ae6f468f95f077c88`
   - `Image.payload`: `26,134,288` B, `sha256 31a9f150ba75d967fa074a320998ba6b88986c952ade1ff002ac718bf44a02c6`
   - `recovery.img`: `100,663,296` B, `sha256 3e0c594060a58e4045ef6dee417931d8e79ed8fb139de38b5cb18d1294788258` (`differing_4k_pages: 19627`)
3. `derive110.py` derives `session_nat110.py` from `session_nat108.py` (`9` substitutions; `derive110.py --check` exit `0`).
4. `analyze_nat110.py` fixes truncated `SpringBoa*` `ps -A` row matching, matches `service spawned with pid <N>` alongside `xpcproxy`, and tracks `etc_quiet_active` when `launchd_console_lines == 0`, reclassifying `artifacts/nat-109/run-001/archive` from false `C4` to `C6 fb-swaps-no-diff`.
5. `test_nat110.py` (`12/12` OK) and `mutate_nat110.py` (`412` mutants: `392` killed, `2` equivalent in `equivalent.json`, `18` invalid, `0` unexplained survivors).
6. Single-run decision: `docs/decisions/0042-nat110-loader-diag-xnu-sc2-md1-single-run-2026-11-13.md`.
