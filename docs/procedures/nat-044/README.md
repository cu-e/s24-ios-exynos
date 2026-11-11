# NAT-044 — Reset canary image `loader-diag-reset` (host build + host/simulator test)

Evidence kind: **host-test**. Nothing here ran on the phone and nothing was flashed. The images are built, hashed and tested
on the host only. The Aarch64 layer is an instruction-level simulation (unicorn): it shows the register/memory contract of the
new code inside the compiled loader, not the behaviour of the S24.

## Why this exists

NAT-043 (first unattended native USB-log run) needs a *deterministic, bounded* way back to a state the restore tooling
(NAT-013) can use. Every native run so far (001-009) ended by waiting for the 83 s watchdog; the host then saw `SEC_UPLOAD`
(~+95 s) and `SAMSUNG USB` only after an owner action. NAT-042 extracted the vendor kernel's `reboot download` sequence into a
freestanding module. Whether the loader's PMU stores take effect, and whether S-Boot honours the Download request, is
unmeasured (U1-U4 of NAT-040/NAT-042). This image is the measurement vehicle: the run-006 loader, which reached PRE_JUMP and
held, plus one reset attempt at a deadline inside the watchdog period. The measurement itself is NAT-046 (native, needs the
phone and the registry `native` permission under decision 0019); this task only builds and tests the image.

## What the image does

Base: NAT-020 build-003 loader (GPL-2.0, e1s loader) + NAT-022 `patch_loader.py --trig-hold --adt-aligned` + NAT-022 marker
library + NAT-026 payload header fix (the run-006 loader family). On top, `patch_loader4.py` applies six exact-match hunks:

| file | hunk |
|---|---|
| `marker.h` | enumerators `MK_RST = 14` (report frames) and `MK_ST_RESET = 0x41` (stage) |
| `markerlib.c` | `mk_wait_tenths` polls `nat044_tick()` (both the busy loop and the skip-wait branch); `mk_hold`'s loop shows `nat044_show()` |
| `guard.c` | `recovery_guard()` calls `nat044_snapshot(pmu)` before the first diagnostic, and `nat044_arm()` right after `s5e_wdt_arm(&w, 83)` |

The new code is in `src/markerlib4.c` (the unit compiled *instead of* `markerlib.c`; it `#include`s the patched one to reach its
static helpers) and `src/reset44.h`. The reset is the **unmodified** NAT-042 module (`docs/procedures/nat-042/module/`).

Run order on the phone:

1. Loader start, ADT/payload preparation, watchdog arm (83 s): unchanged from run 006.
2. `nat044_snapshot`: reads INFORM2 (+0xb8), INFORM3 (+0xbc) and reboot-cmd (+0x190) of the PMU (0x12860000) at entry. If
   INFORM3 holds Download (0x12345601) or Bootloader (0x1234560d) it is overwritten with NORMAL (0x12345600) and read back;
   no other word is touched. The cleared value is **not** hidden: the report shows the entry words and a CLEARED/CLEARFAIL flag.
3. `nat044_arm`: the deadline (default 45 s, build option) is measured from after the watchdog arm, so it is always earlier than
   the watchdog; the build refuses `deadline_s > wdt_s - 20` and `deadline_s <= 0`.
4. The loader holds PRE_JUMP drawing the run-006 markers plus the RST report frames (kind 14): idx 0/1 INFORM3 hi/lo at entry,
   2/3 INFORM2, 4/5 reboot-cmd, 6 status word.
5. At the deadline (polled from every wait loop, so within one draw) the loader draws the RESET stage frame (0x41), then calls
   `s5e_reset_to(PMU, reason)`: INFORM2 byte 2 := 0x4e, INFORM3 := reason, reboot-cmd bits [2:0] := mode, each with a read-back,
   then `0x3c00 := 2` and `wfi`. The attempt happens at most once.
6. If the module returns (reason refused or a read-back differed) nothing was triggered: the status word is drawn (kind 14, idx 7)
   and the hold continues; the watchdog stays the failsafe.

Status word (kind 14 idx 6/7): `rc` bits 7:0 (negated `s5e_reset_to` result: 1 reason refused, 2 INFORM2 read-back, 3 INFORM3
read-back, 4 reboot-cmd read-back), `FIRED` 0x1000, `ARMED` 0x2000, `CLEARED` 0x4000, `CLEARFAIL` 0x8000.

Two images, differing only in the reason word and reboot-cmd mode:

| image | reason | mode | purpose |
|---|---|---|---|
| `loader-diag-reset` | `S5E_REASON_DOWNLOAD` 0x12345601 | 0 | the vendor `reboot download` words (U3) |
| `loader-diag-reset-bl` | `S5E_REASON_BOOTLOADER` 0x1234560d | 3 | the `reboot bootloader` words (U4); only after the first image shows a reset that did not reach Download Mode |

## Files

