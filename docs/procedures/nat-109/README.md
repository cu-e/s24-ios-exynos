# NAT-109: Native run of `loader-diag-xnu-sc1-md1` (decision `0041`) — Stage C1 `SpringBoard` + `libhakios.sb.dylib` + `fb_diff=1`

**Outcome:** `pass` (all `NAT-109` measurement, restore, and analysis acceptance criteria met; pre-registered `analyze_nat108.py` returned **`row C4 springboard-exited`**, **`row B5 fb-swaps-no-diff`**, **`row H5 hb-ps-lists`**, **`row A2 some-daemons-alive`**, and **`chain_row 7 download`**, while post-hoc inspection established that **`SpringBoard[13]` actually survived through `hb` round 5** and was missed by `analyze_nat108.py` due to `ps -A` truncating the command column to `.../SpringBoard.app/SpringBoa`).  
**Decision:** [0041-nat108-loader-diag-xnu-sc1-md1-single-run-2026-11-13.md](../../decisions/0041-nat108-loader-diag-xnu-sc1-md1-single-run-2026-11-13.md)  
**Image:** `loader-diag-xnu-sc1-md1` (`artifacts/nat-108/package-001/loader-diag-xnu-sc1-md1/recovery.img`, SHA-256 `90eecfbc45e055d8514639512c56351668f25e2aae7cd0ea6f50241a744fcdbb`)  
**Target partition:** `RECOVERY` (`/dev/block/sda18`, `100,663,296` bytes) only; restored to pinned stock `recovery.img` (`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) and verified in Android (`SM-S921B`, `e1s`, `S921BXXS9BYH3`, `restore_stock.py assess` `pass`).

## Key Results

1. **Delivery, KL dump (`gap=0`, `hole=0`), and Download Mode return:**
   - Host 1-min load before launch was `< 6.0`.
   - Full `2,475,720,704`-byte padded APFS root (`4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`) delivered to `md1` over USB in `152.598 s` (`16.224 MB/s`), `296` TRBs, `0` retries/errors/aborts/gaps/rejects/resets.
   - `glue62_impl.h` returned the complete `455,754`-byte `why=2` dump of boot `000002` (`4,942` frames / `4,940` records on collector, `4,749` KL records reconstructed, `8,192` head + `447,562` tail, `drops=0`, `faults=0`, `hole_bytes=0`, `gap_bytes=0`, `begin_inferred=false`).
   - USB return transfer (`557,136` engine bytes / `518,435`-byte framed dump, vs `149,450` B in `NAT-107`) took ~`118.2 s` and hit the loader's return-after-reboot watchdog (`HOLD stage=0x51 code=0x223e`), enumerating cleanly in Download Mode (`04e8:685d` `SAMSUNG USB`) at `dt = 379.29 s` (`cls: cap-reset`).

2. **Pre-registered analysers (`analyze_nat108.py`) vs. Post-hoc findings:**
   - `--mode stage-c`: **`row C4 springboard-exited`** (`hole_bytes=0`, `gap_bytes=0`, `springboard_in_jobs=true`, `springboard_spawns=[]`, `springboard_alive_in_last_list=false`, `fb_swaps=2` with layer `0x0 -> 0x1`, `diff_positive=0`, `lsd_cpu_monitor_denials=241`).
   - `--mode stage-b`: **`row B5 fb-swaps-no-diff`** (`backboardd_spawns=[{"clock": 190.860619, "pid": 18}]`, `backboardd_alive_in_last_list=true`, `fb_swaps=2` + `layers 0x0 -> 0x1`).
   - `--mode hb`: **`row H5 hb-ps-lists`** (`hb_marks=5`, `ps_lists=8`, `rounds_with_logd=[4, 5]`, round `5` at `up=54 s` lists `71` live processes).
   - `--mode stage-a`: **`row A2 some-daemons-alive`** (`9` of `10` self-starting jobs reported alive; `com.apple.SpringBoard` missed in last `ps` list).
   - `--mode chain`: **`chain_row 7 download`** (`chain_pass: false` because of Download Mode return).
   - **Post-hoc correction for `analyze_nat108.py` (fixed in `NAT-110` Stage C2 analyser, not retroactively):**
     - `SpringBoard[13]` **did spawn** at `00:03:11.125` (`launchd` elided `xpcproxy` via `service spawned with pid 13` / `Successfully spawned SpringBoard[13] because system support`), **remained alive in `hb` rounds 2, 3, 4, and 5** (`PID 13`, `TIME 0:05.68` in round 5 at `up=54 s`, line `3385` of `kernel-text.txt`), and never exited.
     - `analyze_nat108.py` checked only `xpcproxy spawned` (`spawns=[]`) and un-truncated `ps -A` command suffix `SpringBoard`, whereas BSD `ps -A` truncated line `3385` to `/System/Library/CoreServices/SpringBoard.app/SpringBoa` (`54` chars). Only `com.apple.ABDatabaseDoctor` and `com.apple.datamigrator[31]` (`code=0`) exited during the `60 s` window.

3. **`libhakios.sb.dylib` / `libhakios.dylib` & `MiniIOMobileFramebuffer` telemetry:**
   - `init` logged `library insertion: /redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system;/redwood/lib/libhakios.sb.dylib SpringBoard`.
   - `SpringBoard[13]` installed all HakiOS hooks cleanly: `SpringBoard: no GPU draws, vibrant views are plain (the lock screen's clock is white)`, `activation answered here, setup assistant refused, application snapshots as JPEG, the side button's long press checked, battery level from QG, battery state from QG, poster switcher not offered`, cellular status-bar aggregator hooks, and battery UI hooks.
   - `backboardd[18]` (`window server hooks installed`, `no accelerated renderer; the software one will draw`) executed `render_update -> 0x1` twice (`[230.581s]` and `[231.110s]`), allocating `1125x2436 BGRA` `MiniIOSurface` `2` and `4` (`11,239,424` B each) and performing `2` `MiniIOMobileFramebuffer` swaps (`layers 0x0 -> 0x1`).
   - `MiniIOMobileFramebuffer` emits stats and `fb_diff` lines only when a swap occurs `>= 5 s` after `fStatSince` (`230.581 s + 5 s = 235.581 s`); no swap occurred after `231.110 s`, so `fb_stats` and `fb_pixel_diffs` were empty (`[]`).
   - Memory at `[238.863s]`: `free 581, files 855, programs 136, wired 2522 (4 surfaces 33, ramfs 20), compressor 0 (holding 0) MB; available 1436`.

4. **Diagnostic Findings for Next Stage (`NAT-110`):**
   - `71` concurrent processes on `cpus=1` (`753` launchd notable lines, `hb` round 2 `ps` took `7,666 ms`) delayed `backboardd`'s first swap to `~40 s` into the `60 s` window (`230.58 s`), and bloated the KL dump from `149 KB` to `455 KB` (`118.2 s` USB return -> Download Mode).
   - `lsd[29]` consumed `10.22 s` CPU and emitted `241` `denied attempt to escape CPU monitor (missing required entitlement)` lines to the kernel message buffer through the end of the boot (`[248.809s]`).
   - Top failed XPC lookups recorded by `stage-c`: `com.apple.mobileassetd.v2` (`18`), `com.apple.commcenter.coretelephony.xpc` (`15`), `com.apple.commcenter.xpc` (`13`), `com.apple.locationd.registration` (`12`), `com.apple.identityservicesd.embedded.auth` (`11`), `com.apple.wifi.manager` (`8`).
