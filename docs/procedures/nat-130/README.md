# NAT-130: USB 2.0 root-delivery speed-up (host-test)

Owner `claude-opus-usb130-20261113`. Evidence kind **host-test**: nothing here ran on the phone. The native measurement is NAT-132.

## Why: where the 16 MB/s of NAT-078/NAT-127 goes (inference from existing records, to be measured by NAT-132)

NAT-127 delivered 2,475,720,704 B in 153.3 s as 296 chunks of 8 MiB: 0.518 s per chunk. Per chunk the old path is strictly serial:

1. host checksum of the chunk in pure Python (the pyusb venv has no numpy): **0.12 s measured on this host** for 8 MiB;
2. RX_BEGIN; the device cleans the 8 MiB destination by cache line;
3. the bulk transfer (USB 2.0 High-Speed; a practical HS bulk ceiling is roughly 35-45 MB/s, not measured here);
4. the device invalidates the range and sums it with one volatile 64-bit load per word. The loader runs with
   SCTLR_EL1 = 0x30d8199a (logged on the phone): **M = 0, C = 0**, so every one of those 1,048,576 loads is a Device-nGnRnE access;
5. GET_RX polls until the commit.

Steps 1 and 4 are CPU work while the wire is idle. Which of 3/4 dominates is not known; NAT-132 measures it.

## What changed

* `engine/` = NAT-076's engine plus, backward compatible for `flags == 0`:
  * RX_BEGIN `flags` bits 1:0 = checksum mode of the commit: 0 PLAIN (old loop), 1 FAST (four `ldp` per 64 B, still uncached),
    2 CACHED (port maps exactly the range + one code page read-only write-back through a private 4 KiB-page stage-1 table, turns
    M+C on for the sum only, turns them off, cleans+invalidates the range; temporary vectors switch the MMU off and continue at the
    loader's vector on a fault; falls back to FAST when it cannot map), 3 NONE (commit without a sum, counted);
  * `SUM` (0x40/0x0A): device sums a committed range with mode 0..2 (post-verification of NONE chunks, calibration);
  * `GET_RXT` (0xC0/0x09): phase ticks per chunk (arm/clean, wire, invalidate+sum, host gap) and the last SUM result.
  The NAT-130 port code is compiled only in `usbmon.c` (`USBMON_ENGINE_TU`); the loader's other units include the port header too.
* `root_send130.py`: the sender with modes. Policy `auto`: chunk 0 PLAIN (baseline), then SUM of chunk 0 in PLAIN/FAST/CACHED
  (each must equal the host sum, else the mode is not used), chunks 1-4 NONE (wire alone), the rest with the fastest verified
  mode; NONE chunks are post-verified right after the last of them, while the loader is still in its receive loop. Host sums are
  computed by a background thread (`SumCache`) started while the companion waits for the device. One bulk write per chunk.
  Per-chunk records: host sum / RX_BEGIN / write / poll seconds and the device ticks.
* `deliver130.py`: the unchanged NAT-080 companion run with this sender; adds `phases` to `delivery.json`.
* `build.py`: image `loader-diag-xnu-us1-md1` = NAT-126's sc9 build with only `ENGINE76` pointed at `engine/`.

## Results (host)

| check | result |
|---|---|
| `regress76.py`: NAT-076's 227 tests against this engine | 219 pass; 8 expected differences, each listed with its reason (flags=1 is now FAST; 3 seeded-defect anchors re-seeded below) |
| `test_nat130.py` (modes, SUM, GET_RXT, refusals, staged mode, 17 seeded defects) | 34 pass |
| `test_port130.py` (the aarch64 port text under Unicorn with its stage-1 MMU) | 8 pass: sums for 8 MiB unaligned/2 MiB/1 GiB-crossing ranges, M=C=1 inside the loop, SCTLR/VBAR/TTBR0/TCR/MAIR/TPIDRRO restored, tables map exactly range + code page RO/XN, fallbacks correct, fault leaves via the old vector with M=0 (exception entry emulated by the harness) |
| `test_sender130.py`, `test_deliver130.py` | 10 + 3 pass |
| sc9 rebuild through the chain | byte-identical Image `2f818b88…ec69` (chain reproducible) |
| us1 build/package | Image `7c9c413e…f424` (446,464 B), Image.payload `a338934c…ea40` (26,199,536 B), RECOVERY `364f26f8…9cb2` |
| `make check` | 448 pass |

Unicorn note: it resets SCR_EL3/HCR_EL2 to 0, which makes EL1 AArch32 for translation; the harness sets NS|RW and HCR_EL2.RW as on the phone.

## Not established

On-phone rate, whether CACHED works on the Exynos 2400 (EL2 traps, interconnect attributes, cost of `dc civac` with M=0), the HS wire
ceiling of this DWC3 + host, and anything about SuperSpeed (NAT-131 is the source review for that).

## Commands

```
TMPDIR=/home/egor/.cache/nat130-tmp artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-130/regress76.py
TMPDIR=... artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-130/test_nat130.py   (also test_port130/test_sender130/test_deliver130)
python3 -B -I docs/procedures/nat-130/build.py --out artifacts/nat-130/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-130/build-001 --out artifacts/nat-130/package-001
```
