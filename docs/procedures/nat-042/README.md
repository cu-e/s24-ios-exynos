# NAT-042 — Software-reset-to-Download-Mode return path for the diagnostic loader (source review + host test)

Evidence kind: **source-review + host-test**. Nothing here ran on the phone. Every number comes from the pinned open vendor
kernel (`s24-linux` @ `417484173abc2c4fa93e738ea82ad9f2e84911b1`) and, where marked, from the device's own measured runtime DTB.
**No S-Boot disassembly or static review was used** (the NAT-009/NAT-011 classifier stops are untouched).

## Why this exists

Every native run so far ended by waiting for the watchdog (83 s in NAT-020), after which the host saw `SEC_UPLOAD` (~+95 s) and
`SAMSUNG USB` only later, often after an owner action. Whether our PMU stores reach the hardware at all is unproven: runs
without our watchdog show the same pattern. NAT-043 (first unattended USB-log run) needs a *deterministic, bounded* way back to
a state the restore tooling (NAT-013) can use. The vendor kernel has such a path: `reboot download`. This task extracts it and
packages it as a small freestanding module the loader can call at the end of a run. It does not make that return path
*proven*: that is a native measurement (below).

## Files

| path | role |
|---|---|
| `plan.json` | 47 literal citations (file, line, exact text) at the pin, the derived-value table (17 values), the 6-step vendor sequence, what the loader replays, 3 absence claims, expectations for the runtime DTB |
| `verify_plan.py` | independent verifier: re-reads each cited line from the pin with `git show`, re-derives every number from the cited text (the plan's value must equal it), re-runs the absence greps, parses the measured runtime DTB (own FDT parser; no `dtc`) and compares `reboot-offset`, `reboot-trigger`, `reboot-cmd-offset`, `magic-inform`, `panic-inform` and the PMU `reg`. 105 checks |
| `module/s5e9945_reset.h`, `module/s5e9945_reset.c` | freestanding C: `s5e_reset_snapshot`, `s5e_reset_prepare`, `s5e_reset_trigger`, `s5e_reset_to`; `dsb sy` after every store that must be ordered, `wfi` loop after the trigger; hookable MMIO for the model |
| `test/host_test.c` | PMU register model (records every read/write/barrier) and 13 tests of the module |
| `mutate_reset.py` | breaks the module one line at a time; the host test must fail (27 mutants; a mutant that does not compile is INVALID, not killed) |
| `test_nat042.py` | the suite: verifier + negative controls (tampered line/text/pin/value/absence/DTB), header-constants-equal-derived-values, host model test, aarch64 freestanding build + assembly check, mutation run |
| `decision-template.md` | the decision text the agent fills in (decision 0019) before a native run that uses the module |
| `evidence.json` | the task's evidence record |

Run (host only; needs `cc`, `zig`, `git`, `references/s24-linux` at the pin):

```sh
python3 -I docs/procedures/nat-042/verify_plan.py --json artifacts/nat-042/verify.json
python3 -I docs/procedures/nat-042/test_nat042.py
python3 -I docs/procedures/nat-042/mutate_reset.py --out artifacts/nat-042/mutation   # standalone; test_nat042.py runs it into a temp dir
```

## What the vendor kernel does on `reboot download` (established from source)

PMU = a plain syscon (`samsung,exynos991-pmu` + `syscon`, no driver binds it: AB2) at `0x12860000`, so a PMU regmap write is one
32-bit MMIO store. Registers used (all offsets from the PMU base; the runtime DTB of this device carries the same numbers):

| register | offset | role |
|---|---|---|
| INFORM2 | `0xb8` | `magic-inform`: byte [23:16] ← `0x4e` (`SEC_REBOOT_NORMAL`), other bits kept |
| INFORM3 | `0xbc` | `panic-inform`: the reset reason word |
| reboot-cmd | `0x190` | bits [2:0] ← mode (read-modify-write, mask 7) |
| reboot | `0x3c00` | write `2` = software reset (`reboot-trigger`) |

Reason words (`SEC_RESET_REASON_PREFIX 0x12345600 | n`): unknown/NULL `0x12345600`, **download `0x12345601`**, recovery `0x12345604`,
bootloader `0x1234560d` (commented "go to download mode" in the source). The module deliberately has no constant for recovery.

Sequence for `reboot download` (plan.json `vendor_sequence_download`):

1. `sec_reboot` (restart notifier, priority 130): INFORM2 byte ← 0x4e (RMW).
2. `sec_reboot`: INFORM3 ← `0x12345601`.
3. `sec_reboot`: `cache_flush_all()`, returns `NOTIFY_DONE` so the chain continues.
4. `exynos-reboot` (priority 128): ACPM STOP IPC (`acpm_enter_wfi`).
5. `exynos-reboot`: reboot-cmd bits [2:0] ← mode: `3` for `"bootloader"`, `0` for everything else, **including `"download"`** (AB3: the
   driver does not know that string; only `sec_reboot.c` does, and it is the INFORM3 word that carries the intent).
6. `exynos-reboot`: `0x3c00` ← `2`, then `wfi`.

### Loader versus vendor (what is, and is not, replayed)

| | vendor kernel | existing loader (`recovery_guard.c`, NAT-020) | this module |
|---|---|---|---|
| INFORM3 | written (reason) | read; `0x12345604` cleared to `0x12345600` | written `0x12345601`, read back |
| INFORM2 byte | written | never | written, read back |
| reboot-cmd `0x190` | RMW bits [2:0] | never | RMW bits [2:0], mode bits read back |
| reset trigger | `0x3c00 ← 2` | none: route PMU `0x1244`/`0x1844` + WDT only | `0x3c00 ← 2` after all read-backs OK |
| ACPM STOP | yes | no | **no (no ACPM channel in the loader) — unknown U2** |
| cache flush | yes | no | not replayed (no cacheable state is needed by the reset) |

The module therefore replays vendor steps 1, 2, 5, 6. It is a *reconstruction*, not the vendor sequence.

### Unreconciled prior claims

NAT-004/NAT-011 recorded SWRESET at `0x12860400`/`0x12863a00` and RST_STAT at `0x12860a0c`. Those came from S-Boot static review, were
never verified (NAT-014 is the open check) and **conflict with the vendor `reboot-offset 0x3c00`** confirmed by the device's own
runtime DTB. They are not used here and not deleted from their original notes. If a native run shows the vendor offset has no
effect, the NAT-004/011 offsets become the next thing to test — as a measurement, not as a reading of S-Boot.

## Design for the loader (NAT-044 integrates it; not done here)

* At entry take `s5e_reset_snapshot()` and log INFORM2/INFORM3/0x190 (a missing or stale word is information for U3).
* The run keeps the existing 83 s WDT as the failsafe; the loader itself ends the run at a deadline well before it (≈75 s):
  `s5e_reset_to(pmu, S5E_REASON_DOWNLOAD)`. It never returns on success; a non-zero return (reason rejected or a read-back
  mismatch) means **no trigger was written** — log it and fall through to the watchdog.
* Leftover request: if INFORM3 already reads `0x12345601` at entry, an earlier run left a Download request behind. The loader logs it
  and writes `S5E_REASON_NORMAL` (through `s5e_reset_prepare`, no trigger), as `recovery_guard.c` already does for `0x12345604`, so that
  a run which dies before its own end-of-run path cannot leave the phone asking for Download Mode. The end-of-run call then sets
  DOWNLOAD again. This is NAT-044 image logic, not part of this module.
* The module is a pure function of the PMU window. It does not touch RECOVERY, GPT, EFS or anything else.

## Unknowns (each is a native measurement, not a source question)

| id | question | would be resolved by |
|---|---|---|
| U1 | Do the loader's PMU stores (INFORM2/3, 0x190, 0x3c00) take effect — can the loader write them from EL1/EL2 with the MMU off? | the snapshot at the *next* entry, and whether a reset happens at the deadline instead of the WDT |
| U2 | Does a software reset without the ACPM STOP request work at all? | the reset happening (or not) with all read-backs OK |
| U3 | Does S-Boot honour INFORM3 = DOWNLOAD while its persistent parameter reboot mode is `4` and `0x190` holds a leftover mode? | host enumeration after the reset: iProduct `SAMSUNG USB` (Download Mode) vs `SEC_UPLOAD` vs a normal boot |
| U4 | Is DOWNLOAD (`…01`, primary) right, or does only the BOOTLOADER word (`…0d`) produce Download Mode on this firmware? | the same enumeration; the module supports both reasons so U4 can be a second run |

## Native test plan (NAT-043 chooses when to run it)

* Image: the ckpt3 loader (or the NAT-044 image) with the module linked in, WDT as failsafe.
* Decision text written by the agent before the run under decision 0019 (protocol of runs 001–009: only RECOVERY (`/dev/block/sda18`)
  written; pinned stock RECOVERY SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` restored afterwards with
  the NAT-013 tool and the pyusb venv; full-hash readback; one-shot marker; bounded display/watchdog; hashes recorded).
* Pass/fail wording is fixed in advance: **success** = host sees `SAMSUNG USB` within a stated bound without an owner action and
  without the WDT elapsing; **U1/U2 refuted** = no reset until the WDT; **U3/U4 refuted** = reset occurs but the host sees
  `SEC_UPLOAD` or a normal boot. Any outcome is evidence; none is "return to Android is solved".

## Honest limits

* Established: the sequence, the offsets, the reason words, the mode mapping and the PMU being a plain syscon, all at the pin and
  cross-checked against the measured runtime DTB of this S24 (105 verifier checks, tamper-tested).
* Established on the host only: the module writes exactly the intended registers in the intended order with read-backs, refuses
  other reasons, and does not trigger after a failed read-back (13 model tests, 27/27 mutants killed, aarch64 build clean with
  `dsb sy` and `wfi`). The model is my reading of the vendor code; a shared misreading is invisible to these tests.
* **Not established:** U1–U4; that S-Boot honours the reason word; that any of this returns the phone to Android or to
  Download Mode; anything about the phone's state. Nothing ran on the S24.