| path | role |
|---|---|
| `build.py` | builds both images from a copy of the loader source (`--loader-source`), applies the NAT-022 and NAT-044 patches, compiles with the loader flags, fixes the payload header, writes `build.json` (hashes of images, payloads, the NAT-042 module and the NAT-044 sources) |
| `patch_loader4.py` | the six-hunk source patch; all-or-nothing, each anchor exactly once |
| `src/reset44.h`, `src/markerlib4.c` | the new code (snapshot, arm, tick, show) |
| `decode44.py` | decoder for kind 14 and stage 0x41 on top of NAT-022's `decode.py` |
| `test_support/host_mk4.c`, `test_support/reset_host.c` | x86 harness: the real patched `markerlib.c` + `markerlib4.c` + the NAT-042 module against a PMU register model |
| `test_nat044.py` | 46 tests: Patch, HostReset, Build, Aarch64 (unicorn) layers; layers skip themselves with a reason when `unicorn`/`capstone`/`zig` are missing |
| `mutate_nat044.py` | 46 mutants of the new code, the patch hunks and the build rules; each must fail a test (a mutant that does not build is INVALID, not killed) |
| `decision-template.md` | the decision text the agent fills in under decision 0019 before the native run (NAT-046); not a decision record |
| `evidence.json` | the task's evidence record |

Build and test (host only; needs `cc`, `zig`, the loader source copy of NAT-020 build-003):

```sh
python3 -I docs/procedures/nat-044/build.py --out artifacts/nat-044/build-001 --loader-source <copy of the run-006 loader source tree>
python3 -I docs/procedures/nat-044/test_nat044.py                      # system python: the layers that need no unicorn run, the rest skip
<venv with unicorn+capstone>/bin/python -I docs/procedures/nat-044/test_nat044.py   # all 46 tests
<venv with unicorn+capstone>/bin/python -I docs/procedures/nat-044/mutate_nat044.py --out artifacts/nat-044/mutation-001 --jobs 4
python3 -I docs/procedures/nat-022/package.py --image artifacts/nat-044/build-001/loader-diag-reset/Image --out artifacts/nat-044/package-001
```

(`-I` matters: an interpreter run from a directory containing a `dis.py` shadows the standard library.)

## What is established, what is not

Established (host-test): the patched sources equal the run-006 sources except the named hunks; the aarch64 images build
reproducibly (two builds, identical hashes), carry a valid Image header and fit one MiB; in the
instruction-level run of the compiled loader the PMU stores occur in the NAT-042 order with the vendor values, at the deadline
and after the RESET marker, the entry snapshot shows on screen, a leftover Download/Bootloader request is cleared and reported,
a read-back failure triggers nothing and is reported, an unarmed loader never writes the PMU, and the deadline is armed only
after the watchdog (call order of the real `recovery_guard`).

Not established, and not claimed:

* **U1**: that the loader's PMU stores reach the hardware. **U2**: that `0x3c00 := 2` resets without the ACPM STOP request that the
  vendor kernel sends first. **U3/U4**: that S-Boot honours INFORM3 = Download / Bootloader. All four are native measurements
  (NAT-046); the simulator and the host model are not the S24 and have no caches, MMU or memory attributes.
* The RESET marker is on screen for milliseconds before the reset: its absence in a recording is not evidence.
* If the trigger store takes effect but the SoC does not reset, the loader sits in the NAT-042 `wfi` loop and the watchdog ends the
  run at about +83 s, as in runs 001-009.
* The entry words are read *before* the clear, so a Download/Bootloader request left by an earlier run is visible in the
  report (INFORM3 entry word + CLEARED flag), not hidden. The clear itself is a PMU write the simulator only models.
* A reset that works is not "return to Android is solved": that is a separate measurement (NAT-046 reports what the host sees).

## Findings made while testing (both about the tests, not about the image)

* `zig cc` emits FP/SIMD registers even with `-mgeneral-regs-only` (already noted in `nat-022/build.py`): the NAT-044 code has
  `ldr d0` / `str d0` pair copies in `nat044_snapshot` and a `d8` constant in the base marker code. This is safe in the loader
  because `start.S` clears `CPTR_EL2` and sets `CPACR_EL1.FPEN` before the first call into C (checked by
  `test_the_loader_enables_fp_simd_before_any_c_code_runs`). It would *not* be safe in code that runs after the kernel took over.
* My first version of the "no SIMD in the text" test was vacuous: `capstone.Cs.disasm()` stops at the first undecodable word and
  decoded only the two instructions of the Image header. It was replaced by the FPEN property above. NAT-036's equivalent test
  (`test_the_nat036_code_has_no_simd_and_no_misaligned_access`) disassembles per function symbol and asserts the whole function
  decoded, so it does not have this defect; NAT-044's `Build` layer now follows that pattern (`ElfImage.code`).
* The first mutation run (45 mutants) found two survivors: the CLEARFAIL status bit (the test computed the expected status itself
  instead of decoding what the loader draws: tautological) and the `dsb sy` between the INFORM3 clearing store and its read-back
  (nothing looked at the compiled code). Both tests were rewritten to check the real output; a mutant that only the build
  refused (`wdt` parsed as one digit) was INVALID and was replaced by one that builds. The final run is `mutation-002`.

## Next

NAT-048 (session driver with a decision-file gate and a host USB event logger) and NAT-046 (the native run). The decision text
for NAT-046 is `decision-template.md`.
