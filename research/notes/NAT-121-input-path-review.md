# NAT-121 input path review (source-review, 2026-11-13; nothing ran on the phone for this note)

State after NAT-120: the owner saw the whole iOS home screen on the physical panel; touch is off (`e1stouch=0`).

## Three breaks between the STM touch controller and backboardd (each from the code that runs)

1. **Kernel touch driver faults.** `bsd/dev/e1s_touch.c` (STR-014 derive-001, compiled into the running kernel) maps PERIC1/ALIVE GPIO
   with `ml_io_map` into `gpp9`/`gpa1` but then passes the physical-address macros (`E1S_GPP9_DAT` = 0x110300e4 ...) to
   `gpio_rd/gpio_wr`: NAT-066's data abort at `_e1s_touch_init+0x174`, `far 0x110300e4`. Fix: every register macro relative to the mapped
   base (`gpp9 + 0xe4`, `gpa1 + 0x24`, EINT registers +0x704/+0x904/+0xa04 inside the same 4 KiB ALIVE page).
2. **Device name mismatch.** The kernel queue is `/dev/redwood-touch` (`redwood_input.c`, `devfs_make_node(..., "redwood-touch")`);
   the prebuilt `libhakios.dylib` in md0 (IOS-014; strings checked: only `/dev/hakios-touch`) opens `/dev/hakios-touch`. Record layout is
   identical (`{u64 time; u32 type, finger, x, y}`, 24 B; types 1-5 equal). Fix: a second devfs node `hakios-touch` on the same cdevsw.
   Without it the input thread in backboardd fails at open (its `hakios: input: /dev/hakios-touch: ...` line was not in the returned
   log tail of NAT-118/120: the head/tail window missed backboardd's start; not observed either way).
3. **Pins and power not verified.** The driver bit-bangs SPI9 on gpp9[0..3] (CS 3, CLK 2, MOSI 1, MISO 0), switching them from their USI
   function (2) to GPIO output; the pin order matches the DT's `spi9_bus = gpp9-2, gpp9-1, gpp9-0` / `spi9_cs = gpp9-3` only by the
   donor's assumption (RES-007: "GPIO pin ordering, bit timing and rails must be verified before output-driving"). The rails (LDO18 I/O,
   LDO9 analog via ACPM) may be off after S-Boot; the kernel log says `e1s-pmic: ACPM is not available`. The S9 donor needed a power cycle.

## Staged plan (each a separate image; nothing here authorizes or runs anything)

* NAT-121 (host): kernel patch set on `e1s_touch.c` (mapped-base fix; `e1stouch_steps=N` like the S9 donor: 1 = map + read pin
  config/EINT state only, 2 = pins to GPIO + read STM device id, 3 = event loop) and `redwood_input.c` (hakios-touch node). Needs
  KRN-044's rebuild for three objects (loader_return.o, e1s_touch.o, redwood_input.o): extend `rebuild.py` to several `--object/--patch`
  pairs. Host tests on the extracted functions against a fake register file.
* NAT-122 (native): `e1stouch=1 e1stouch_steps=2`: read-only state + device-id transfer; owner asked to touch the screen during the window.
  The verdict is the device-id line and `hakios: input: touch screen service ...`; touch acceptance needs the owner seeing a reaction
  (e.g. swipe between home-screen pages).
