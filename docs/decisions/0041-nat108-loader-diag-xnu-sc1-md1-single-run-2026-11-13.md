# Decision 0041: Single native run of `loader-diag-xnu-sc1-md1` (NAT-108 / Stage C1 + hb + fb_diff=1)

Date: 2026-11-13
Scope: `native` (RECOVERY-only `/dev/block/sda18`, single run, standing grant under decision 0019)
Status: Active single-run specification (`native = false` until preflight is ready; close `native = false` immediately after stock `RECOVERY` restore)

## Rationale

`NAT-107` (`loader-diag-xnu-sb2-md1`) validated Stage B (`backboardd` + `libhakios.dylib` + `containermanagerd` alive, `MiniIOSurface` surfaces 1 and 3, 3 `MiniIOMobileFramebuffer` swaps, `867 MB` free / `1504 MB` available RAM) and showed why row B5 had zero positive pixel diffs: `SpringBoard` was not yet in the small root (`LaunchDaemons` lacked `SpringBoard`/`lsd`/on-demand services and `var/` preferences), and `fb_diff=1` was not set in kernel boot-args.

`NAT-108` advances cleanly to Stage C1 (`loader-diag-xnu-sc1-md1`) identically to `NAT-106` except:
- `md0` small root (`artifacts/nat-108/pid1-sc1-hb/root.apfs`, `4,194,304` bytes, `423` files) combines `NAT-106`'s Stage B + hb base with all `22` donor `DARWIN_JOBS` plus `--rest` on-demand `LaunchDaemons`/`LaunchAngels` (`405` plists total including `com.nat085.ps`), pinned donor prebuilt `lib/libhakios.sb.dylib` (`0755`, SHA-256 `d4f1c6b06b4b016b1a3ea77d741382053efde0093a5a8f77226a215bee87b232`), two-line `etc/inject.conf` targeting `SpringBoard` in addition to `backboardd`/`containermanagerd`, the `8` pinned `var/` preference plists (`purplebuddy` `SetupDone=True`, `springboard`, `frontboard`, `migration`, etc.), and fixed zoneinfo/`var.skel` entries.
- Kernel boot-args append ` fb_diff=1` before ` xrd=md0` (`246 < 256` bytes) and update `nat_attempt=NAT106-sb2` -> `nat_attempt=NAT108-sc1`, keeping `NAT-106`'s `512 KiB` (`524288u`) `NAT062_TAIL_RETURN`, `4096u` burst, `10 * N62_WAIT()` settle delay, XNU kernel, ADT, and streamed `2,475,720,704`-byte `md1` APFS root unchanged.

## Pinned Inputs and Targets

- Device target: `SM-S921B` (`e1s`, `S921BXXS9BYH3`), `/dev/block/sda18` (`RECOVERY`, `100,663,296` bytes only; zero writes to `BOOT`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `USERDATA`, `super`, `EFS`, or GPT).
- Stock `RECOVERY` (`devices/recovery/backups/2026-11-10/recovery.img`): SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`.
- Candidate `RECOVERY` (`artifacts/nat-108/package-001/loader-diag-xnu-sc1-md1/recovery.img`): SHA-256 `90eecfbc45e055d8514639512c56351668f25e2aae7cd0ea6f50241a744fcdbb`.
- Loader `Image` (`385,024` bytes): SHA-256 `4604b814a09be6f4fc49b8a2b506fcce6d9e9f2331492b8a20de683ef3eec5e5`.
- Payload `Image.payload` (`26,134,288` bytes at offset `2048`): SHA-256 `67ec6504724b70db21b7eecc1f3c2c837166561e239303a3d3b56f048e3c9524`.
- Small root `md0` (`artifacts/nat-108/pid1-sc1-hb/root.apfs`, `4,194,304` bytes, `423` files): SHA-256 `bb02a20bd9ec5ad87df634adbed93e9936ae24c3c32901ed1369b274850e9725`.
- Padded root image (`artifacts/nat-083/system-padded.apfs`, `2,475,720,704` bytes): SHA-256 `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`.
- Launcher: `docs/procedures/nat-108/session_nat108.py` (`--image loader-diag-xnu-sc1-md1`).
- One-shot marker: `artifacts/nat-108/native-attempt-loader-diag-xnu-sc1-md1-used.json` (one write, one readback check, one `adb reboot recovery`; zero retries).
- Analysers (read-only after collector/watcher exit): `docs/procedures/nat-108/analyze_nat108.py` (`--mode stage-c`, `--mode stage-b`, `--mode hb`, `--mode stage-a`, `--mode chain`).

## Execution & Recovery Obligations

1. Confirm `NAT-108` host tests and mutation gate are `done`, host load average (`1-min < 6.0`) and background worker list are idle.
2. Run read-only preflight first (`session_nat108.py --image loader-diag-xnu-sc1-md1 --out ...` without `--execute`).
3. Open `native = true` citing `docs/decisions/0041-nat108-loader-diag-xnu-sc1-md1-single-run-2026-11-13.md` and run `--execute` once.
4. On watchdog return to Android (or Download Mode recovery via `NAT-013` if needed), immediately restore stock `RECOVERY`, verify with `check_android.py` and `restore_stock.py assess`, close `native = false`, wait for collector and watcher exit, and evaluate `analyze_nat108.py`.
