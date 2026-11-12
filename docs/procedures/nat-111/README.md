# NAT-111 — Native Device Measurement of `loader-diag-xnu-sc2-md1` (Stage C2)

Single authorized native execution of `loader-diag-xnu-sc2-md1` (`NAT-110` build under decision `0042`) on `SM-S921B` (`e1s`, `S921BXXS9BYH3`).

**Target partition:** `RECOVERY` (`/dev/block/sda18`, `100,663,296` bytes) only; restored to pinned stock `recovery.img` (`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) and verified in Android (`SM-S921B`, `e1s`, `S921BXXS9BYH3`, `docs/procedures/nat-013/restore_stock.py assess` -> `pass`).

## Host Load Note

- At `--execute` launch, `/proc/loadavg` 1-min load was `7.39` (`> 6.0` literal string in `acceptance[0]`) from pre-existing desktop processes (`yoitsu-launcher`/`java`/`firefox`), while `vmstat 1 3` showed `93-94%` idle CPU (`1/4368` runnable on `12` cores, `b=0`, `wa=0%`).
- Delivery and USB EP0 collection completed cleanly with zero drops, zero faults, zero retries, `hole_bytes=0`, `gap_bytes=0`, and `closed=true`; therefore the single measurement was accepted without repeating a native run.

## Observed Outcomes (`analyze_nat110.py`)

| Check | Result | Key Facts |
|---|---|---|
| Delivery | `delivered` | `2,475,720,704` B (`4377e988...`) in `152.831 s` (`16.199 MB/s`), `296` TRBs, `0` retries/errors/gaps/rejects/resets |
| Stage C | `C6 fb-swaps-no-diff` | `SpringBoard[13]` spawned `195.803122 s`, alive in round 6 (`39` processes total); `backboardd[16]` spawned `195.214529 s`; `3` swap lines (`swap 1` surface `1` at `234.930833 s`, `layers 0x0->0x1` at `235.443590 s`, `swap 2` surface `3` at `235.459277 s`); `fb_stats=[]`; `fb_pixel_diffs=[]` |
| Quiet + Prune Check | `etc_quiet_active=false` | Empty `/redwood/etc/quiet` (`0` bytes) did not silence `launchd` (`668` console lines); pruning `27` plists + `com.nat085.ps.plist` reduced live processes in final round from `71` (`NAT-109`) to `39` and log size from `455,754` B to `314,132` B (`3,047` lines) |
| CPU-Monitor Contention | `448` denials | `lsd[25]` reached `0:13.26` CPU TIME in round 5 (`up=45 s`, state `Rs` in round 6) and logged `448` CPU-monitor escape denials (`241` in `NAT-109`), while `SpringBoard[13]` accumulated `0:05.24` -> `0:05.51` CPU TIME between rounds 3 and 5 with no further swaps after `235.459277 s` |
| Stage B | `B5 fb-swaps-no-diff` | Matches Stage C swap telemetry with `backboardd[16]` alive in round 6 |
| Heartbeat (`hb`) | `H5 hb-ps-lists` | `6` `hb` marks (`up=0..55 s`), `6` `ps` exits `status=0` (`105..2026 ms`), `39` processes in round 6 (`O` format) |
| Stage A | `A2 some-daemons-alive` | `early_boot_complete_kernel_s=195.111424`; `28` alive Apple jobs (`Stage A` string match misses `SpringBoard` even though round 6 `O`-format `ps` lists `/System/Library/CoreServices/SpringBoard.app/SpringBoard` at PID `13`) |
| Chain | `chain_row 7` | `HOLD stage=0x51 code=0x223e` (`dt=388.88 s`, `download` `04e8:685d`, `cap-reset`), `why=2` dump `314,132` B (`3,273` records, `gap=0`, `hole=0`, `closed=true`) |
