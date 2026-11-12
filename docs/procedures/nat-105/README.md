# NAT-105: Native run of `loader-diag-xnu-hb2-md1` (decision `0039`) — B8 closed, Stage A base daemons verified

**Outcome:** `pass` (all acceptance criteria met; B8 log-window/settle gap closed with `gap_bytes=0`, `hole_bytes=0`; pre-registered analysers reached **`row H5 hb-ps-lists`** and **`row A1 base-daemons-alive`**).  
**Decision:** [0039-nat104-loader-diag-xnu-hb2-md1-single-run-2026-11-12.md](../../decisions/0039-nat104-loader-diag-xnu-hb2-md1-single-run-2026-11-12.md)  
**Image:** `loader-diag-xnu-hb2-md1` (`artifacts/nat-104/package-001/recovery.img`, SHA-256 `540b64a5736d444bdf8c0f09a6897c0469b3fb36332dce87f3ff626377bb1963`)  
**Target partition:** `RECOVERY` (`/dev/block/sda18`, `100,663,296` bytes) only; restored to pinned stock `recovery.img` (`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) and verified in Android.

## Key Results

1. **Delivery & USB collector (B8 closed):**
   - Full `2,475,720,704`-byte padded APFS root (`4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`) delivered to `md1` over USB in `196.925 s` (`12.572 MB/s`), `296` TRBs, `0` retries/errors/aborts/gaps/rejects/resets.
   - `glue62_impl.h` (`5s` settle wait + `NAT062_BURST=4096u` + `NAT062_TAIL_RETURN=262144u`) returned the **entire** `116,093`-byte dump of boot `000002` (`1,405` contiguous frames, `0` drops, `hole_bytes=0`, `gap_bytes=0`, `begin_inferred=false`).
   - Device exited cleanly into Download Mode (`04e8:685d` `SAMSUNG USB`) at `dt = 387.71 s` (`cls: cap-reset`).

2. **Pre-registered analysers (`analyze_nat104.py`):**
   - `--mode hb`: **`row 5 hb-ps-lists`** (`hb_marks=6`, `ps_lists=13`, `rounds_with_logd=[2, 3, 4, 5, 6]`, `gap=0`, `hole=0`).
   - `--mode stage-a`: **`row 1 base-daemons-alive`** (`all 7 self-starting jobs are in the last complete ps list; alive in total: 11`; `launchd_lines=311`, `last_list_rows=13`, `last_list_cut=false`).
   - Alive Apple processes at `hb` round 6 (`up=51s`, `PID 1..32`):
     `/sbin/launchd.darwin`, `/usr/libexec/runningboardd`, `/System/Library/CoreServices/powerd.bundle/powerd`, `/usr/libexec/containermanagerd`, `/usr/sbin/distnoted`, `/usr/libexec/usermanagerd`, `/usr/libexec/fseventsd`, `/usr/libexec/logd`, `/usr/sbin/notifyd`, `/usr/libexec/logd_helper`, `/usr/sbin/cfprefsd` (plus `/redwood/bin/hb` and `/bin/ps`).
   - `com.apple.datamigrator` also spawned on-demand via Mach IPC (`pid 24`, `00:04:15.355` .. `00:04:26.754`) and exited `0` cleanly.

3. **Kernel & userland observations relevant to Stage B (`backboardd` / graphics):**
   - `e1s-log: image-owned console ring, 1023 KiB`; `35 checks, 0 failed`; `memory: free 998, files 552, programs 10, wired 2533 ... MB; available 1550`.
   - `MiniIOMobileFramebuffer: display 1125x2436 on a panel of 1080x2340 (4320 bytes per row)`; `e1s-display: framebuffer 1080x2340 depth 32 stride 4320 phys 0xfa200000`.
   - Missing services reported as expected lookups in Stage A's minimal plist set: `com.apple.iohideventsystem`, `com.apple.SystemConfiguration.configd`, `com.apple.coremedia.systemcontroller.xpc`, `com.apple.OSIntelligence`, `com.apple.lsd.mapdb`, `com.apple.lsd.xpc`, `com.apple.biome.access.user`, `com.apple.frontboard.systemappservices`.
   - Note on `--mode chain`: reported `nat087.restore.row = 9` because `manifest_original.errors = 1` (`start-failed` USB poll timeout before Download Mode entry at `dt 387.71s`), even though `boot 000002` had `drops=0`, `faults=0`, and complete contiguous delivery/dump.
