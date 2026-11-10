# S5E9945 watchdog candidate, 2026-11-10

Evidence category: source-review and host-test. No MMIO or device execution.

Primary sources are `s24-linux` 417484173abc2c4fa93e738ea82ad9f2e84911b1 and
`s24-bsp-reference` f85e53cfa5497ead5d78821efbac84e51f37a4e1 (same driver bytes).
File references below apply to both pins; preserve their GPL-2.0-or-later notices.

- `drivers/watchdog/s3c2410_wdt.h:16-40`: WTCON 0, WTDAT 4, WTCNT 8,
  WTCLRINT 12, WTMINCNT 16; reset bit 0, interrupt bit 2, enable bit 5,
  divider bits 3:4, prescaler bits 8:15, DBGACK bit 16, window bit 20.
- Header lines 54-58 and `s3c2410_wdt.c:204-222`: v1 routes through PMU
  NONCPU_INT_EN 0x1244 bit 2, v2 through 0x1844 bit 3; reset status 0x10
  bits 24/25. The obsolete disable register is removed (comment at 178);
  there is no S5E9945 cnt_en callback. Do not write old 0x408/0x40c offsets.
- `s3c2410_wdt.c:297-331`: setting route bit enables reset, clearing masks it.
  `:535-568` supplies stop, window minimum=count*2, data/count, enable ordering;
  `:582-635` derives timeout from rate/128 and prescaler+1.
- `arch/arm64/boot/dts/exynos/s5e9945.dts:623-647` assigns timers at
  0x10040000 / 0x10050000, OSCCLK2 plus gate clocks;
  `drivers/clk/samsung/clk-s5e9945.c:44` defines OSCCLK2 as 25,600,000 Hz.
- Runtime NAT-005 DTB (SHA-256
  95fa811abca3f5f8889705add485f94c4490c57a853bded10539d4631bef46c3)
  resolves both syscon phandles to `/system-controller@12860000`, size 0x10000.
  Sanitized resolved facts: `docs/procedures/nat-007/runtime.json`.
- `drivers/samsung/sec_reboot.c:96,325-326,428-430,463-478` writes recovery
  reason 0x12345604, and normal/unknown reason 0x12345600, through panic-inform.
  The runtime sec-reboot node resolves the same PMU and offset 0xbc.

The owned module takes caller-supplied volatile MMIO pointers and an established
clock rate. It does not enable clock gates or claim that S-Boot leaves them on.
At 25.6 MHz, requested 30 s uses prescaler 91, count 65218, approximately
30.00028 s. Overflow/invalid requests reject before writes. Host register
fixtures cover both variants, unrelated PMU bits, query/pet/disarm and rejection.
ASan/UBSan exercises these fixtures; ARM compilation checks freestanding use.

Inference: an enabled routed timer should reset the SoC. Only a separately
authorized native test can establish clock survival, secure PMU access, expiry,
S-Boot's next target and absence of a reset loop. No S-Boot source is supplied;
the kernel's reason writes do not prove S-Boot consumes or clears that marker.
Reset is not proof of restoration to Android. NAT-004 must qualify that path.
