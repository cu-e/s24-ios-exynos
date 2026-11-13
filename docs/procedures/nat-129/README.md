# NAT-129: scA image (touch rails + bounded polling touch ID, keys off) on the us1 loader

Owner claude-opus-usb130-20261113. The task was transferred from Hermes (claude-opus-nat116-20261113) under decision 0003. Evidence kind host-test.

## What is built

`build.py` builds `loader-diag-xnu-scA-md1` using NAT-123's build chain (sc8/sc9 plumbing) with these changes:
- the kernel is `artifacts/nat-128/kernel-001` (`d6d56001…4517`: NAT-128's three bounded read-only ID attempts, no IRQ or event thread);
- the tokens are `e1s_wdt_pet=1 e1s_decon_hw=1 e1spmic=2 e1skeys=0`;
- NAT-115's `DROP_BASE_TOKENS` is extended by `e1sufs_probe=0`. Its only reader, `e1s_ufs_probe`, returns on `e1sufs=0` first, and
  `e1sufs=0` stays. Without the drop, the cmdline would be 258 bytes; with it, 243;
- the loader engine is NAT-130's (us1, 37.19 MB/s in NAT-132).

The post-build check asserts the tokens, the dropped ones, ≤ 255 bytes, the kernel hash, and the engine hashes.

`derive137.py` → `session_nat137.py` is NAT-132's session driver with counted substitutions: image, hashes, package, decision glob,
marker, and preconditions (+ NAT-128/129/132). The companion stays NAT-130's.

`analyze137.py` is the pre-registered analyser for the run, covering touch from the `poll N device/hardware id` lines plus keys,
power, window and display.

## Results (host)

| check | result |
|---|---|
| build | Image `e0aec56f…296b`, Image.payload `332da1f8…cbec` (26,199,088 B), cmdline 243 B |
| package | RECOVERY `a4809fe2704fe86b376016345ced17d669096483de892bc16c212735ce312826` |
| `test_nat129.py` | 5 OK. The kernel's own `e1s_input.c` is compiled with counting stubs and executed: `e1skeys=0` gives 0 threads, 0 PMIC calls, 0 MMIO maps; without the token, or with `e1skeys=1`, the thread starts (control). The kernel binary carries the disabled string. The cmdline is checked |
| `nat-123/test_nat123.py` | 12 OK (PMIC allowlist, readback, refusals) |
| `nat-128/test_nat128.py` | 1 OK (exactly nine read frames, no IRQ/thread, for both synthetic peers) |
| `test_analyze137.py` | 7 OK |
| `derive137.py --check` | pass, session_nat137.py `c1af9a28…d346` |
| `make check` | 448 OK |

Single-run decision: docs/decisions/0055-nat137-loader-diag-xnu-scA-md1-single-run-2026-11-14.md. It quotes the owner's
standing LDO9/LDO18 consent (0052) and the 2026-11-14 direction to the touch line. Nothing here is phone evidence.
