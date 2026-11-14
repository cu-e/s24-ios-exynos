# NAT-195: e2p, a read-only probe of the EL2 state on started cores (host)

**Evidence kind:** host-test. NAT-196 is the native run (decision 0080). This is roadmap piece S7
(`docs/plans/smp-gpu-roadmap-2026-11-14.md`).

## Why

NAT-153 showed that the cores PSCI `CPU_ON` starts enter at EL2 (CurrentEL 0x8). XNU programs only EL1 there, so they never reach
`arm_init_cpu`.

Before a core can be moved to EL1, we need to know what the firmware leaves in EL2: traps, stage-2 translation, timer access, GIC
system-register access. This image only reads that state.

**Correction to NAT-153's README.** It says the boot CPU "came to the loader at EL1 (S-Boot's handoff)". That is not so:
- The loader's logged `EL=0x1` is written after its own `start.S` `from_el2` `eret` (`mov x20, #4 /* loader_main's EL marker: EL1 */`).
- NAT-022's entry canary saw **EL2** at the loader's first instruction (ENTRY `0x8900`, two boots).

So S-Boot enters at EL2, and the loader drops itself to EL1.

## What e2p is

e2p is scV (NAT-185, the native-resolution reference) with `osfmk/start.o` rebuilt from `start.patch`. That patch is NAT-152's, plus one
block in the out-of-line mark-4 code (`Lpsci_smp_mark4`). Mark 4 is the last point the NAT-153 cores reached with the MMU off.

A started core that finds `CurrentEL == 0x8`:
1. reads `HCR_EL2`, `SCTLR_EL2`, `MDCR_EL2`, `VBAR_EL2`, `CNTHCTL_EL2`, `CNTVOFF_EL2`, `CPTR_EL2` and `ICC_SRE_EL2` (`mrs` only);
2. stores them in its own early-mark slots 3–6 with NAT-152's mark macro;
3. sets the stage word to `0x5EC000E2`;
4. calls PSCI `CPU_OFF` (0x84000002, the call `psci_smp.c` already uses), so it ends switched off, like the NAT-153 cores;
5. falls into a `wfe` loop only if `CPU_OFF` returns.

A core at EL1 goes on as before. **No EL2 register is written.**

The boot CPU's existing `psci: cpu N early marks:` line prints slots 1–6, so `psci_smp.c` is unchanged. The block sits in the slack
between `__start` (0x…b570) and the page-aligned `_LowExceptionVectorBase` (0x…c000).

## Host checks

`python3 -B docs/procedures/nat-195/test_nat195.py`: 6 OK.
- **Patch.** It is a superset of NAT-152's, with no removed line. Counted as a multiset, the added code uses only `mrs`, `cmp`, `b.ne`,
  the mark macro, `ubfx`/`adrp`/`add`/`movz`/`movk`, one `str` to the mark slot, `dc cvac`, `dsb`, one `smc` (CPU_OFF), `wfe` and `b`.
  **No `msr`.** A mutant that adds `msr HCR_EL2, x11` fails the test.
- **Kernel.** `artifacts/nat-195/kernel-001`, no-storage `ac5575501d10446ba41c62b1c97dac34613fe62d5490796d46df60db62fdd14b`, 0 undefined.
  - Every segment size and the complete `nm -n` list equal scV's.
  - The byte differences are the LC_UUID, the probe block, the two `cbnz` branches in `common_start` to marks 5/6, and LINKEDIT.
  - Disassembly of 0x…b570–0x…c000: no `msr`, one `smc`, one `wfe`, and all eight EL2 `mrs`.
- **Image.** `loader-diag-xnu-e2p-md1`: loader sites rc 0 / ok / bad 0. The command line is scV's with the tag `nat_attempt=NAT195-e2p`
  (254 B).
- **Package.** RECOVERY `ef99af4dabd107a96361b08a6efd6e1933b99ceeddd16899052d921b20e7366d`, payload
  `b736cb088ac99b571ea21bee7608b9b239bc44fa8c8dfbdbe90474249ba9d8d1`, loader Image `94712a03…`.
- **Session.** `session_nat196.py` (`3655d168…`), derived by counted replacement (`derive196.py --check`).
- **Analyser.** `e2p196.py` gives E-noprobe on NAT-153's real log (9 cores, all entered at EL2). On synthetic lines it gives E-ok,
  E-partial and E-none, and decodes the fields.

## Registered verdicts for NAT-196 (`e2p196.py`)

| verdict | condition |
|---|---|
| E-none | no early-marks line: inconclusive |
| E-noprobe | no core has stage word 0x5EC000E2 |
| E-partial | some started cores have it |
| E-ok | every started core has it |

With E-ok/E-partial, the analyser reports for each core:
- the eight registers and their decoded fields: HCR RW/TGE/E2H/VM/IMO/FMO/TSC/TWI/TWE, SCTLR_EL2 M/C/I, CNTHCTL EL1PCTEN/EL1PCEN,
  CPTR TFP/TZ/TCPAC, ICC_SRE SRE/Enable;
- whether all cores show the same state;
- which registers the loader's own `from_el2` sequence would change.

Also reported:
- AFFINITY_INFO after CPU_OFF (expected 1);
- the boot CPU's normal run against scV: home screen, K, touch, top186, the timed return.

## What follows

E-ok gives the facts for roadmap piece S8. S8 runs the loader's own EL2→EL1 sequence on a started core and `eret`s to EL1 at the
reset vector. It also shows whether that sequence needs anything more for the secondaries, for example `CNTVOFF_EL2`, `VBAR_EL2` or
`MDCR_EL2` values the boot CPU never saw.
