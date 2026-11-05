# VM-029 guest timer and interrupt prerequisites

Owner: `codex-guest-exec-20261106-dk`. Worktree `worktrees/vm-029-20261106`,
branch `team/vm-029-20261106`. Source review and bounded host inspection only.
No compiler, QEMU, guest, phone, MMIO operation or timer interrupt was executed.

The exact selected guest and historical QEMU/shim sources agree on virtual timer
INTID 27. The checked launch declaration deliberately fixes the historical
`virt,gic-version=3`, TCG, Cortex-A76, one CPU and 256 MiB configuration. It is
a declarative prerequisite check, not a full QEMU argument validator or a
permission to launch. Historical shim/synthetic CPU success does not qualify
XNU timer delivery, clock monotonicity, IRQ rearm or console operation.

## Reproduce the source inspection

Run in the task worktree, or in MAIN after integration, with a fresh output:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
python3 -s tools/build/avf_guest_timer_irq.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-timer-irq/NEW-inspection --controls
```

The process reads exact immutable source, configuration and tool inputs. All
hashes stream from disk, including the 19 MiB graph and QEMU executable. Text
witness inputs are capped at 1 MiB each. The inspector has a 256 MiB address
space limit, a 30-second deadline, no child process and current-image
`/proc/self/status` RSS/HWM records. A report is retained on handled failure.
It creates only the requested fresh report directory. It does not regenerate
the namespace, run source scripts or touch MAIN state.

The fixture [inputs.json](../../../fixtures/public/avf-guest-timer-irq/inputs.json)
binds 19 inputs by size and SHA256. The guest source is the frozen VM-008
`prepare-2/source/xnu` tree. Its graph is bound to
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
Four actual graph rows bind GIC, machine routines, ARM initialization and rtclock
source plus genuine configuration hashes and the BCM2837 compiler selection.
This is graph membership and source inspection; the inspector never compiles
those rows or treats an object manifest as an object build.

Source ancestry remains Scion
`a6f4bc38aa244359cd365c976244a88c9d6b3304`, public XNU
`c54f35ca767986246321eb901baf8f5ff7923f6a` and QEMU
`698104725efad4b29079d857dfdebbd804e34c99`. The exact source composition and
QEMU archive acquisition qualifications remain in the existing VM-007/VM-004
handoffs. Their source/license bytes remain beside the original artifacts;
this task copies no upstream implementation, SDK or binary into Git.

## Source trace and explicit constraints

| Boundary | Exact source witness | Result and required constraint |
| --- | --- | --- |
| Board | `pexpert/pexpert/arm64/BCM2837.h`, board selector and graph recipes | `ARM_ARCH_TIMER`, `GENERIC_GIC_V3_IRQ=1`; BCM2837 selected in genuine recipes. Lexical inspection does not replace preprocessing. |
| Controller | QEMU `hw/arm/virt.c` | GICv3 distributor `0x08000000+0x10000`, redistributor window `0x080a0000+0x00f60000`. One CPU needs a matching MPIDR redistributor with a `0x20000` frame. |
| DT conversion | Shim `avf/shim/avfboot.c` | Reads GICv3 FDT registers and third timer triple; PPI number becomes `16+num`. Emits Apple `/arm-io/gic` four-u64 `reg` offsets, `virtual-timer-intid` and CPU frequency from `CNTFRQ_EL0`. Raw FDT is insufficient for the guest's `SecureDT` lookup. |
| Physical mapping | Shim and guest `osfmk/arm64/gic_v3_irq.c` | Shim subtracts `io_base=0x100`; guest adds `pe_arm_get_soc_base_phys()` and maps distributor/redistributor. Require the converted DT and unchanged ranges convention. |
| Virtual timer | Guest GIC and QEMU `include/hw/arm/bsa.h` / `virt.c` | Both use INTID 27. QEMU wires `GTIMER_VIRT` to `ARCH_TIMER_VIRT_IRQ`. Guest ignores emitted `virtual-timer-intid`; reject any differing declaration. |
| Interrupt range | Guest GIC and QEMU `NUM_IRQS=256` | Guest accepts SPI 32..1019, 48 simultaneous slots. QEMU has 32 internal + 256 external interrupts, so the checked intersection is SPI 32..287. Empty required-SPI declaration makes no peripheral claim. |
| Initialization | `osfmk/arm/arm_init.c`, `pexpert/arm/pe_identify_machine.c`, `pe_fiq.c` | `PE_init_cpu()` calls `pe_init_fiq()` and generic GIC setup before `fiq_context_init(TRUE)` enables the virtual timer. GIC maps MMIO, enables ICC system registers, finds/wakes redistributor, enables Group 1 PPI, distributor and CPU interface, then installs IRQ handler. |
| Clock | `machine_routines.c`, `rtclock.c`, `pe_identify_machine.c` | Virtual timer uses `CNTV_CTL_EL0` / `CNTV_TVAL_EL0`; counter reads `CNTVCT_EL0`. Guest consumes CPU `timebase-frequency`; shim emits it from actual CNTFRQ. This run reads no guest register and asserts no numerical frequency. |
| IRQ dispatch | `gic_v3_irq.c` | Reads `ICC_IAR1_EL1`, routes INTID 27 to `rtclock_intr(TRUE)`, ends through `ICC_EOIR1_EL1`; unknown IRQs are masked/counted. No observed IRQ delivery or EOI ordering claim. |

The fixture [launch.json](../../../fixtures/public/avf-guest-timer-irq/launch.json)
is intentionally narrow. A different CPU, accelerator, CPU count, timer INTID,
MMIO window or DT representation requires new qualification. The current
inspector rejects eight actual mutated declarations, including GICv2, KVM,
multiple CPUs, wrong timer, nonexistent SPI, undersized range and raw FDT.

The generic source waits for redistributor wake and distributor write completion
without a source timeout. There is no evidence that either wait completes for
this actual XNU image. Future runtime evidence must use a separately accepted
complete kernel and a finite owned supervisor, record the exact QEMU argv,
source/image/tool identities, serial milestones and actual stop/exit behavior,
and preserve timeout/failure logs. A timer enable log alone cannot establish
interrupt delivery or deadline rearm.

## Handoff and acceptance boundary

Source/light inspection is authorized by VM-029. VM-008 independent namespace
review and integrator acceptance remain separate prerequisites for compiler
use. A real build needs root's exclusive resource lease and stable memory
admission; any QEMU start needs root's explicit single-guest lease. No lease is
requested or consumed by this inspector. Integrators alone publish MAIN and run
common checks under `state/.integration.lock`; this worker runs no `make check`.

The original owner retains the claim until independent review, integrator
acceptance and fresh MAIN common checks. The next action is review of the
scoped commit and bound host evidence. The runtime timer/IRQ gate remains open.

Implementation commit: `b4ae11ed2db7d248e5c8d594d3d5b6a8d3a163d1`.
The commit-bound suite at
`worktrees/vm-029-20261106/artifacts/avf-guest-timer-irq/final-b4ae11e/`
passed the genuine inspection and eight launch rejection controls. Two real CLI
rejections retain exit 2 reports: changed input identity and a deliberately
re-pinned QEMU timer definition of 30 against guest 27. These changed inputs
are test-local copies; original sources remain untouched. The successful
inspector's current-image `/proc` VmHWM was 73,351,168 bytes. It completed in
under one second with no child, compiler or guest. See [evidence.json](evidence.json)
for commands, actual exits, tools, exact input/output hashes, prior runs and
limitations. The CLI control driver executes three finite inspector processes
sequentially; the inspector itself starts none.
