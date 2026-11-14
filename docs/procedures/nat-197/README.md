# NAT-197: secondary EL2→EL1 drop (roadmap S8, host-test)

**Evidence kind:** host-test. Nothing here ran on the phone. The native run is NAT-198.

## Why

- NAT-153: PSCI `CPU_ON` starts cpu1–cpu9 at EL2. XNU's start path programs only EL1 registers. The cores reach MMU-on and never
  join.
- NAT-196 (native, E-ok): each started core finds HCR_EL2 RW|API|APK|ATA, the EL2 MMU off, VBAR_EL2 = 0, CNTHCTL_EL2 = 3,
  CNTVOFF_EL2 = 0, CPTR_EL2 = 0x32ff and ICC_SRE_EL2 = 9.
- The boot loader's own `from_el2` (`artifacts/nat-020/build-003/source/shim/e1s-xnu/start.S:28`) has taken the boot CPU from EL2
  to EL1 in every native run since NAT-022. Applied to a secondary, it gives that core the boot CPU's configuration. Only HCR_EL2 and
  CPTR_EL2 change; the other writes rewrite values the firmware already left.

The values come from the project's own phone-proven code. This piece does not use, read or reproduce the Linux `init_el2` source
that roadmap S6 / NAT-154 was about; S6 stays stopped.

## What changes against e2p (NAT-195), and so against scV

`osfmk/start.o` only (`start.patch`, applied to the original `start.s`; it is NAT-195's patch plus this):

1. **In place.** `reset_vector`'s second instruction, `mrs x12, SCTLR_EL1` (NAT-150's), becomes `b Lnat197_drop`. It is the same
   size, so no instruction moves.
2. **Out of line,** in the reset-vector page after NAT-152's mark blocks (which had about 2 KiB of slack there):

   ```
   Lnat197_drop:  cmp x11, #0x8 ; b.ne Lnat197_el1          // at EL1 already: only come back
                  HCR_EL2 = 1<<31 ; CNTHCTL_EL2 = 3 ; ICC_SRE_EL2 |= 9 ; CPTR_EL2 = 0
                  ELR_EL2 = Lnat197_el1 ; SPSR_EL2 = 0x3c5 ; eret   // EL1h, DAIF masked
   Lnat197_el1:   x11 |= CurrentEL << 8                     // 0x408: came at EL2, now EL1
                  mrs x12, SCTLR_EL1 ; b Lnat197_back       // the moved instruction, then reset_vector+8
   ```

   The sequence equals the loader's instruction for instruction. Only the scratch registers (x1/x2 → x9/x10) and the label differ,
   and the loader's own `mov x20, #4` marker is left out.
3. **Fallback.** NAT-195's probe stays at mark 4. A core that is somehow still at EL2 there records its EL2 state (stage word
   0x5EC000E2) and calls PSCI CPU_OFF, as in NAT-196.

The boot CPU never takes `reset_vector`. It comes in through `_start` → `start_first_cpu`. The command line is scV's with the tag
`nat_attempt=NAT197-e21` (254 bytes).

## Host checks

All on 2026-11-14:

- **`test_nat197.py`: 9 tests, OK.**
  - The patch is NAT-195's plus the drop. The only instruction moved is `mrs x12`.
  - The block equals the loader's `from_el2`, parsed from `start.S`.
  - The block's system-register writes are exactly HCR_EL2, CNTHCTL_EL2, ICC_SRE_EL2, CPTR_EL2, ELR_EL2 and SPSR_EL2. It has no
    store, no smc and no hvc.
  - In the linked kernel:
    - segments and `nm -n` equal scV's (NAT-185);
    - `_reset_vector+4` branches into the block in the same page;
    - the `b.ne` target, the `adr` target and the eret landing are the same;
    - the way back is to `_reset_vector+8`;
    - the rest of the reset vector is byte-for-byte scV's.
  - The analyser: real NAT-196 and NAT-153 logs give S0-none (E2-probe / E6-mmu-on). Synthetic all / some / fault / panic lines.
  - The session derivation is current, and the image hashes match.
- **Patch mutants.** SPSR 0x3c5→0x3c9, CNTHCTL 3→7, `CPTR_EL2, xzr`→`x9` and `HCR_EL2, x9`→`x10` are each killed by the tests.
- **Loader sites.** `check_loader_sites.py` rc 0 (in `build.json` `nat152_changes`).

## Image

`loader-diag-xnu-e21-md1`:
- RECOVERY `artifacts/nat-197/package-001/loader-diag-xnu-e21-md1/recovery.img`, SHA-256
  52a8b24da5124c55b5813bcfc1869b28ff0826c4c5cfa9c78b5595c9a549e110;
- payload b579d77ffda311e326f747d5a315d2d4652a0222ceb957e0dbdeccec2f325b50;
- kernel no-storage 0da06b549569d442f36f2431d27014f14d783a1099e4f545b12453ed10d9b8d3.

Session driver `session_nat198.py` comes from NAT-196's through `derive198.py`. Only the image, the hashes, the package, the
decision glob, the marker and the precondition list change.

```
python3 -c 'import json,subprocess,sys;a=json.load(open("docs/procedures/nat-197/rebuild-args.json"));sys.exit(subprocess.run([sys.executable,"-B","docs/procedures/krn-044/rebuild.py",*a]).returncode)'
python3 -B docs/procedures/nat-197/build.py --out artifacts/nat-197/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-197/build-001 --out artifacts/nat-197/package-001
python3 -B docs/procedures/nat-197/derive198.py
python3 -B docs/procedures/nat-197/test_nat197.py
```

## Criteria registered for NAT-198 (before the run)

`smp198.py` on the kernel text. The first match wins:

| verdict | condition |
|---|---|
| S-none | no `GenericARMPE: N of M processors are running` line: inconclusive |
| S-panic | a `panic(cpu ...)` / `Debugger called` line |
| S2-all | running 10, no failure line |
| S1-some | running > 1 |
| S0-none | running 1 |

For each core that did not join, the report gives:
- where it stopped (E1–E6, or E2-probe = still at EL2);
- its entry EL and its EL after the drop (0x408);
- any fault (ESR class, ELR/LR as kernel addresses).

Reported beside it:
- the stop path at the timed return (`did not stop` notes);
- the boot CPU's scV measures: display verdicts, fbcopy181, bbd188, top186, cpuclk173, touch170.

None of the scV analysers is per-CPU. A frame-rate change is reported as measured, not attributed.

**What S2/S1 would and would not establish.** It would establish that XNU's scheduler counts the cores as running. It would not
establish:
- correct IPIs and timers under load;
- correct cluster topology;
- any frame-rate gain.

Those are S10–S12 (`docs/plans/smp-gpu-roadmap-2026-11-14.md`).
