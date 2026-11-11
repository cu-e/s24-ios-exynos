# NAT-045 — USB bring-up ladder of the loader (host build + host/simulator test)

Evidence kind: **host-test**. Nothing here ran on the phone. The ladder is C code, generated from the pinned vendor sources,
built for x86 and aarch64 and exercised against a register-level model and an instruction-level simulator. It is not a
measurement of the S24.

## Why this exists

NAT-043 (first unattended native USB-log run) needs the loader to get the USB controller from "unknown" to "the NAT-041 log
engine can run" without the Linux kernel, and to say *where* it stopped when it cannot. Runs 001-009 only ever showed stage
numbers on the screen. The vendor driver sequence (NAT-040 plan) is long and every step can fail silently (a gated clock reads as
zero, an unpowered domain stalls the bus). This task turns the plan into a ladder of rungs, each of which checks what it relies
on and stops with a code that names the rung, the failure class and the table row.

## The ladder

| rung | what | writes | ops |
|---|---|---|---|
| L0 | table self-check (rung layout, read-only rungs really read-only); hardware untouched | no | — |
| L1 | `pd_hsi0` power state: PMU `HSI0_CONFIGURATION`/`HSI0_STATUS` (always-on PMU) | no | 2 |
| L2 | CMU_TOP mux/gate/divider feeding HSI0 (always on) | no | 3 |
| L3 | domain off → vendor power-on rows + bounded wait + `hsi0_cmu_init` rows; then CMU_HSI0/QCH reads | yes | 21 |
| L4 | DWC3 liveness: `GSNPSID` upper half is `0x5533` or `0x3331` | no | 1 |
| L5 | PHY isolation release, USBCON `init_link`, pipe3 detach, eUSB2 PHY initiate, read-backs | yes | 84 |
| L6–L8 | NAT-041 engine: core init + `RUN_STOP`, bus reset / `CONNECTDONE`, host nonce | yes | `ladder_usb.c` |

111 ops in L1–L5. Stop code `LAD_ERR(rung, code) = -(rung*16 + code)`; codes READBACK 1, TIMEOUT 2, STATE 3, NOTALIVE 4, CFG 5,
DISABLED 6. `lad_state.err_op` is the table row; `ladder_ops.json` names it (label, vendor source text, NAT-040 plan steps).

**L0–L2 are read-only and are the only rungs in the default image.** Without `-DLAD_WRITING_RUNGS` `ladder.c` has no store and no
delay compiled in, the default stop rung is 2, and `lad_run` refuses rung 3 and above with `LAD_E_DISABLED` before touching the
hardware (tests: `DefaultBuild`, and the `Aarch64` object has no store to a device window, no barrier store and no counter read).
A write rung stops at its first failed read-back, never retries, and never writes a block that the domain state says is off.

## How it is built

```
ladder_spec.json  -- selection data: which vendor functions/rows, in which order, which are omitted and why (no constants)
      |
derive.py         -- reads the vendor sources at the pinned SHA (git show), compiles the function bodies, re-reads every constant
      |              from the pinned text, cross-checks against the NAT-040 plan; refuses anything it cannot model (exit 2)
      v
src/ladder_regs.h + ladder_ops.json  (generated; `derive.py --check` = up to date)
      |
src/ladder.c      -- interpreter over the NAT-041 port (usbmon_rd32 / wr32 / delay_us / ticks); no hardware constant in C
src/ladder_usb.c  -- L6–L8: maps usbmon_init / usbmon_poll results to stop codes
```

Vendor pin: `417484173abc2c4fa93e738ea82ad9f2e84911b1` (`references/s24-linux`). Vendor semantics reproduced: PMUCAL write is a plain
store when `mask == U32_MAX`, otherwise read-modify-write; a PMUCAL wait polls every 1 µs and gives up after more than 200 000 polls;
`hsi0_on` uses the always-on PMU block `0x12860000` (CONFIG +0x2000, STATUS +0x2004); delays in L5 are 500/500/10/10/10/1000/28/2500 µs.

Build and test (host only):

```sh
python3 -I docs/procedures/nat-045/derive.py --check          # 0 = the generated files equal what the vendor sources give
python3 -I docs/procedures/nat-045/test_nat045.py               # system python: Table, Generator, Ladder, DefaultBuild, Usb; Aarch64 skips
<venv with unicorn+capstone>/bin/python -W ignore -I docs/procedures/nat-045/test_nat045.py      # all layers (zig on PATH)
<venv>/bin/python -W ignore -I docs/procedures/nat-045/mutate_nat045.py --out artifacts/nat-045/mutation-004 --jobs 10
```

