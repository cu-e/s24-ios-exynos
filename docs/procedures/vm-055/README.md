# VM-055: s24vmm --fp-on

With `--fp-on`, s24vmm sets `CPACR_EL1 = 0x300000` (FPEN = 0b11) on the boot vCPU with
`KVM_SET_ONE_REG` before the first `KVM_RUN`. The start event records it as `"fp_on":1`. Without
the option nothing changes.

## Why

XNU's `common_start` enables FP/SIMD with `msr CPACR_EL1, x0` (xnu c54f35ca,
`osfmk/arm64/start.s:762-763`). There is no ISB after it, and nothing synchronizes context before
`arm_init` calls `cpu_data_init`, whose `fmov d0, xzr` is XNU's first FP instruction. The Arm
architecture does not require a direct write to a system register to affect later instructions
before a context synchronization event.

The VM-054 probe `docs/procedures/vm-054/fp_sync_probe.S` measured this in an s24vmm guest on the
S24 (runs `artifacts/vm-054/fp-sync-cpu{0,4,9}`):

- On A520, A720 and X4, an `fmov` right after an unsynchronized FPEN 00→11 write traps with
  ESR 0x1fe00000.
- On A520 and X4 it still traps after about a million ALU instructions.
- With an ISB after the write, it never traps.

The guest's CPACR_EL1 reads 0x300000 throughout, so the stale value is invisible in register dumps.

Firmware leaves FP enabled before an OS starts. Starting the vCPU with FPEN = 0b11 makes XNU's own
write a no-op, so its missing ISB no longer matters.

## Checks

`python3 -I src/vmm/check.py --run check-007 --task vm-055` passes on 368e146:

- `test_vmm` 220 checks and `test_io` 92 checks under ASan+UBSan
- the seqlock test under TSan
- a warning-free static NDK build

The device effect is VM-054's evidence: with `--fp-on` the XNU guest reaches PID 1; without it the
guest hangs as before.

## Limits

- Only the boot vCPU gets this state. KVM resets a vCPU started with PSCI CPU_ON, so an SMP XNU guest
  will hit the same trap on its secondaries.
- Possible fixes for secondaries, none implemented:
  - avfboot's CPU_ON entry sets CPACR_EL1 with an ISB before it jumps to XNU;
  - XNU gets an ISB after the write.
