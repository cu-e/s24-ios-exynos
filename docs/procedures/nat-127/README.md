# NAT-127: sc9 restores visible iOS without PMIC access

Owner claude-opus-nat116-20261113. Evidence kind native-device. One run under
decision 0051, reboot requested 2026-11-13T15:54:20.569887Z.

## Established

- Full candidate RECOVERY readback matched pinned sc9 image before reboot.
- Root delivery: 2475720704 bytes / 153.335 seconds, no retries or RX errors.
- Native log explicitly e1s-pmic: disabled (e1spmic=0). No ACPM probe/PMIC
  transaction path entered. STM ID is printed after the transfer and is five
  zero bytes; controller unresponsive guard prevents IRQ/event thread startup.
- launchd activity is back (2392 received lines mentioning launchd); backboardd
  pid 16 opened hakios-touch at kernel 201.241680 s. No SpringBoard userabort.
- Recording holds 73 frames in the ring, in contrast to sc8's zero; this is a
  retained ring count, NOT the total number of frames rendered in the run.
- Pre-registered verdict W-ok / D2-refreshing / F1-new-frame / T1-no-response /
  P0-no-verified-rails, physical input not established. Memory evidence and
  physical visibility are separate.
- Owner observation after stock restore, verbatim: "Видел домашний экран iOS
  целиком". English translation: "Saw the entire iOS home screen". This is
  physical display evidence, not just a frame in RAM; no photo was supplied.
- Framebuffer log reports about 6-7 frames/s in the final intervals, around
  54 ms driver time per frame. DECON refresh is not application FPS. No Xclipse
  acceleration or sustained 60 FPS established.

## Restore

Download Mode observed at 2026-11-13T16:02:38.268853Z, bus 5/address 59.
nat-012 stock upload/reboot succeeded. check_android at 16:03:49.021926Z:
SM-S921B/e1s/BYH3, boot_completed=1, existing user-data directories present,
full RECOVERY hash match. NAT-013 assess pass. Native permit closed. These are
minimal checks, not exhaustive checks of all settings/account/application content.

## Interpretation and next step

Removing both sc8's PMIC path and its unresponsive-STM IRQ admission restored
userland and physical home-screen visibility. It does not distinguish IRQ
starvation from recurring ACPM reads or another changed scheduling path.
Do not claim the cause proved. Input still absent, no acceleration/FPS goal done.

Prepare on host a polling-only controller diagnostic with the two authorized
rail values, no recurring PMIC key reader, bounded attempt count, and raw
hardware-ID read before optional scan activation. No scan/firmware/reset write
should be added speculatively. The specific decision 0049 single run was
consumed; request fresh PMIC-write permission on the prepared plan before any
such native run. Independent source review and builds may continue.
