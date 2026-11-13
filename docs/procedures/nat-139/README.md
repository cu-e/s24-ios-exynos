# NAT-139: scB touch image (USI SPI9 pin map, MISO level check, 1 MiB kernel log ring)

Evidence kind: host-test. No device was used. Owner claude-opus-usb130-20261113. NAT-138 is the same work, registered by mistake with
a dependency on the inconclusive NAT-137; it is superseded by this task.

## Why (from NAT-137)

1. **Pin map.** NAT-122, NAT-124 and NAT-137 bit-banged SPI9 as CLK gpp9-2 / MOSI 1 / MISO 0 / CS 3. That order was read from
   `spi9_bus: samsung,pins = "gpp9-2", "gpp9-1", "gpp9-0"`, which only lists pins. The pinned DT names the signals of the same USI pads:
   - `s5e9945-pinctrl.dtsi`: uart1 `rxd_hiz` = pad 0, `tx_dat` = pad 1, `rts` = pad 2.
   - `s5e9945-usi.dtsi:1016`: USI09 hsi2c_18 `gpio_scl = <&gpp9 0>`, `gpio_sda = <&gpp9 1>`.
   - `s5e9945-usi.dtsi:1038`: hsi2c_19 `gpio_scl = <&gpp9 2>`, `gpio_sda = <&gpp9 3>`.
   - the e1s touch node: `cs-gpio = gpp9-3`.

   With the USI sharing RXD/SPICLK/SCL, TXD/SPIDO/SDA, RTSn/SPIDI, CTSn/CS, SPI9 is **CLK gpp9-0, MOSI gpp9-1, MISO gpp9-2,
   CS gpp9-3**. No pinned source prints the SPI names of the pads; this is an inference, and only a native run tests it.
2. **Log gap.** The 128 KiB msgbuf ring kept about 1 s before the touch lines (701 lsd CPU-monitor lines), so NAT-137 lost the
   PMIC readbacks.

## Changes

- `e1s_touch_combined.patch` = NAT-128's combined patch plus:
  - the USI pin map;
  - a read-only MISO level check. It reads MISO with CS high, drops CS for two half-bit delays with no clock edge, reads MISO again,
    raises CS, and prints `e1s-touch: spi9 map clk=gpp9-0 mosi=gpp9-1 miso=gpp9-2 cs=gpp9-3; miso cs-high=X cs-low=Y`.

  The three bounded ID polls are byte-for-byte NAT-128's: C0 22 / D1 …, then FB 20 …. There is no IRQ, no thread, no reset and no
  sense-on.
- Kernel `artifacts/nat-139/kernel-001` (KRN-044 rebuild.py):
  - main object loader_return.o (nat-121 patch);
  - extras e1s_touch (this patch), redwood_input (nat-121), e1s_acpm and e1s_pmic (nat-123).

  Results: 0 undefined symbols, 29 storage stubs, kernel.no-storage `b5483e1d…1617`. After normalizing the build path
  (nat-139 → nat-128), loader_return.o, redwood_input.o, e1s_acpm.o and e1s_pmic.o are byte-identical to NAT-128's. Only
  e1s_touch.o differs.
- Image `loader-diag-xnu-scB-md1` (`build.py`, derived from nat-129/build.py) adds `msgbuf=1048576`:
  - This is XNU's own boot-arg (subr_log.c `oslog_init_msgbuf`, `log_setsize`, MAX_MSG_BSIZE 1 MiB).
  - loader_return.c dumps `msgbufp->msg_size` bytes, so the dump follows the larger ring.
  - The console used 401427 bytes of the 1.5 MiB loader log in NAT-127, NAT-132 and NAT-137.

  `ufs_write=0` is dropped to stay within 255 bytes. Its only reader (redwood_ufs.c:1500) acts on `== 1` alone, so the token equals
  its absence. The kernel is the no-storage build, and `e1sufs=0` stays.
- The cmdline is 246 bytes. Against scA it removes `ufs_write=0` and the tag, and adds `msgbuf=1048576` and `nat_attempt=NAT139-scB`.
  The engine is NAT-130's (the same hashes as scA).

## Results

| Item | Value |
| --- | --- |
| RECOVERY | `artifacts/nat-139/package-001/loader-diag-xnu-scB-md1/recovery.img` e9aa908ea4c4edf1938e5722d296ce38fb711c6520607ba47c3713d9c6bce431 (100663296 B) |
| Image.payload | d26656ac2d0ae97fe5befdd8aa4fd2203e0a369d2a8b9307dbeb248cdf3d24a2 (26199088 B at 2048) |
| Loader Image | 55f6d3b92d89da3ee35de0f2b99ca2581eb038b98109ae7be568bb9f025d71c1 |
| Kernel | b5483e1de76d7c734aefa80ae27e75f0f8292c5221ddf6baa10e664f4e541617 |
| Session driver | `session_nat140.py` e7814e16e3ab09ef532dd553e8059ee747b80425c86c6fa9bbae6e39bdb25633 (`derive140.py --check`: counted substitutions from session_nat137.py) |

## Tests (host)

`python3 -B -I docs/procedures/nat-139/test_nat139.py`: 9 OK. `host/peer139.c` is a pin-level synthetic SPI mode-0 peer. It sees only
GPP9 CON/DAT traffic from the driver's real bit-banged transfer.

| Driver | Peer wiring | Result |
| --- | --- | --- |
| NAT-139 | USI (0/1/2/3) | reads the peer's synthetic IDs; frames = one clock-less select, then exactly the nine NAT-128 frames; no clock edge outside a frame; no IRQ or thread |
| NAT-128 | USI | all-00 IDs, CS toggles but the peer never sees a clock edge: the phone's T1 class |
| NAT-128 | old (2/1/0/3) | reads the IDs (control: the model does not fail by itself) |
| NAT-139 | old | all-00 IDs |

Two more wrong wirings (MISO on pad 1; CLK/CS swapped) were run by hand and also give all-00. Further checks:
- the patch's extra register writes are exactly the two CS writes of the level check;
- the kernel carries the new strings;
- the cmdline tokens are correct;
- `ufs_write` has one reader;
- `msgbuf` is bounded by XNU.

`python3 -B docs/procedures/nat-139/test_analyze140.py`: 4 OK. The analyzer gives the NAT-137 verdicts on NAT-137's real text, plus
MAP-missing and L-pmic-lost. On NAT-124's text it gives L-pmic-kept. On synthetic additions it gives MAP-ok and T2.

## Not established

This is not electrical evidence. Which wiring the phone has, whether the STM answers, and any input, acceleration or FPS remain
unmeasured. The next step is the single native run NAT-140 under its own per-image decision.
