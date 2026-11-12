# NAT-107: Native run of `loader-diag-xnu-sb2-md1` (decision `0040`) — Stage B `backboardd` + `libhakios.dylib` + `MiniIOMobileFramebuffer` swaps

**Outcome:** `pass` (all acceptance criteria met; pre-registered analysers reached **`row B5 fb-swaps-no-diff`**, **`row H5 hb-ps-lists`**, and **`row A1 base-daemons-alive`**).  
**Decision:** [0040-nat106-loader-diag-xnu-sb2-md1-single-run-2026-11-13.md](../../decisions/0040-nat106-loader-diag-xnu-sb2-md1-single-run-2026-11-13.md)  
**Image:** `loader-diag-xnu-sb2-md1` (`artifacts/nat-106/package-001/loader-diag-xnu-sb2-md1/recovery.img`, SHA-256 `c64bbe0b73b78148b148dbb5e3780e803a2e177ace19635711f86d9f22ebd542`)  
**Target partition:** `RECOVERY` (`/dev/block/sda18`, `100,663,296` bytes) only; restored to pinned stock `recovery.img` (`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) and verified in Android.

## Key Results

1. **Delivery & USB collector (`gap=0`, `hole=0`):**
   - Full `2,475,720,704`-byte padded APFS root (`4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`) delivered to `md1` over USB in `210.711 s` (`11.749 MB/s`), `296` TRBs, `0` retries/errors/aborts/gaps/rejects/resets.
   - `glue62_impl.h` (`NAT062_BURST=4096u`, `NAT062_TAIL_RETURN=524288u`, settle waits) returned the entire `149,450`-byte `why=2` dump of boot `000002` (`1,756` frames / `1,754` contiguous records, `8,192` head + `141,258` tail, `drops=0`, `faults=0`, `hole_bytes=0`, `gap_bytes=0`, `begin_inferred=false`).
   - Device exited cleanly into Download Mode (`04e8:685d` `SAMSUNG USB`) at `dt = 387.72 s` (`cls: cap-reset`).

2. **Pre-registered analysers (`analyze_nat106.py`):**
   - `--mode stage-b`: **`row B5 fb-swaps-no-diff`** (`hole_bytes=0`, `gap_bytes=0`, `backboardd_in_jobs=true`, `backboardd_spawns=[{"clock": 256.691374, "pid": 14}]`, `backboardd_exits=[]`, `backboardd_alive_in_last_list=true`, `fb_swaps=3` + `swap #1` layers transition `0x0 -> 0x1`, `diff_positive=0`).
   - `--mode hb`: **`row H5 hb-ps-lists`** (`hb_marks=6`, `ps_lists=13`, `rounds_with_logd=[3, 4, 5, 6]`, last round `6` names `18` processes).
   - `--mode stage-a`: **`row A1 base-daemons-alive`** (`all 8 self-starting jobs are in the last complete ps list; alive in total: 13`, `launchd_lines=392`, `last_list_rows=18`, `last_list_cut=false`).
   - Alive Apple processes at `hb` round 6 (`up=54s`, `PID 1..37`): `/sbin/launchd.darwin`, `/usr/libexec/runningboardd`, `/System/Library/CoreServices/powerd.bundle/powerd`, `/usr/libexec/backboardd`, `/usr/libexec/containermanagerd`, `/usr/sbin/distnoted`, `/usr/libexec/usermanagerd`, `/usr/libexec/fseventsd`, `/usr/libexec/logd`, `/usr/sbin/notifyd`, `/usr/libexec/logd_helper`, `ACCHWComponentAuthService` (`CoreAccessories`), `/usr/sbin/cfprefsd`, `/usr/libexec/MobileGestaltHelper`, `analyticsd` (`CoreAnalytics`), `datamigrator` (`DataMigration`, cleanly exited `0` afterwards).

3. **`libhakios.dylib` & `backboardd` Stage B telemetry:**
   - `init` logged `library insertion: /redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system`.
   - `containermanagerd[15]` printed `hakios: container manager: no personas` and stayed alive (`Ss`).
   - `backboardd[14]` printed `hakios: window server hooks installed`, `hakios: is_ready -> 1`, `hakios: ignore_update_p -> 0 (call 2, flags 0x411804801, update flags 0x80018)`, `hakios: no accelerated renderer; the software one will draw`, and executed `begin_update`/`render_update`/`finish_update` three times without crashing.
   - `MiniIOSurface` created surface `1` and surface `3` (`1125x2436 'BGRA'`, `4608` bytes/row, `11239424` bytes each). `MiniIOMobileFramebuffer` processed swaps `1 (#0)`, `2 (#1)`, `3 (#2)`, transitioning layer `0` from `0x0` to `0x1`.
   - Zero pixel diff (`B5`) is expected in Stage B because `SpringBoard` and UI scene clients are not yet present in `LaunchDaemons`, so `backboardd` composites an empty scene (`0` non-zero pixels vs cleared framebuffer).

4. **Missing services & kernel observations relevant to Stage C (`SpringBoard`):**
   - Lookups returning `No such process` in Stage B: `com.apple.oscard` (`backboardd[14]`), `com.apple.coremedia.virtualframebuffer.xpc` (`backboardd[14]`), `com.apple.lsd.mapdb` / `com.apple.lsd.xpc` (`runningboardd[11]`), `com.apple.frontboard.systemappservices` (`powerd[13]`), plus `configd`, `OSIntelligence`, `biome.access.user`, `locationd.registration`, `aggregated.addaily`, `commcenter`, `corewifi`, `wifi.manager`.
   - `MiniIOMobileFramebuffer` unimplemented selectors called cleanly without failing bring-up: `57, 15, 22, 29, 33, 27, 17, 84, 50, 68, 55`.
   - Memory at `[305.344s]`: `free 867, files 637, programs 20, wired 2570 (3 surfaces 32, ramfs 99), compressor 0 (holding 0) MB; available 1504`.
   - `hakios: input: /dev/hakios-touch: No such file or directory` (expected with `e1stouch=0`; node in `/dev` is `crw-rw-rw- /dev/redwood-touch`).
