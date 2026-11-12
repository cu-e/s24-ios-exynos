# NAT-104: `loader-diag-xnu-hb2-md1` (B8 Log-Window & USB Settle Fix)

**Evidence kind:** `host-test` (build, packaging, C host harness, synthetic archive tests, and mutation pass on host only; nothing here runs on a phone).

## Root Cause Addressed (B8)

In `NAT-098` and `NAT-103`, `loader_return.c` appended the `~30.5 KiB` kernel message buffer after the console ring inside `loader_log` (`116,430` bytes in `NAT-103`), while `glue62_impl.h` returned only `NAT062_HEAD_RETURN = 8192u` and `NAT062_TAIL_RETURN = 32768u`. Combined with an initial `32 KiB` USB ring overflow during `why=2` return reconnect (`NAT062_BURST = 8192u` with no pre-begin settle wait), `75,470` middle bytes plus `4,896` dropped tail bytes hid all `hb` and `ps` console output.

## Changes Over `NAT-102`

`docs/procedures/nat-104/build.py` keeps the exact `NAT-102` XNU payload, ADT, `4,194,304`-byte `md0` small root (`97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c`), and only updates:
1. Command-line tag: `nat_attempt=NAT102-hb1` -> `nat_attempt=NAT104-hb2` (2 differing ASCII bytes after the `385,024`-byte loader region in `Image.payload`).
2. `shim/e1s-xnu/glue62_impl.h` (`sha256 38d8723b033bcb6b969af9ca961586c54f0582c3c56d720dcb0efd5f7b8df863`) via fail-closed `patch_glue104()`:
   - `NAT062_TAIL_RETURN`: `32768u` -> `262144u` (`8192 + 262144 = 270,336` bytes capacity; `gap = 0` for `116 KiB` logs; `262144 % 96 = 64 != 0` preserves unambiguous `kl_reader2.py` geometry inference).
   - `NAT062_BURST`: `8192u` -> `4096u` (well under `1/3` of the `32 KiB` USB ring per burst).
   - Return settle delay: `10 * N62_WAIT()` (`5 s`) inserted strictly for `why == NAT062_WHY_RETURN` before emitting `KL begin`; `NAT062_WHY_FINAL` (`8192 + 8192`, `0` pre-begin waits) is unchanged.

## Built Artifacts (`artifacts/nat-104/`, gitignored)

- `Image` (`385,024` bytes): `88f64a746e58df72a8c4a8f81f1bf38c674a3e5f834e041f94873ab237fdbc07`
- `Image.payload` (`26,134,288` bytes at offset `2048`): `4161da474ddb1c708d8b2674111d8f6e6286a697888a999b6d1fee5963d3d1b7`
- `recovery.img` (`100,663,296` bytes): `540b64a5736d444bdf8c0f09a6897c0469b3fb36332dce87f3ff626377bb1963` (`19,627` differing 4K pages vs stock `96620b8b...`)

## Verification

- `derive104.py --check`: `ok: session_nat104.py equals the derivation (9 substitutions)` (`session_nat104.py` `sha256 fcb5b383f2c9ded4431317a9d5ab773f5ed362eec937789570fc0b77cf68b6c8`).
- `test_nat104.py -v`: `20` tests `OK` (`BuildWrapper`, `BuiltPayload`, `-DNAT062_HOST -Wall -Wextra -Werror` `CHostHarness`, `AnalyzeNat104` with `120 KiB` / `280 KiB` synthetic archives and `NAT-103` `40960`-byte grid refusal, `SessionDriver104` gate & derivation).
- `mutate_nat104.py`: `254` mutants (`analyze_nat104.py`: `116` total / `107` killed / `1` equivalent / `8` invalid; `build.py`: `119` total / `114` killed / `1` equivalent / `4` invalid; `derive104.py`: `19` total / `19` killed), `0` unexplained survivors (recorded in `mutation.json` and `equivalent.json`).
- Candidate single-run decision drafted in `docs/decisions/0039-nat104-loader-diag-xnu-hb2-md1-single-run-2026-11-12.md`.
