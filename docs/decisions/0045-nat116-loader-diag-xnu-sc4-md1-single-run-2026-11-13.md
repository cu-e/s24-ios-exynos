# Decision 0045: Single-run `RECOVERY` authorization for NAT-116 (`loader-diag-xnu-sc4-md1`)

Date: 2026-11-13

## Owner authorization

The owner's message of 2026-11-13 (recorded as decision 0044) says: "Разрешаю NAT-116 и последующие подготовленные одиночные нативные
эксперименты без повторного согласования каждого образа, хеша или длительности" ("I authorize NAT-116 and later prepared single native
experiments without re-approval of each image, hash or duration"). Under decisions 0019 and 0044 this record authorizes **one**
single-attempt RECOVERY-only run of this image. It does not extend to other partitions or to a retry. Boundaries of decisions
0002/0019/0044 stand: Android, apps, settings, accounts and user data stay intact; no partition other than RECOVERY is written.

## Exact images

* `loader-diag-xnu-sc4-md1` RECOVERY (`artifacts/nat-115/package-001/loader-diag-xnu-sc4-md1/recovery.img`):
  100,663,296 B, SHA-256 `c0642059a4ba21e1205461bedc1b448952779b27f841b750211eb1b3c3d553f9` (re-hashed on the host 2026-11-13
  before this decision)
* Embedded `Image.payload`: 26,138,512 B, SHA-256 `85c2989b3ef7d5ba4774894c3bde0f2039ef61acfe4056a097890afc02582dc1`
* Kernel `kernel.no-storage` (KRN-044 rebuild + `docs/procedures/nat-115/kernel-combined.patch`):
  `cc952151c8d6007fa6ccd3c0e57d0320d85f329166fa23700930b8f2af680b18`
* Loader, md0 and delivered md1 root: NAT-113's, unchanged (md1 `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`)
* Stock RECOVERY restore target: `devices/recovery/backups/2026-11-10/recovery.img`,
  `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`

## Changes, time limit, stop conditions, restore

As in `docs/procedures/nat-115/decision-draft.md` (that draft is adopted unchanged as this decision's technical content):

* Changes vs NAT-113 (decision 0043): the kernel feeds the S5E9945 CL0 watchdog (`WTCLRINT=0`, `WTCNT=WTDAT`, the writes the loader
  already makes) every 10 s, only after reading back an enabled+reset `WTCON`, a plausible `WTDAT` and a counter that reloads, and only
  until `loader_return_after + 5 s`; read-only wait dump of SpringBoard/backboardd threads; window 150 s (`loader_return_after=150`,
  `rec_secs=150`); loader deadline 475 s.
* Fail-safe: if a feed check fails, the kernel feeds nothing and cuts the window to 63 s itself (NAT-113 window).
* Stop conditions (independent of kernel health): unfed watchdog ≤ 84 s after the last pet (SEC_UPLOAD/reset); feed stops at 155 s;
  NAT-044 hard loader deadline 475 s → Download Mode.
* Restore: Download Mode at the deadline → `docs/procedures/nat-012/restore_stock.py` (stock RECOVERY above) with readback →
  Android boot → `check_android.py` (RECOVERY SHA-256 via su, user-data directories) → `nat-013/restore_stock.py assess` = pass →
  native permit closed. If the phone does not reach Download Mode by itself, the owner is told the exact key action.

## Pass rule

Fixed before the run in `docs/procedures/nat-115/analyze116.py`: P-window / X-window, then exactly one of H1-frame / H2-cpu /
H3-wait / H4-display / X-none. No lock-screen claim unless a recorded frame differs from the logo and shows it.

## Scope

Only RECOVERY (`/dev/block/sda18`) is written, once, with full readback; then stock RECOVERY is restored with full readback. BOOT,
init_boot, vendor_boot, dtbo, vbmeta, super, USERDATA, EFS, GPT, keys and settings are not touched. One attempt; no automatic retry.
Driver: `docs/procedures/nat-115/session_nat115.py` (decision 0019 protocol).
