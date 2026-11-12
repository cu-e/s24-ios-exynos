# NAT-103: native run of `loader-diag-xnu-hb-md1` (decision 0038)

Evidence kind **native-device**, outcome **inconclusive** (`analyze_nat102.py` row **H1**, `analyze_nat097.py` row **A8**). The task stays open. The one-shot marker `artifacts/nat-102/native-attempt-loader-diag-xnu-hb-md1-used.json` exists; decision 0038 is consumed.

## What ran

`loader-diag-xnu-hb-md1` (NAT-102) is NAT-096's quiet Stage A image (`com.apple.lsd` omitted) with NAT-101's static heartbeat binary `/redwood/bin/hb` (`16,635` bytes) added to `md0` and `/redwood/bin/hb &` inserted in `etc/rc` immediately before `exec /sbin/launchd.darwin`. It ran once on `SM-S921B`/`e1s` (`S921BXXS9BYH3`) on 2026-11-12 (reboot requested `20:35:29.07Z`, host 1-minute load `1.91` at launch), RECOVERY (`/dev/block/sda18`, sha256 `e938cb4a5578b404685feeb21c0a480285b57157f10f4573fba07f28f5afba94`) only, restored from the pinned stock recovery (`96620b8b...babf67`) via `NAT-013` (`restore_stock.py`), and Android verified (`check_android.py` pass, `restore_stock.py assess` pass: `recovery_readback_matches=true`, `user_data_directories_present`). `native` closed in `state/lab.json`.

## Pre-registered result (run after watcher and collector exited)

| Analyser (unchanged) | Result |
| --- | --- |
| `analyze_nat087.py` (chain) | row `9`, `PARTIAL`, `restore` row `9` (`not-evaluated`): 2 boots of this image, `incomplete` manifest (`3` capture errors: `start-failed`, `producer-reported-drop`, `producer-reported-drop`), `2` collector drops, no reason-0 arrival before stream end (`cap-reset`, Download Mode `04e8:685d` at `+388.23s`). |
| `analyze_nat097.py` (Stage A, reader v2) | row **A8** (`not-evaluated`): `no launchd line in the returned text; the dump's begin record was lost and its geometry was inferred from the end line and the received offsets (NAT-097 rules)`. |
| `analyze_nat102.py` (heartbeat ladder `H0`–`H5`) | row **H1** (`no-hb-line`): `no SWEET hb: line in the kernel text; the dump's begin record was lost and its geometry was inferred (NAT-097 rules)`. `hb_lines`: `0`, `lists_not_from_hb`: `1` (from `/redwood/etc/rc` `$ /bin/ps -A`, 2 rows), `launchd_console_lines`: `0`, `gap_bytes`: `75,470`, `hole_bytes`: `7,968`. |

`H5` was not met; `NAT-103` stays open.

## Post-hoc findings beyond the ladder (not a ladder pass)

Comparison of the inferred dump geometry (`posthoc.json`, `kernel-log-boot2-posthoc.txt`) against NAT-098 (`docs/procedures/nat-098/`):

* **Full 2.31 GiB root delivered cleanly:** `2,475,720,704` bytes in `172.04s` (`14.39 MB/s`, `296` TRBs, `0` retries, `0` device rx errors/aborts/gaps/rejects/resets).
* **Kernel and launchd progression without `lsd` flood:** `init` passed `35/35` checks; `df`, `mount`, `ps`, `vm_stat` printed in `head` (no EIO, `-rwxr-xr-x 1 16635 /redwood/bin/hb` and `-rw-r--r-- 1 1152 /redwood/etc/rc` visible in `ls`); `0` `lsd` CPU-monitor lines across `304` timestamped tail lines (`kernel clock 216.673s .. 269.309s`); `launchd` executed `commit-boot-mode`, `restore-datapartition`, `init-with-data-volume` and skipped 20 boot tasks (`Early boot complete` at `218.659902s`).
* **Userland process activity shifted relative to NAT-098 (circumstantial indicator that `hb` started and forked `/bin/ps`):**
  * In NAT-098 (without `hb`), launchd's 8 simultaneous startup spawns at `218.x` were `pids 9..16`, followed by `pids 17..25` ending at `+1` per `10.0s` (`22, 23, 24, 25`).
  * In NAT-103 (with `hb`), launchd's 8 simultaneous spawns at `218.058s..218.080s` shifted by `+2` to `pids 11..18` (`logd[18]`, `containermanager[14]` named in minisandbox lines), followed by `19, 20, 21, 23, 24` (`pid 22` absent from memorystatus) and four `10.04s`-spaced spawns (`239.145s`, `249.206s`, `259.250s`, `269.291s`) stepping by **`+2` (`pids 25, 27, 29, 31`)** with `pids 26, 28, 30` absent from memorystatus. At `266.728s`, `memory: free 998, files 552, programs 10`.
  * Total dump length increased by **`+4,588` bytes** over NAT-098 (`116,430` vs `111,842`), entirely before `tail`.
* **Root cause of B8/H1 blindness identified (`loader_return.c` + `glue62_impl.h` window geometry):**
  * `loader_return.c` (`loader_log_append_msgbuf()`) appends `\n--- kernel message buffer ---\n` and the kernel `msgbufp` (`~30.5 KiB`) **after** the console ring (`loader_log` bytes `0..~85.5 KiB`).
  * `docs/procedures/nat-062/src/glue62_impl.h` transmits only `NAT062_HEAD_RETURN = 8,192` bytes (`0x0..0x2000`, stopping inside `/redwood/etc/rc` `vm_stat`) and `NAT062_TAIL_RETURN = 32,768` bytes (`0x146ce..0x1c6ce` = `83,662..116,430`), skipping **`75,470` bytes (`gap`)**.
  * Of the `32,768`-byte `tail`, the first `4,896` bytes (`0x146ce..0x159ee`) were lost to the USB ring-overrun drop (`000002` `at_offset=8152 lost_bytes=8708`), and all `27,904` surviving tail bytes (`0x159ee..0x1c6ce`) lie **100% inside the kernel message buffer (`[216.673s .. 269.309s]`)**.
  * Thus, unlike NAT-088 (where `len=57,665` left ~7 KiB of console output inside the `32 KiB` tail), in both NAT-098 (`len=111,842`) and NAT-103 (`len=116,430`) **zero bytes of the console ring after byte `8,192` were included in the surviving tail**. Neither `launchd` nor `hb` console output can be observed or falsified through `/dev/console` until the unsent `gap` / log-channel limit (`B8`) is lifted.

## Files

`task.json`, `README.md`, `evidence.json`, `kernel-text-excerpt.txt`. Raw collector archive, delivery report, preflight/run/restore reports, and unsanitized kernel text (`kernel-log-boot2-posthoc.txt`, which includes the host username in the kernel version banner) remain in gitignored `artifacts/nat-103/`. Device inventory is recorded in `devices/local-2026-11-12-nat103.json`.
