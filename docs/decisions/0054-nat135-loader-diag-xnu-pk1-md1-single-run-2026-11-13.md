# Decision 0054: one NAT-135 run of loader-diag-xnu-pk1-md1 (read-only SuperSpeed prerequisite probe)

Date: 2026-11-13. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052. 0052 is the owner's standing
permission of 2026-11-13 for prepared native USB experiments; consent is recorded there and not asked again. No PMIC/ACPM
operation is used: the image keeps sc9's `e1spmic=0`. Nothing is written to any register by the probe.

## Image and boundary

Image loader-diag-xnu-pk1-md1, built by NAT-134. It is us1 (NAT-132's image) with only the USB engine replaced:
- RECOVERY artifacts/nat-134/package-001/loader-diag-xnu-pk1-md1/recovery.img,
  SHA-256 98f389890188685aca4913503be8e6e4125313016ea56ad81715d765579e8f69 (100663296 bytes).
- Image.payload SHA-256 adc3c40f3f9be07acc354fff4e4d6e6667578ef21ea242ba09bd66e2a43d06aa (26199536 bytes at offset 2048).
- Loader Image 20da048af0325f0df4a39a831c2cd2fe62370767299f7232fc7247cbfc6a0c95.
- Kernel, ADT, md0, the cmdline tokens and every bound are sc9's, as in us1. Cmdline tag `nat_attempt=NAT134-pk1`.
- The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot (session_nat135.py,
  derived by derive135.py --check).
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67, devices/recovery/backups/2026-11-10/recovery.img.
- Root image artifacts/nat-083/system-padded.apfs, 2475720704 bytes, SHA-256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6.

## Changes against us1 (the NAT-132 run)

The engine answers PEEK (0xC0/0x05, wIndex 0x5045) with one 32-bit read of an entry of a fixed, compiled-in table of 64 addresses
(NAT-131 section 5; docs/procedures/nat-134/peek134.py TABLE). It has no arbitrary-address form and no write form. The table covers:
- PMU 0x1286061c/0x620;
- DWC3 version and SS link registers;
- USBCON;
- CMU_HSI0 gates/QCH;
- USBDP PHY ctrl (plain reads, no CR port);
- TCA;
- CMU_PERIC2 GPIO gate/QCH;
- GPC7 CON/DAT.

The host companion deliver134.py reads the entries in table order on the delivery connection, before the first RX_BEGIN, and
journals each value with fsync before the next request.
- A group is skipped when its CMU gate reads "manually off" (MANUAL=1, CGVAL=0): USBDP gated on 0x17802058, TCA on 0x1780205c,
  GPIO on 0x11802054.
- The first failed or mismatched reply stops the probe, and then no delivery is attempted.
- Otherwise NAT-132's delivery follows unchanged (policy auto, 8 MiB writes).

## Risk specific to this run

A read of an unclocked or unpowered APB block can stall the bus or raise an SError. In that case the host's control transfer times out,
the probe stops at that entry (every earlier value is already journalled), and no delivery happens. The loader then either recovers
through its own fault handler or hangs until the 83 s hardware watchdog. The watchdog path is NAT-046/NAT-059's: SEC_UPLOAD, an
automatic restart, and possibly the owner's keys for Download Mode.

The reads are ordered from always-on to unknown, so that a stall costs only the later entries. The riskiest reads (USBDP, TCA,
GPIO) are gated.

## Time limit, stop mechanism, restore

The sc9 bounds are unchanged:
- companion wait 300 s;
- delivery cap 225 s;
- loader receive cap 240 s;
- kernel timed return 150 s, with watchdog feed;
- loader deadline 475 s, then return to Download Mode.

The probe adds 64 control transfers before the delivery, each bounded by the transport timeout of 5 s.

Restore:
1. Run docs/procedures/nat-012/restore_stock.py with the pyusb venv python, from the observed Download Mode bus/address.
   - If the phone came back to Android instead (watchdog path), use `session_nat135.py --restore` from Android, which is a dd with full readback.
2. Run check_android.py OUTPUT, then nat-013 restore_stock.py assess.
3. Require all of the following:
   - boot_completed=1;
   - SM-S921B/e1s/S921BXXS9BYH3;
   - full stock RECOVERY hash;
   - user-data directories present.
4. Close the native permission.

If neither Download Mode nor Android appears within ten minutes, the owner is asked for the key combination. This is one attempt,
with no retry without a new verifiable reason.

## Interpretation registered before the run

From peek.jsonl and delivery.json:
- VER_NUMBER ≥ 0x3132302a decides whether NAT-131 S19's LLUCTL/FORCE_GEN1 branch applies (U4).
- PMU 0x12860620 bit 0 and the USBDP/TCA values give the cold state at loader entry (U5).
- PHY_CONFIG0 power-stable bits give the indirect rail check (U6).
- The CMU_PERIC2 gate and GPC7 CON/DAT tell whether the orientation pin can be read and what it reads (U7).
- GUCTL bit NOEXTRDL gives U11.

Reading the outcome:
- A skipped group is reported as "clock manually off at loader entry", with its gate value. It is not a failure.
- A stalled entry is reported with its index, and that block is classed as not readable at loader entry.
- The delivery numbers are reported as a repeat of NAT-132's measurement. Their purpose is to show the probe did not disturb the
  receive path, not to make a new speed claim.
- No SuperSpeed claim follows from this run. It only reads.
