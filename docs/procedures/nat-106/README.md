# NAT-106: Stage B + Heartbeat Host Build, Pack, Analyser, Driver, and Mutation Gate (`loader-diag-xnu-sb2-md1`)

Host-only preparation for Stage B (`com.apple.backboardd`, `libhakios.dylib`, `/redwood/etc/inject.conf`) on top of `NAT-105`'s proven heartbeat + `8192 + 524288` B8-safe logging pipeline. Nothing ran on a phone.

## Artifacts and Changes

1. **Stage B + heartbeat small root (`build_sb2_hb_root.py` -> `artifacts/nat-106/pid1-sb2-hb/`)**:
   - Wraps `docs/procedures/nat-099/build_stage_b_root.py` over the pinned `NAT-101` base (`artifacts/nat-101/pid1-hb/root.apfs`, `sha256 97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c`, `26` files).
   - Adds `LaunchDaemons/com.apple.backboardd.plist`, `lib/libhakios.dylib`, and `etc/inject.conf` (`/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system\n`), yielding `29` files (`root.apfs`: `4,194,304` bytes, `sha256 182aead762086a1f322995bd0f05365d7115184d8d775bac3563aa527fa61c56`) with kernel `apfs_lib` readback `ok`.
2. **Image build and packaging (`build.py`, `docs/procedures/nat-044/package.py` -> `artifacts/nat-106/{build-001,package-001}`)**:
   - Builds `loader-diag-xnu-sb2-md1` (`nat_attempt=NAT106-sb2`, total cmdline `236` bytes), keeping `NAT062_BURST=4096u` and `10x N62_WAIT()` on `NAT062_WHY_RETURN`, and widening `NAT062_TAIL_RETURN` from `262144u` to `524288u` (`512 KiB`, `524288 % 96 = 32 != 0`).
   - `Image`: `385,024` B (`f6b1d859cc049c7f44fab58589bb0f604ddab68b6f4e5e561d76fed5d5c991cd`)
   - `Image.payload`: `26,134,288` B (`f1edc9b37d70f917d816cc462a5b09aacf152b2a0c7fa6b41ea98b99e8fb97fb`)
   - `recovery.img`: `100,663,296` B (`c64bbe0b73b78148b148dbb5e3780e803a2e177ace19635711f86d9f22ebd542`)
3. **Analyser (`analyze_nat106.py`)**:
   - Raises `TAIL_MAX[2] = 524288` across wrapped `NAT-104` / `NAT-097` / `NAT-087` / `NAT-102` analysers cleanly and adds `--mode stage-b` implementing the `B0`-`B6` ladder (`no-kernel-text` through `panel-pixels-changed`).
4. **Driver & single-run decision (`derive106.py` -> `session_nat106.py`, `docs/decisions/0040-...`)**:
   - Counted derivation (9 substitutions from `session_nat104.py`), verified by `derive106.py --check`.
5. **Verification**:
   - `test_nat106.py` (`11/11` passing, including `-DNAT062_HOST -Wall -Wextra -Werror` C harness round-trips at `400 KiB` / `600 KiB` and `B0`-`B6` ladder checks).
   - `mutate_nat106.py`: `480` mutants (`442` killed, `4` documented equivalent in `equivalent.json`, `34` invalid, `0` unexplained survivors).
