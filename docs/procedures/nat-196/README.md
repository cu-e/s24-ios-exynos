# NAT-196: EL2 state left on the PSCI-started cores (native, decision 0080)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-e2p-md1 (NAT-195), one run on 2026-11-14 (reboot 08:56:49Z).
Afterwards stock RECOVERY was restored with a full hash check, and Android was verified:
- `artifacts/nat-196/restore-001/report.json`, from the nat-012 trace;
- nat-013 assess: pass (all six stages);
- `check_android.py`: pass, recovery_hash_match true (09:11:17Z).

The phone reached Download Mode by itself after the run. No button press was needed.

## Result: E-ok on all 9 started cores

All nine started cores (cpu1–cpu9) wrote stage word 0x5EC000E2. Each read eight EL2 registers without writing any, then called
PSCI CPU_OFF. AFFINITY_INFO afterwards was 1 (OFF) on every core, so CPU_OFF was accepted from EL2.

| register | cpu1–3 (A520) | cpu4–8 (A720) | cpu9 (X4) | decoded |
|---|---|---|---|---|
| CurrentEL | 0x8 | 0x8 | 0x8 | EL2 (confirms NAT-153, corrected in NAT-195) |
| HCR_EL2 | 0x0100030080000000 | same | same | RW=1, API=1, APK=1, ATA (bit 56)=1; VM/IMO/FMO/AMO/TGE/E2H/TSC/TWI/TWE = 0 |
| SCTLR_EL2 | 0x30d8099a | 0x30c5083a | 0x30c5099a | M=0, C=0, I=0 (EL2 MMU and caches off), EE=0 |
| MDCR_EL2 | 0x14 | 0x14 | 0x1f | HPMN 20 / 31; TPM/TDE/TDA = 0 |
| VBAR_EL2 | 0x0 | 0x0 | 0x0 | **no EL2 vector table**: any trap to EL2 jumps to PA 0 |
| CNTHCTL_EL2 | 0x3 | 0x3 | 0x3 | EL1PCTEN=1, EL1PCEN=1 |
| CNTVOFF_EL2 | 0x0 | 0x0 | 0x0 | virtual counter = physical counter |
| CPTR_EL2 | 0x32ff | 0x32ff | 0x32ff | TFP=0, TZ=0, TCPAC=0 (FP/SIMD/SVE not trapped) |
| ICC_SRE_EL2 | 0x9 | 0x9 | 0x9 | SRE=1, Enable=1 (EL1 may use the GIC system-register interface) |

The register values are the same within each core type. SCTLR_EL2 and MDCR_EL2 differ between core types, which is expected:
those registers have implementation-defined RES1 bits and a per-core PMU counter count.

### What this means for the EL2→EL1 drop (roadmap S8)

The loader's own `from_el2` (`artifacts/nat-020/build-003/source/shim/e1s-xnu/start.S:28`) already runs on the boot CPU and is
proven by every native XNU run since NAT-022. It writes:
- HCR_EL2 = RW;
- CNTHCTL_EL2 = 3;
- ICC_SRE_EL2 |= 9;
- CPTR_EL2 = 0;
- ELR_EL2/SPSR_EL2 (EL1h, DAIF masked), then `eret`.

Against the measured secondary state:
- **CNTHCTL_EL2, ICC_SRE_EL2 and CNTVOFF_EL2** already have the values the boot CPU runs with. The writes are no-ops.
- **CPTR_EL2** loses only RES1 bits, as on the boot CPU.
- **HCR_EL2** loses API, APK and ATA. The boot CPU runs XNU with them cleared.
- **MDCR_EL2, VBAR_EL2 and SCTLR_EL2** are not touched by the loader on the boot CPU either.

So the same sequence, applied on a secondary before XNU's EL1 code, gives it the boot CPU's configuration. No new register value is
needed. VBAR_EL2 = 0 explains how NAT-153's secondaries failed after MMU-on: they ran XNU's EL1 code while still at EL2, and the
first exception had nowhere to go.

## Boot CPU, beside it (same as scV)

| measure | value |
|---|---|
| display | W-ok, D2-refreshing; iOS S1 (alive) |
| smp | C0-one: cpu1–9 started, none joined (expected: they were sent to CPU_OFF) |
| fbcopy181 | K2, driver copy median 1.99 ms |
| bbd188 | B1, 54.1 ms/frame median (baseline 67.95) |
| top186 | U-sat, cpu0 busy 0.993, backboardd 0.72 |
| cpuclk173 | C2, 960 → 1958.4 MHz |
| touch170 | P1, chip answers 3/3, no coordinate events (nobody touched the screen) |
| watchdog | fed every 10 s for 275 s from 114.4 s; log runs to 383.3 s; Download Mode reached by itself |

`analyze150`'s `early_where` reports "unreadable" for all nine cores. Its parser does not know stage 0x5EC000E2. That is expected,
and e2p196 is the analyser registered for this run.

## Files

- Analysis: `artifacts/nat-196/analysis/` (`e2p196.json`, `verdict.json`, `kernel-text.txt` and the scV analysers); `artifacts/nat-196/analyse.sh`.
- Run: `artifacts/nat-196/run-001`, `artifacts/nat-196/run-001.log`; restore: `artifacts/nat-196/restore-001`.
- Inventory: `devices/local-2026-11-14-nat196.json` (local, untracked).
