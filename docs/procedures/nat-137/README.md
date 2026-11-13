# NAT-137: native run of loader-diag-xnu-scA-md1 (touch rails + bounded polling touch ID)

Evidence kind: native-device. Outcome: **inconclusive**. Decision 0055, one attempt, consumed
(artifacts/nat-137/native-attempt-loader-diag-xnu-scA-md1-used.json).

## What ran

The NAT-129 scA image ran, with RECOVERY a4809fe2…2826 written to /dev/block/sda18 and read back in full before the single reboot. It is
the NAT-128 polling-only touch kernel:
- `e1spmic=2` (LDO18 0x3d := 0xd8, LDO9 0x34 := 0xf0, exact readbacks);
- `e1skeys=0`;
- the NAT-130 USB engine.

Session: `python3 -I docs/procedures/nat-129/session_nat137.py --out artifacts/nat-137/run-001 --image loader-diag-xnu-scA-md1 --execute`, rc 0.

## Results

| Item | Result |
| --- | --- |
| Root delivery | 2475720704 B in 66.666 s = **37.136 MB/s**, sha256 4377e988…62f6 (repeat of NAT-132's 37.185) |
| Loader on USB | bus 7 (high-speed) +17.8 s after Android left; left at +490 s (loader deadline) |
| Download Mode | bus 8 dev 8 (`685d`) at +494 s |
| Window / display / iOS | W-ok / D2-refreshing / F1-new-frame (73 recorded frames) |
| Keys | K0-disabled: `e1s-keys: disabled (e1skeys=0)` at 105.875 s |
| Touch | **T1-no-response**: poll 1 device id 00×5 and hardware id 00×8; polls 2–3 ff×5 and ff×8; `poll-only diagnostic complete` |
| Power | P0 by the rule, but see "log gap". The rails were neither verified nor refuted in this run. |
| Restore | nat-012 restore_stock (venv) rc 0, the four 0x65/0x66/0x67 stages; check_android: boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, stock RECOVERY 96620b8b…bf67, user-data dirs present; nat-013 assess **pass** |

## Log gap (why power is not P1/P2)

The `--- kernel message buffer ---` section is exactly 131072 bytes, the size of XNU's default msgbuf ring. Its first line is cut
mid-line: it begins `d-touch: e1s platform…`, the end of `redwood-touch: …`. In NAT-127 the `e1s-pmic` line comes directly before
that line, so the PMIC rail lines were overwritten in the ring.

The flood is 701 copies of `process lsd[25] denied attempt to escape CPU monitor (missing required entitlement)`
(osfmk/kern/task_policy.c:2867). It is the same count in NAT-127, NAT-132 and NAT-137. In all three runs the ring retains only about
1 s before the e1s driver lines. P0 here therefore says nothing about whether the rails were enabled.

The same PMIC code (NAT-123 `e1spmic=2`) did verify both rails on this phone in NAT-124:
- `LDO18 0x3d 0x18 -> 0xd8 -> 0xd8`
- `LDO9 0x34 0x30 -> 0xf0 -> 0xf0`

The STM still answered 00 there.

The console section is 401427 bytes and never wrapped the 1.5 MiB loader log. XNU's own `msgbuf=` boot-arg (bsd/kern/subr_log.c:859,
maximum 1 MiB) followed by loader_return.c's dump of `msgbufp->msg_size` would therefore keep the whole kernel log.

## Finding: the bit-banged SPI pin map is probably swapped

e1s_touch.c bit-bangs SPI9 as MISO = gpp9-0, MOSI = gpp9-1, CLK = gpp9-2, CS = gpp9-3. That order was read from the listing
`spi9_bus: samsung,pins = "gpp9-2", "gpp9-1", "gpp9-0"` (research/notes/NAT-121-input-path-review.md:16 already called it an
assumption). A pin list carries no signal order.

The pinned DT (references/s24-linux) names the signals on the same USI pads:
- s5e9945-pinctrl.dtsi uart1: `uart1_bus_rxd_hiz` = gpq0-0, `uart1_bus_tx_dat` = gpq0-1, `uart1_bus_rts` = gpq0-2.
- s5e9945-usi.dtsi:1016: USI09 hsi2c_18 `gpio_scl = <&gpp9 0>`, `gpio_sda = <&gpp9 1>`.
- s5e9945-usi.dtsi:1038: hsi2c_19 `gpio_scl = <&gpp9 2>`, `gpio_sda = <&gpp9 3>`.
- e1s dts: `cs-gpio = gpp9-3`.

Pad 0 is the clock pad (RXD/SPICLK/SCL), pad 1 the data-out pad (TXD/SPIDO/SDA) and pad 2 RTSn/SPIDI. With that USI sharing the map is
CLK = gpp9-0, MOSI = gpp9-1, MISO = gpp9-2, CS = gpp9-3. The SPI names of the pads are not printed in a pinned source; they are
inferred from the UART and I2C names.

Under that map the driver samples the chip's clock input, an undriven pin with pull NONE, as "MISO". It drives the chip's MISO as a
clock. That reproduces all-00 then all-ff whatever the rails do.

## Not established

No touch input, no IRQ, no event, no acceleration and no FPS. T1 says only that the sampled pin never carried an ID.

## Next (new verifiable reason, host first)

NAT-138 (host):
- a kernel with the USI pin map;
- a pin-level MISO diagnostic: idle level with CS high, then with CS low before clocking;
- `msgbuf=1048576` so the rail readbacks survive. `ufs_write=0` is dropped for space; its only reader enables writes on `== 1`, the
  kernel is the no-storage build and `e1sufs=0` stays.

Then a single native run under its own decision.
