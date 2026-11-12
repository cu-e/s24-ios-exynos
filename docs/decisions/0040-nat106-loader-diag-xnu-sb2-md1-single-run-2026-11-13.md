# Decision 0040: Single native run of `loader-diag-xnu-sb2-md1` (NAT-106 / NAT-107, Stage B + hb + 512 KiB KL tail)

Date: 2026-11-13
Scope: `native` (RECOVERY-only `/dev/block/sda18`, single run, standing grant under decision 0019)
Status: Active single-run specification (`native = false` until preflight is ready; close `native = false` immediately after stock `RECOVERY` restore)

## Rationale

`NAT-105` (`loader-diag-xnu-hb2-md1`) closed blockers B7 and B8 (`gap=0, hole=0`, `11` Apple Stage A daemons alive in `/bin/ps` lists including all `7` self-starting jobs).

`NAT-106` advances cleanly to Stage B by building `loader-diag-xnu-sb2-md1` identically to `NAT-104` except:
- `md0` small root (`artifacts/nat-106/pid1-sb2-hb/root.apfs`, `4,194,304` bytes, `29` files) combines `NAT-101`'s heartbeat loop (`pid1-hb`) with `NAT-099`'s three Stage B files (`LaunchDaemons/com.apple.backboardd.plist`, `lib/libhakios.dylib`, `etc/inject.conf` targeting `backboardd containermanagerd containermanagerd_system`).
- `glue62_impl.h` (`sha256 7fa35d764441bca2ce000408a2fea17672c149a45129047224c70880dcc71d60`) sets `NAT062_TAIL_RETURN = 524288u` (`512 KiB`, `524288 % 96 = 32 != 0`) while keeping `NAT062_BURST = 4096u` and the `10 * N62_WAIT()` (`5 s`) settle delay on `NAT062_WHY_RETURN` before emitting `KL begin`.
- Kernel command line tag updates `NAT104-hb2` -> `NAT106-sb2` (`nat_attempt=NAT106-sb2`); everything after the `385,024`-byte loader region aside from `md0` (same XNU payload, same ADT, and streamed `2,475,720,704`-byte `md1` APFS root) stays unchanged.

## Pinned Inputs and Targets

- Device target: `SM-S921B` (`e1s`, `S921BXXS9BYH3`), `/dev/block/sda18` (`RECOVERY`, `100,663,296` bytes only; zero writes to `BOOT`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `USERDATA`, `super`, `EFS`, or GPT).
- Stock `RECOVERY` (`devices/recovery/backups/2026-11-10/recovery.img`): SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`.
- Candidate `RECOVERY` (`artifacts/nat-106/package-001/loader-diag-xnu-sb2-md1/recovery.img`): SHA-256 `c64bbe0b73b78148b148dbb5e3780e803a2e177ace19635711f86d9f22ebd542`.
- Loader `Image` (`385,024` bytes): SHA-256 `f6b1d859cc049c7f44fab58589bb0f604ddab68b6f4e5e561d76fed5d5c991cd`.
- Payload `Image.payload` (`26,134,288` bytes at offset `2048`): SHA-256 `f1edc9b37d70f917d816cc462a5b09aacf152b2a0c7fa6b41ea98b99e8fb97fb`.
- Small root `md0` (`artifacts/nat-106/pid1-sb2-hb/root.apfs`, `4,194,304` bytes, `29` files): SHA-256 `182aead762086a1f322995bd0f05365d7115184d8d775bac3563aa527fa61c56`.
- Padded root image (`artifacts/nat-083/system-padded.apfs`, `2,475,720,704` bytes): SHA-256 `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`.
- Launcher: `docs/procedures/nat-106/session_nat106.py` (`--image loader-diag-xnu-sb2-md1`).
- One-shot marker: `artifacts/nat-106/native-attempt-loader-diag-xnu-sb2-md1-used.json` (one write, one readback check, one `adb reboot recovery`; zero retries).
- Analysers (read-only after collector/watcher exit): `docs/procedures/nat-106/analyze_nat106.py` (`--mode stage-b`, `--mode hb`, `--mode stage-a`, `--mode chain`).

## Execution & Recovery Obligations

1. Confirm `NAT-106` host tests and mutation gate are `done`, host load average (`1-min < 6.0`) and background worker list are idle.
2. Run read-only preflight first (`session_nat106.py --image loader-diag-xnu-sb2-md1 --out ...` without `--execute`).
3. Open `native = true` citing `docs/decisions/0040-nat106-loader-diag-xnu-sb2-md1-single-run-2026-11-13.md` and run `--execute` once.
4. On watchdog return to Android (or Download Mode recovery via `NAT-013` if needed), immediately restore stock `RECOVERY`, verify with `check_android.py` and `restore_stock.py assess`, close `native = false`, wait for collector and watcher exit, and evaluate `analyze_nat106.py`.
