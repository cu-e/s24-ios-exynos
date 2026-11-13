# NAT-134: read-only SuperSpeed prerequisite probe (host)

Owner claude-opus-usb130-20261113. Evidence kind host-test. This is the probe NAT-131 section 5 recommends as the first SS
experiment: it resolves U4 (DWC31 revision), U5 (cold state of PMU/USBDP/TCA/CMU at loader entry), U6 (indirectly), U7
(PERIC2 GPIO readable) and U11. NAT-133 already answered U1, U2, U3 (not available), U6 under Android, and U8.

## What changed

- `engine/` is NAT-130's engine with one request added. **PEEK** (0xC0/0x05) needs wIndex = 0x5045 and wLength ≥ 16. wValue is an
  index into `peek_addr[]` in `usbmon.c`, a fixed table of 64 addresses, the same list in the same order as `peek134.py` TABLE.
  - The reply is `struct usbmon_peek`: magic "S24P", index, count, address, value. Each request does one 32-bit read through
    the new port hook `usbmon_peek32` (aarch64: a volatile load followed by `dsb sy`).
  - The request stalls on any other wIndex (including NAT-076's wIndex 0), an index past the table, or a short wLength.
  - There is no arbitrary-address form and no write form. The struct layouts of NAT-076/NAT-130 are unchanged.
- `model/`: NAT-130's model plus a test register file for `usbmon_peek32`, with a read log and fault injection.
- `peek134.py`: TABLE (in group order pmu, dwc3, usbcon, cmu_hsi0, usbdp, tca, cmu_peric2, gpio) and `run()`.
  - Entries are read in order, and each request/value is journalled with fsync before the next.
  - The usbdp, tca and gpio groups are skipped if their CMU gate (read earlier) shows MANUAL=1/CGVAL=0. The gate bits come from
    the cmucal SFR_ACCESS rows at the NAT-131 pin.
  - The probe stops at the first failure or mismatched reply.
- `deliver134.py`: NAT-130's deliver130.py, loaded unchanged, with the probe run on the delivery connection before the first
  RX_BEGIN. A probe error ends the run before any delivery; `--no-peek` gives NAT-130 behaviour.
- `build.py`: image `loader-diag-xnu-pk1-md1` = us1 with only `ENGINE76` pointed at `engine/` (tag `nat_attempt=NAT134-pk1`, the same length).
- `derive135.py` → `session_nat135.py`: NAT-132's session driver with counted substitutions (image, hashes, package, decision
  glob, marker, preconditions, companion).

## Results (host)

| check | result |
|---|---|
| `regress134.py`: NAT-076 suite + NAT-130 suite, unchanged, on the NAT-134 engine/model | 261 run, 8 failures = NAT-130's listed expected differences, 0 unexpected |
| `test_nat134.py` | 21 tests OK: table equals host table; shape, blocks and gate order; protocol and refusals read nothing; delivery unaffected; host order, gating, stop, mismatch; 6 seeded defects caught, plus a control on the unmodified engine |
| `test_deliver134.py` | 4 tests OK: probe before the first RX_BEGIN, then delivery; gated group skipped; failed read stops before any RX_BEGIN; `--no-peek` |
| `port134.py` (NAT-130's Unicorn port tests on this engine dir) | 8 tests OK |
| pk1 build/package | Image `20da048a…0c95` (446,464 B), Image.payload `adc3c40f…06aa` (26,199,536 B), RECOVERY `98f38989…8f69`. Against us1, build.json differs only in the four engine file hashes and the hashes derived from the Image |
| `derive135.py --check` | pass; session_nat135.py sha256 `a7ed4383…500a` |

Host tests say nothing about what the phone's registers hold or whether reading them is safe there. Decision 0054 records the
single native run (NAT-135) and its risk (an unclocked read can stall; then the watchdog path of NAT-046/NAT-059 applies).

## Commands

```
python3 -B docs/procedures/nat-134/regress134.py
python3 -B docs/procedures/nat-134/test_nat134.py
python3 -B docs/procedures/nat-134/test_deliver134.py
TMPDIR=/home/egor/.cache/nat134-tmp artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-134/port134.py
python3 -B -I docs/procedures/nat-134/build.py --out artifacts/nat-134/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-134/build-001 --out artifacts/nat-134/package-001
python3 -B docs/procedures/nat-134/derive135.py --check
```
