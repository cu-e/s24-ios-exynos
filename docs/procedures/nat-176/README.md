# NAT-176: scS, a read-only display-layer snapshot before DPP hardware scaling (host)

## Why

NAT-175 (F30) found that under animation every frame spends 8.77 ms on the CPU scaling the iOS surface from 1125×2436 to
1080×2340. The scaling runs on the same single core that renders. The size iOS sees cannot change: with any other size MobileGestalt
reports an unknown screen class. The display hardware can scale instead (NAT-162: DPP1 has a scaler, and S-Boot's win3 is mapped to
it). No register of DPP, SRAMC or SysMMU has been read on this phone yet, so the first native step is to read them, and only once
their power domains are shown to be on.

## What changed (one object)

`bsd/e1s_display.o` is now built from `e1s_display.patch`:
- **Gate.** `e1s_dpp_snapshot()` first reads the stock pmucal status words "DPUB_STATUS" 0x12861D44, "DPUF0_STATUS" 0x12861D84 and
  "DPUF1_STATUS" 0x128626C4 (`flexpmu_cal_local_s5e9945.h:819, 898, 916`; `s5e9945-pm-domains.dtsi:93-115`). Unless bit 0 is set
  in all three, nothing else is read.
- **Reads.** Otherwise it loads NAT-162's table and prints it:
  - DECON FRAME_COUNT (first and last), TRIG_CON, SHD_REG_UP_REQ, INT_EN, DATA_PATH_CON;
  - windows 2/3 with their shadows, and their WINCON (CHMAP);
  - DMA L0/L1 with shadows;
  - DPP L0/L1, SRAMC L0/L1;
  - SysMMU 0x19840000 CTRL/STATUS/VERSION/CTRL_VM/FLPT (`samsung-iommu-v9.h:18-46`).
- **When.** At probe, and again from a kernel thread at 300 s of uptime, while iOS is drawing and the swipes run. Stamped kernel
  lines survive for the whole run (NAT-175: 0–383 s present), unlike the tail-only `tl:` lines.
- **Off switch.** `e1sdpp=0` turns it off.
- **No writes.** There is no store to any register.

Everything else is scR (NAT-174): the swipe thread, `touch_lat=1`, cpu0 FREQ_REQ. The command line is scR's with the tag
`nat_attempt=NAT176-scS`, still 254 B.

Kernel `artifacts/nat-176/kernel-001`: no-storage `d84b4ce0e6aed7d730dff9a2afbea49baf84d2eadfbb669e12e230be86966a58`,
0 undefined. `build.py` checks that it is NAT-174's record plus exactly `bsd/e1s_display.o` from this patch. NAT-152's view for
nat-123's four-object check is extended to hide that one verified object.

## Host checks

`python3 -B docs/procedures/nat-176/test_nat176.py`: 7 OK.
- **Static.** In the added lines a register pointer is only declared, compared with NULL, assigned from `ml_io_map`, or passed to
  `e1s_display_read`. There is no indexed store and no raw volatile access, and nothing of the original is removed.
- **Fake MMIO** (`host/fakemmio176.c`). Every mapping is read-only memory, so a store would fault. Each word encodes its own address.
  Both snapshots print exactly NAT-162's groups and offsets with the right values. The late one follows the 300-s clock mark. Each
  block is mapped once.
- **Gate.** Any of the three status bits at 0 means two "skipped" lines and only the PMU mapped. A value of 0x2 counts as off
  (bit 0). `e1sdpp=0` maps nothing.
- **Analyser `dpp177.py`.** Verdicts and decoding: visible window → DPP channel → scaler, SysMMU translating or not, changes from
  probe to late.

Mutants: a gate that checks DPUB only is caught (1 failure); an inserted PMU store is caught (3 failures).

- **Build** `artifacts/nat-176/build-001`: loader sites rc 0 / ok / bad 0, relocscan clean, 254 B.
- **Package** `artifacts/nat-176/package-001`, image `loader-diag-xnu-scS-md1`: RECOVERY
  `002f5653014155df0f19226ae5d2d7cdf696c70ea5fae7b1d968745321b6fdbd`.
- **Session** `session_nat177.py` (93ed6dad…), derived by counted replacement from NAT-175's (`derive177.py --check`).

## Registered verdicts for NAT-177 (`dpp177.py`)

| verdict | condition |
|---|---|
| R-none | no `e1s-dpp` line (probe not reached) |
| R-gated | a snapshot skipped because a display power domain reported off |
| R-partial | some of the 12 groups missing from a snapshot that was not skipped |
| R-ok | all 12 groups in both snapshots |

Decoded and reported, not judged:
- which DPP channel feeds each enabled window, and whether it has a scaler;
- DMA base, format and sizes; the DPP scaler state; SysMMU translating or bypassed;
- what differs between probe and late.

The NAT-175 analysers are also rerun, for reproducibility of F30 and C2.

## Risk specific to this image

A load from a block whose clock or power is off can hang the bus or raise an SError. Mitigations:
- the PMU gate;
- NAT-070 already read DMA L0–L3 in the same DPUF0 region on this phone;
- each group is printed as it is read, so a stop shows where it happened;
- the timed return and the fed watchdog bound the run.

## Not established here

- Host evidence only: nothing about what the phone's registers hold.
- The scaler programming itself, which is a later, separate image with its own decision.
