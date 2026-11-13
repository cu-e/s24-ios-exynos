# NAT-140: native run of loader-diag-xnu-scB-md1: the touch controller answers on the USI SPI9 map

Evidence kind: native-device. Outcome: **pass** (the registered question is answered). Decision 0056, one attempt, consumed
(artifacts/nat-140/native-attempt-loader-diag-xnu-scB-md1-used.json).

## What ran

The NAT-139 scB image ran:
- RECOVERY e9aa908e…e431 written to /dev/block/sda18, with a full readback before the single reboot;
- the NAT-139 kernel b5483e1d…1617, which has the USI SPI9 pad order CLK gpp9-0 / MOSI 1 / MISO 2 / CS 3 and a read-only MISO level
  check;
- `e1spmic=2`, `e1skeys=0`, `msgbuf=1048576`.

Session: `python3 -I docs/procedures/nat-139/session_nat140.py --out artifacts/nat-140/run-001 --image loader-diag-xnu-scB-md1 --execute`, rc 0.

## Results

| Item | Result |
| --- | --- |
| Root delivery | 2475720704 B in 66.586 s = 37.181 MB/s, sha256 4377e988…62f6 |
| Loader on USB | bus 7 +14.0 s after Android left; left at +486.0 s (loader deadline) |
| Download Mode | bus 8 dev 10 (`685d`) at +490.1 s |
| Kernel log | the `msgbuf` section holds the whole kernel log from 98.33 s (cache geometry, `kprintf initialized`). 149394 B, while the same 701 lsd CPU-monitor lines are present: **L-pmic-kept** |
| Power | **P2-both-rails-verified**. Chip IDs S2MPS27 0x01 / S2MPS28-4 0x31; before LDO9 0x34=0x30, LDO18 0x3d=0x18 (both off); `LDO18 0x3d 0x18 -> 0xd8 -> 0xd8`, `LDO9 0x34 0x30 -> 0xf0 -> 0xf0`; settled 100 ms (101.534–101.643 s) |
| Pins | `gpp9 con=0x1011 dat=0x8`; `spi9 map clk=gpp9-0 mosi=gpp9-1 miso=gpp9-2 cs=gpp9-3; miso cs-high=0 cs-low=0`: **MAP-ok** |
| Touch | **T2-chip-answers**. All three polls are identical: device ID `ok (53 54 40 36 03)`, hardware ID `36 40 03 00 93 00 92 64` |
| Keys | K0-disabled |
| Window / display / iOS | W-ok / D2-refreshing / F1-new-frame (73 recorded frames); panel P1-panel-has-pixels |
| Restore | nat-012 restore_stock (venv) rc 0, PIT 8192, 100663296 B acknowledged, 0x67/0 and 0x67/1; check_android pass (boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, stock RECOVERY 96620b8b…bf67, user-data dirs present); nat-013 assess **pass** |

## What this establishes

- The STM touch controller on this S24 is reachable by bit-banged SPI on gpp9 with CLK = pad 0 and MISO = pad 2. NAT-122/124/137's
  CLK 2 / MISO 0 map was the cause of their all-00/ff answers.
- The controller is powered by LDO18 1.8 V and LDO9 3.0 V, both set by the XNU kernel through ACPM with exact readbacks.
- The answers are stable across polls 50 ms apart. The device ID begins `53 54` ("ST").
- The hardware ID's first bytes `36 40` do **not** equal the pinned stm_reg.h `STM_TS_ID0/ID1` 0x48/0x36. The exact part identity
  is therefore not established from this pair.
- The 1 MiB kernel log ring keeps the full kernel log in this configuration.

## Not established

- No touch input: no IRQ, no event read, no sense-on, no coordinates reached iOS.
- No acceleration and no FPS.
- MISO reads 0 with CS low before any clock. That says nothing more about the chip.

## Next

1. Host: the event path on the verified pins, staged like NAT-121:
   - controller reset/sense-on as Samsung's stm_ts does;
   - polled `READ_ONE_EVENT` (0x87) with bounded reads and the IRQ line (gpa1-2) sampled, not attached;
   - coordinates posted to /dev/hakios-touch.
2. Then one native run, where the owner touches the screen during a stated window.