`--out` must not exist. NAT procedure tests are not part of `make check`.

## Files

| path | role |
|---|---|
| `ladder_spec.json` | the selection data for `derive.py` |
| `derive.py` | vendor-body compiler + NAT-040 cross-check; `--write` / `--check` |
| `src/ladder.h`, `src/ladder.c`, `src/ladder_usb.c` | interpreter and L6–L8 glue (freestanding, no libc) |
| `src/ladder_regs.h`, `ladder_ops.json` | generated op table (do not edit) |
| `test_support/plat.c`, `plathost.py` | x86 host platform: register file, HSI0 power-domain gate, virtual time, fault injection; the NAT-041 DWC3 model behind the DWC3 window |
| `test_support/devmodel.py` | independent reference interpreter + platform in Python (access log with virtual time) |
| `test_support/a64sim.py` | aarch64 build with the loader's port, run in unicorn |
| `test_nat045.py` | tests, five layers (Table, Generator, Ladder, DefaultBuild, Usb) + Aarch64 |
| `mutate_nat045.py` | mutation runner: C, generator and table mutants; each must fail a test or be justified |
| `evidence.json` | the task's evidence record |

## The unknowns of NAT-040 as probe results

The NAT-040 unknowns are not guessed in the code; each one is either a recorded value with a name or a documented non-attempt:

| unknown | what the ladder records / does | where |
|---|---|---|
| U1 supplies | nothing readable; a block that answers all-zero/all-ones stops with `NOTALIVE` (L4 `GSNPSID`, L5 USBCON `VERSION`) | `lad_exec_read`, `LAD_F_NOTALIVE` |
| U2 `pd_hsi0` / SMC | `lad_state.pd_was_on` (0/1, `0xff` = L1 did not run) from the `HSI0_STATUS` read under the vendor mask; L3 writes only when it is 0 and `allow_pd_poweron`; the SMC (0.02) is **not attempted** | L1, `lad_rung` |
| U3 clocks | every CMU_TOP (L2) and CMU_HSI0/SYSREG/QCH (L3) read is a record `lad_rec{op,v0}` with a label in `ladder_ops.json` | L2, L3 reads |
| U4 repeater/tune | not touched (`phy_exynos_eusb_tune` returns early without `hs_tune_param`) | README finding |
| U5 DMA | not part of L1–L5; the NAT-041 engine is the first user (L6) | `ladder_usb.c`, NAT-041 |
| U6 combo PHY / ids | `lad_state.gsnpsid` (L4); read-back records of every L5 store (`v1`), `soft_mismatch` for the vendor writes the plan does not list | L4, L5 |
| U8 end of a run | not part of the ladder; NAT-042 reset | NAT-042/044 |

## What is established, what is not

