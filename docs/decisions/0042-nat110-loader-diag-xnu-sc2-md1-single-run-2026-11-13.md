# Decision 0042: Single-run `RECOVERY` authorization for `NAT-110` (`loader-diag-xnu-sc2-md1`)

Date: 2026-11-13

## Standing authority and scope

Under decision 0019 (`docs/decisions/0019-nat049-048-051-052-canary-runs-and-self-approval-2026-11-10.md`), this record authorizes **one** single-attempt `RECOVERY`-only run on `SM-S921B` (`e1s`, `S921BXXS9BYH3`) using `loader-diag-xnu-sc2-md1` from `NAT-110`, followed unconditionally by full-hash restoration and verification of the pinned stock `RECOVERY` image before closing `native`.

All other partitions (`BOOT`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `USERDATA`, `super`, `EFS`), GPT tables, keys, settings, accounts, and Android user data remain untouched.

## Exact pinned image and hashes

* Image name: `loader-diag-xnu-sc2-md1`
* Packaged `RECOVERY` (`artifacts/nat-110/package-001/loader-diag-xnu-sc2-md1/recovery.img`):
  * Bytes: `100663296`
  * SHA-256: `3e0c594060a58e4045ef6dee417931d8e79ed8fb139de38b5cb18d1294788258`
* Embedded `Image.payload` (at byte offset `2048`):
  * Bytes: `26134288`
  * SHA-256: `31a9f150ba75d967fa074a320998ba6b88986c952ade1ff002ac718bf44a02c6`
* `Image`:
  * Bytes: `385024`
  * SHA-256: `954aef2c80da0d326cb63574422ac5be2420effcd892cd7ae6f468f95f077c88`
* Stage C2 + heartbeat `md0` small root (`artifacts/nat-110/pid1-sc2-hb/root.apfs`):
  * Bytes: `4194304` (`396` files, `377` LaunchDaemons)
  * SHA-256: `6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c`
* USB-delivered padded iOS root (`artifacts/nat-083/system-padded.apfs`):
  * Bytes: `2475720704`
  * SHA-256: `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`
* Pinned stock `RECOVERY` restore target (`devices/recovery/backups/2026-11-10/recovery.img`):
  * Bytes: `100663296`
  * SHA-256: `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`

## Delta from `NAT-108` / `NAT-109`

1. Adds empty `etc/quiet` (`0644`) to `md0`, silencing `launchd`'s synchronous console stderr (`2,086` lines / `279,524 B` in `NAT-109`) so the return KL dump finishes comfortably inside `--deadline-s 365` and CPU 0 is not stalled rendering console text.
2. Removes `com.nat085.ps.plist` (duplicate heartbeat alongside `/redwood/bin/hb`) and `27` non-UI wireless/cloud/telemetry/sharing/speech/widget plists from `LaunchDaemons/` so `SpringBoard` and `backboardd` receive CPU within the single-CPU (`cpus=1`) window.
3. Keeps `fb_diff=1`, sets `loader_return_after=63` (exact `83 s WDT - 20 s` safety bound from `NAT-079`, keeping kernel cmdline `246 B < 256 B`), and raises `--deadline-s` to `365` (`>= rx_cap 240 + return_after 63 + work_margin 60 = 363`, inside the `600 s` watcher/collector window).

## Mandatory execution and recovery protocol

1. Only after `NAT-110` closes (`state=done`) and a dedicated `native` child task (`NAT-111`) opens with `state/lab.json` `native=true` citing this decision file:
   * Write `loader-diag-xnu-sc2-md1/recovery.img` once to `/dev/block/sda18` via `session_nat110.py --execute` with full SHA-256 readback, active USB watcher, EP0 collector, and bulk-OUT delivery companion.
2. Unconditionally restore stock `RECOVERY` (`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) via `session_nat110.py --restore` (`--reboot-recovery` never repeated) with full SHA-256 readback, verify booted Android (`sys.boot_completed=1`) and `restore_stock.py assess`, then close `native=false` via `tools/lab.py permission native false`.
