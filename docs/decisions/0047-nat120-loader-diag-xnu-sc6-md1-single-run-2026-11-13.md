# Decision 0047: Single-run `RECOVERY` authorization for NAT-120 (`loader-diag-xnu-sc6-md1`, built by NAT-119)

Date: 2026-11-13

## Owner authorization

Decision 0044 records the owner's standing consent of 2026-11-13 ("Разрешаю NAT-116 и последующие подготовленные одиночные нативные
эксперименты без повторного согласования каждого образа, хеша или длительности"), including bounded experiments with the display.
Under decision 0019 and decision 0044 this record authorizes **one** single-attempt RECOVERY-only run of this image; the owner was not
asked again. Only RECOVERY (`/dev/block/sda18`) is written; Android, apps, settings, accounts and user data stay intact.

## Reason (new verifiable cause)

Owner observation after NAT-118: the iPhone's bottom bar was visible on the physical panel, icons and background were not. Analysis
(`research/notes/NAT-118-owner-panel-observation.md`): after the kernel's return the loader paints marker bands over panel rows
0-2063 (only the bottom ~277 rows keep iOS), and while the kernel runs nothing triggers DECON0, which is in MIPI command mode.

## Exact images

* RECOVERY `artifacts/nat-119/package-001/loader-diag-xnu-sc6-md1/recovery.img`: 100,663,296 B,
  SHA-256 `e430d54e302e4a4e3251022fe65ae026429ebf90e22c4c6704d2e1ead170b6ac`
* Embedded `Image.payload`: 26,141,568 B, SHA-256 `4175a7ff5aacdf48e561dd292e2ec685c5bc4e553fd1cc724a380c1b140620d1`
* Loader `Image` `b73cf7a7a40c639b95e3426e868c9df84d5eef6d91dc01f866ea1e21f68f09f1`
* Kernel `kernel.no-storage` `ecea87511448ba3309896c832faefbe1be103e1b14449e08a795cf4e595c5873` (KRN-044 rebuild of
  `docs/procedures/nat-119/kernel-combined.patch`)
* ADT `44bbd1d0...` (NAT-117), md0/md1 unchanged, stock RECOVERY target `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`

## Changes relative to NAT-118 (decision 0046) and risk

1. Kernel writes DECON0 (`0x19100000`) `TRIG_CON` (0x30) and `SHD_REG_UP_REQ` (0x50) with the loader's HW-form kick sequence, which
   the loader has executed on this phone in every run since NAT-022 (decision 0010) without a fault; at most 64 kicks (start of the
   window + every 10 s), only if `GLOBAL_CON` reads enabled + command mode. Display registers only; no power, clock or PMIC register.
   Worst case: the panel shows a wrong/stale frame or stays dark; the run's bounds are unaffected.
2. The loader stops drawing its marker bands after the kernel's return (no hardware change; the USB log path is unchanged).
3. Command line + `e1s_decon_hw=1` (249 B < 256 B).

Time limit, watchdog arithmetic and stop conditions are NAT-118's (measured): 150 s kernel window with the kernel feeding the
S5E9945 watchdog (cut to 63 s by the kernel itself if the feed is not proven), hard loader deadline 475 s → Download Mode.

## Restore

As decision 0046: Download Mode → `nat-012/restore_stock.py` with readback → Android → `check_android.py` → `assess` pass → permit
closed. If no Download Mode within ~10 minutes: the owner holds Volume Down + Power until the screen goes off, then Volume Down +
Volume Up with the cable connected.

## Pass rule (`docs/procedures/nat-119/analyze120.py`, tested before the run)

`X-window` / `D0-no-kick` / `D1-kick-frozen` / `D2-refreshing` (frame-counter rate between kicks), with the iOS verdict of analyze118
alongside. The owner's observation is recorded verbatim and separately; "visible iOS on the panel" is claimed only from the owner's
observation or a photo.
