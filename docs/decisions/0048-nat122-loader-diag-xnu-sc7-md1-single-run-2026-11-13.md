# Decision 0048: Single-run `RECOVERY` authorization for NAT-122 (`loader-diag-xnu-sc7-md1`, built by NAT-121)

Date: 2026-11-13

## Owner authorization

Under decision 0019 and decision 0044 (owner's standing consent of 2026-11-13 to prepared single native experiments without
re-approval of each image, hash or duration) this record authorizes **one** single-attempt RECOVERY-only run of this image. Only
RECOVERY (`/dev/block/sda18`) is written; Android, apps, settings, accounts and user data stay intact.

## Reason

NAT-120 showed the whole iOS home screen on the panel (owner). Next goal stage: input. NAT-066 panicked in the e1s touch driver
(physical addresses used as virtual); NAT-121 fixed it and staged it. This run answers: does the fixed driver run without a fault, what
GPIO state S-Boot leaves on gpp9/gpa1, and does the STM controller answer a device-id read over bit-banged SPI9.

## Exact images

* RECOVERY `artifacts/nat-121/package-001/loader-diag-xnu-sc7-md1/recovery.img`, 100,663,296 B,
  SHA-256 `f62c3c9ec38d0557492235cc00520c3e035f3b10ad883e9b7652dda376c2301b`
* `Image.payload` SHA-256 `ec1e8c728eb68dcc02d01f3069010ff927b4812343a18ce6d8caacb8ee618475`
* Kernel `kernel.no-storage` `7ccab9b6c1359298d0d53fac2bd30533294baa272f78f7beeed2f7761092ad85` (KRN-044 three-object rebuild:
  loader_return.o = NAT-119's patch; e1s_touch.o; redwood_input.o)
* ADT, loader rules, md0/md1: NAT-119's. Stock RECOVERY target `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`

## Changes relative to NAT-120 (decision 0047) and risk

1. `e1stouch_steps=2` (and `e1stouch=0` removed): step 1 reads PERIC1 gpp9 and ALIVE gpa1/EINT registers (read only). Step 2 sets
   gpp9[3] (CS) high, then gpp9[0..3] to GPIO with the directions of the DT's SPI9 function (CLK gpp9-2, MOSI gpp9-1, CS gpp9-3 out;
   MISO gpp9-0 in), no pulls, and runs two SPI transactions (Samsung STM read sequence `C0 22`, `D1 00 00` + 5 bytes; `C0 23`, ... 11
   bytes): register reads of the controller; no firmware or configuration write, no flash command. No IRQ, no event thread, no ALIVE write.
   Host tests (fake register file): step 1 writes nothing, step 2 writes only the PERIC1 page, no access outside the two mapped pages.
   Risk: if the DT pin order were wrong, a pin the controller drives could be driven for a few milliseconds (1.8 V I/O, low current);
   the pins return to their Android configuration at the next Android boot. Touch rails are not touched (no ACPM).
2. `/dev/hakios-touch` devfs node on the existing queue + log lines; no hardware.

Time limit, watchdog and stop conditions are NAT-120's (150 s kernel window, kernel watchdog feed, loader deadline 475 s → Download Mode).

## Restore

As decision 0047 (Download Mode → `nat-012/restore_stock.py` → Android → `check_android.py` → `assess` → permit closed; owner key combo
if no Download Mode within ~10 minutes).

## Pass rule (`docs/procedures/nat-121/analyze122.py`, tested before the run)

Window / display / iOS verdicts as NAT-120, plus touch: `T0-fault`, `T0-no-step1`, `T1-no-response`, `T2-chip-answers`. Working touch is
not claimed from this run.
