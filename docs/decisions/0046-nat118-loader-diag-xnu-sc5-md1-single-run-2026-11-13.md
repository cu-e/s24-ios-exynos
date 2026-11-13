# Decision 0046: Single-run `RECOVERY` authorization for NAT-118 (`loader-diag-xnu-sc5-md1`, built by NAT-117)

Date: 2026-11-13

## Owner authorization

Decision 0044 records the owner's standing consent of 2026-11-13: "Разрешаю NAT-116 и последующие подготовленные одиночные нативные
эксперименты без повторного согласования каждого образа, хеша или длительности". Under decision 0019 and decision 0044 this record authorizes
**one** single-attempt RECOVERY-only run of this image; the owner was not asked again. No retry; no other partition. Boundaries of
0002/0019/0044 stand: Android, apps, settings, accounts and user data stay intact; only RECOVERY (`/dev/block/sda18`) is written.

## Reason for this run (new verifiable cause, not a repeat)

NAT-116 (decision 0045) showed SpringBoard aborting 9 times with `Failed to load bounding path bitmap data from the asset manager for
asset name: BoundingPathBitmap-1125x2436-375x812-3.00x`, and the image's ADT has no `/product` node (from which MobileGestalt takes
the artwork traits). This image adds the real D22AP `/product` node. The hypothesis under test: the missing node is the cause.

## Exact images

* `loader-diag-xnu-sc5-md1` RECOVERY (`artifacts/nat-117/package-001/loader-diag-xnu-sc5-md1/recovery.img`):
  100,663,296 B, SHA-256 `9696818ff9ccc3f38276a7196a8a934085da8860758e8ef25788a0bc581b0536`
* Embedded `Image.payload`: 26,141,200 B, SHA-256 `81b33e6de389b122e0e252d64d0cb221c3f6c5d3c4270a88472cc2cb298fd5c7`
* Loader `Image`: `a81d3add2945be8092a7a231289bcd36142d62eba5d6b2c1b03af6eeae56d742` (NAT-115's code; 13 differing bytes = five
  mov/movk immediates of the embedded payload hash/size constants, checked with capstone)
* Kernel: NAT-115's `kernel.no-storage` `cc952151c8d6007fa6ccd3c0e57d0320d85f329166fa23700930b8f2af680b18`, unchanged
* ADT: `44bbd1d06693d706dfede4ea1e3d85953cb7eb3151854302c2a41fcdceadf79e` (NAT-085's ADT + D22AP `/product`, 61 properties,
  artwork-device-subtype 2436, scale 3, idiom phone, gamut sRGB)
* md0 / delivered md1: unchanged (md1 `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`)
* Stock RECOVERY restore target: `devices/recovery/backups/2026-11-10/recovery.img`,
  `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`

## Changes relative to NAT-116 (decision 0045) and risk

1. ADT gains a `/product` node (device-tree data only, read by IOKit/MobileGestalt in user space; no hardware access).
2. `wait_dump=1` removed from the command line (it panicked the kernel at the return in NAT-116); the code is inert without it.
3. Payload inner diff vs NAT-115 is only: the ADT (`adt_size` 0x3718 -> 0x4198), the command line (`nat_attempt=NAT117-sc5`,
   `wait_dump=1` gone, 234 B < 256 B) and the trailing bytes.

No new hardware register is touched. Time limit, watchdog arithmetic and stop conditions are NAT-116's, measured there:
150 s kernel window with the kernel feeding the S5E9945 watchdog (the kernel cuts itself to 63 s if the feed is not proven); unfed
watchdog resets ≤ 84 s after the last feed; feed stops at window + 5 s; NAT-044 hard loader deadline 475 s → Download Mode (observed
in NAT-116 at +496 s after the reboot command).

## Restore

Download Mode at the deadline → `docs/procedures/nat-012/restore_stock.py` with readback → Android boot → `check_android.py`
(RECOVERY SHA-256 via su, user-data directories) → `nat-013/restore_stock.py assess` = pass → native permit closed. If the phone does
not reach Download Mode by itself within ~10 minutes, the owner is told the exact key action (hold Volume Down + Power until the
screen goes off, then Volume Down + Volume Up with the USB cable connected).

## Pass rule (fixed before the run, `docs/procedures/nat-117/analyze118.py`, tested on NAT-116 and NAT-113)

Window `W-ok` (timed return, no panic before it, pixel report complete) or `X-window`; then the first of `F1-new-frame`,
`A1-same-abort` (the hypothesis is refuted), `A2-other-abort` (the next blocker is named), `S1-alive-no-frame`. No lock-screen claim
unless a recorded frame differs from the logo and the thumbnail shows it.

## Commands

    python3 tools/lab.py project permit --scope native --value true --decision docs/decisions/0046-nat118-loader-diag-xnu-sc5-md1-single-run-2026-11-13.md --owner OWNER
    python3 docs/procedures/nat-117/session_nat117.py --out artifacts/nat-118/preflight-001 --image loader-diag-xnu-sc5-md1
    python3 docs/procedures/nat-117/session_nat117.py --out artifacts/nat-118/run-001 --image loader-diag-xnu-sc5-md1 --execute
    (restore and analysis as in docs/procedures/nat-116/README.md, with analyze118.py)