Established (host-test): the L1–L5 sequences are exactly the vendor sequences at the pinned SHA, including bit-field values (checked
independently against the C compiler's bit-field layout of the vendor headers) and the NAT-040 plan rows; the ladder never touches
the HSI0 block while the domain is off; the first failed read-back/timeout/liveness check stops the run with the documented code;
the default build contains no store and no delay; the aarch64 build performs the same accesses in the same order with the same
virtual time as the reference.

Not established, and not claimed:

The numbers are the unknowns of the NAT-040 plan (`docs/procedures/nat-040`):

* the effect of any write on the real SoC: nothing ran on the phone.
* **U1** — the rails are not readable from the loader, so a stop at L3/L4 cannot be told from an unpowered rail by this code alone.
* **U2** — the power-domain state at L1: the S24 may report `pd_hsi0` on or off at loader entry; both paths are tested on a model.
* **U3** — whether the L2/L3 clock reads are plausible (an all-zero read after L3 would mean the mux did not take effect).
* **U4** — the repeater/PHY tuning is not touched (`phy_exynos_eusb_tune` returns early without `hs_tune_param`).
* **U5** — DMA behaviour of the NAT-041 engine (cache/coherence) is not modelled.
* **U6** — the `GSNPSID` value and the read-back of the USBCON/eUSBCON registers on the real block.
* **U8** — the NAT-042 reset path as the way back after a stop.
* The aarch64 layer is unicorn: no MMU, caches, memory attributes, SError or real bus.

## Findings made while building this

* **Not in the NAT-040 plan.** The vendor `ready_rewa` tail (ops 45–60: REWA_CTL, HSREWA_CTL, REFTO, HSTK, INTR, INT1_EVNT_MSK) is part
  of the vendor `init_link` and the ladder performs it, but the NAT-040 plan does not list it. Its stores are marked `LAD_F_SOFT`: a
  read-back mismatch is recorded in `soft_mismatch`, not fatal.
* **QCH enable** (plan 1.03) is not a ladder write — only QCH reads in L3. The wrapper steps 1.04/1.06 are calls whose content is
  the cited rows; 3.07 (`phy_exynos_eusb_tune`) returns early; 3.13 is the argument of `udelay(value)` and has no row of its own; the delay ops
  31/33/39/100 carry an empty plan list. The SMC step (0.02, `DTZPC` `0x17810204`) is **not attempted** by the ladder.
* **U6 risk.** The vendor `exynos_usbcon_detach_pipe3_phy` call is commented out in the vendor `utmi_init` but kept in the NAT-040 plan
  (4.05/4.06); the ladder performs it (plan order) and its read-backs are the first thing to look at if L5 stops there.
* **Liveness.** L5 starts with the USBCON `VERSION` read; all-zero/all-ones stops with `NOTALIVE` before the first L5 write.
* **The plan cross-check was too lenient** (found by the mutation run): a `PMUCAL_WRITE` row was satisfied by the ladder's *read* of the
  same register, and a `PMUCAL_READ` row by the *wait* of the same register, because the match only looked at address and mask. `derive.py`
  now matches by the kind the row's type means (READ → RD, WRITE → WRP/WRM, WAIT → WAIT) and by value; the generated plan annotations
  moved accordingly (the generated header is unchanged: only the `plan` lists in `ladder_ops.json`).
* **The L7/L8 wait tests were vacuous** (found by the mutation run): the NAT-041 model polls the engine itself after each host step, so
  `lad_usb_wait` could poll nothing and the tests still passed; and the "accesses scale with the poll count" test passed with zero
  accesses. Fixed with a model that does not poll (`model_set_host(0, …)`) and exact poll counts.
* **SET masks and LOAD addresses were invisible** (found by the mutation run): from a zero register file a wrong mask on a field that is assigned
  `0` changes nothing, and a LOAD from the wrong register reads the same `0`. Two checks that share nothing with the generator were added:
  every SET row is recomputed from the vendor statements by compiling the vendor register headers with `cc` (bit-field layout by the compiler,
  22 rows), and every LOAD/STORE group is required to use one register.
* **Defences that are equivalent mutants** (listed with their reason in `mutate_nat045.py`): the monotonic-rung-start check in
  `lad_selfcheck` (the membership check refuses the same tables, only later), the write-op line in `lad_rung` of the default build (the
  self-check refuses such a table first), the `val & mask` in WRM (every PMUCAL row of the pinned sources has its value inside its mask).
  `lad_selfcheck`'s `LAD_NOPS == 0` is likewise unreachable with the generated table.
* The first draft of several tests mirrored the implementation (a regex over `ladder.c`, a status computed by the test itself). They were
  replaced by behavioural checks with fault injection (`plat_stuck`, `plat_flip`, `plat_flip_from`, `plat_dwc3_overlay`).

## Mutation check

`mutate_nat045.py` breaks one thing at a time in a scratch copy and requires the suite to fail: lines of `ladder.c`/`ladder_usb.c`/
`ladder.h`, lines of `derive.py` (the generator is re-run on the mutated copy), and one field of every row of the generated header.
A mutant that does not build or crashes the generator is `INVALID` (not a kill); a survivor must be justified as equivalent.
The final run is `artifacts/nat-045/mutation-004/summary.json`: 503 mutants (136 C, 61 generator, 306 table fields), 498 killed, 5 equivalent
(each justified in `mutate_nat045.py`), 0 survived, 0 invalid, 0 anchor errors. Earlier runs are not evidence of the final tree: run 002 had 38
survivors and 5 invalid mutants (all addressed above); run 003 left one survivor, a plan READ row satisfied by a WAIT of the same register when
mask and value coincide (`derive-plan-read-row-satisfied-by-a-wait`), for which
`test_a_read_row_whose_mask_and_value_equal_the_waits_is_still_not_carried_by_the_wait` was added; a first attempt at run 004 crashed with
`Disk quota exceeded` in `/tmp` (an unrelated tmpfs quota) and was repeated with `TMPDIR` on the project disk before any result was kept.

## Next

NAT-047 builds the `loader-diag-usbmon` image from this ladder and the NAT-041 engine; NAT-046 (native reset canary) and NAT-043
(first native USB-log run) follow under decision 0019. This task does not run anything on the phone.
