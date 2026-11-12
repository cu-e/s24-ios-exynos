# Decision 0039: Single native run of `loader-diag-xnu-hb2-md1` (NAT-104 / NAT-105, B8 log-window fix)

Date: 2026-11-12
Scope: `native` (RECOVERY-only `/dev/block/sda18`, single run, standing grant under decision 0019)
Status: Active single-run specification (`native = false` until preflight is ready; close `native = false` immediately after stock `RECOVERY` restore)

## Rationale

`NAT-103` (`loader-diag-xnu-hb-md1`) proved via post-hoc kernel analysis that its `116,430`-byte console/dmesg buffer overflowed the `NAT-062` `8192 + 32768` return dump window (`75,470` B gap plus `4,896` B initial USB ring drop), leaving `hb` and `ps` lists unobservable in the unsent middle of the log (blocker B8).

`NAT-104` builds `loader-diag-xnu-hb2-md1` identically to `NAT-102` except:
- `glue62_impl.h` (`sha256 38d8723b033bcb6b969af9ca961586c54f0582c3c56d720dcb0efd5f7b8df863`) sets `NAT062_TAIL_RETURN = 262144u` (`8192 + 262144 = 270336` bytes capacity), lowers `NAT062_BURST` to `4096u`, and inserts a `10 * N62_WAIT()` (`5 s`) settle delay on `NAT062_WHY_RETURN` before emitting `KL begin` while keeping `NAT062_WHY_FINAL` unchanged.
- Kernel command line tag updates `NAT102-hb1` -> `NAT104-hb2` (`nat_attempt=NAT104-hb2`); everything after the `385,024`-byte loader region (XNU payload, ADT, `4,194,304`-byte `md0` small root `97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c`, and streamed `2,475,720,704`-byte `md1` APFS root `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`) is unchanged.

## Pinned Inputs and Targets

- Device target: `SM-S921B` (`e1s`, `S921BXXS9BYH3`), `/dev/block/sda18` (`RECOVERY`, `100,663,296` bytes only; zero writes to `BOOT`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `USERDATA`, `super`, `EFS`, or GPT).
- Stock `RECOVERY` (`devices/recovery/backups/2026-11-10/recovery.img`): SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`.
- Candidate `RECOVERY` (`artifacts/nat-104/package-001/loader-diag-xnu-hb2-md1/recovery.img`): SHA-256 `540b64a5736d444bdf8c0f09a6897c0469b3fb36332dce87f3ff626377bb1963`.
- Loader `Image` (`385,024` bytes): SHA-256 `88f64a746e58df72a8c4a8f81f1bf38c674a3e5f834e041f94873ab237fdbc07`.
- Payload `Image.payload` (`26,134,288` bytes at offset `2048`): SHA-256 `4161da474ddb1c708d8b2674111d8f6e6286a697888a999b6d1fee5963d3d1b7`.
- Padded root image (`artifacts/nat-083/system-padded.apfs`, `2,475,720,704` bytes): SHA-256 `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`.
- Launcher: `docs/procedures/nat-104/session_nat104.py` (`--image loader-diag-xnu-hb2-md1`).
- One-shot marker: `artifacts/nat-104/native-attempt-loader-diag-xnu-hb2-md1-used.json` (one write, one readback check, one `adb reboot recovery`; zero retries).
- Analysers (read-only after collector/watcher exit): `docs/procedures/nat-104/analyze_nat104.py` (`--mode chain`, `--mode stage-a`, `--mode hb`).

## Execution & Recovery Obligations

1. Confirm `NAT-104` host tests and mutation gate are `done`, host load average (`1-min < 6.0`) and background worker list are idle.
2. Run read-only preflight first (`session_nat104.py --image loader-diag-xnu-hb2-md1 --out ...` without `--execute`).
3. Open `native = true` citing `docs/decisions/0039-nat104-loader-diag-xnu-hb2-md1-single-run-2026-11-12.md` and run `--execute` once.
4. On watchdog return to Android, immediately restore stock `RECOVERY` (`session_nat104.py ... --restore`), verify with `check_android.py` and `restore_stock.py assess`, close `native = false`, wait for collector and watcher exit, and then evaluate `analyze_nat104.py`.
