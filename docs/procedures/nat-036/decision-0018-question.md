# Draft question for decision 0018: one native run of `loader-diag-xnu-ckpt3` (NOT requested)

Status: **draft text, not a decision and not a request.** Decision 0018 does not exist. Per AGENTS.md and decision 0002 each native
image needs its own owner decision; "decide yourself" and standing autonomy name no image. This text is to be asked (in Russian, with
the choice labels below) only after (a) the NAT-036 tests and build records are committed, and (b) a session driver for this image
exists, gated on the decision file like `session_xnu_ckpt2.py` (a separate host task, NAT-037; not part of NAT-036). Hashes below are
those of the committed-tree builds; they must be re-checked against `artifacts/nat-036/build-001-final` before asking.

## Reason for the image

Run 009 (decision 0017) was the first C-level execution of XNU on the S24: the kernel's `arm_init`, `cpu_data_init` and
`PE_init_platform` ran to C checkpoint 11 and every measured value except SCTLR bits 5/7 equalled the model. The stub held there
(final, not resumable). NAT-035 specified the resume from a C stop in the model and found that the loader as built wrote a boot-CPU
`reg` the kernel's `cpu_init` rejects (`MPIDR` bit 31 not masked). NAT-036 built both: the loader fix and a resumable C stub with a
selectable stop list. This image is the first that lets the kernel continue past a C checkpoint on the phone.

## What the image does

* The loader, checkpoints 1-4 and the checkpoint-5 resume are those of run 009 (same code, three `loader.c` hunks: the ADT boot-CPU
  `reg` is now `MPIDR & 0xffff`, the include and the install call).
* At each C checkpoint of the stop list the stub (MMU switched off first) clears `loader_return_entered`, stores the next stop into
  `slot[2]` (both with `dc civac` before and after), restores the kernel's registers, SP and SCTLR, puts the kernel's own `TTBR0`
  (captured at checkpoint 5, validated) back through the kernel's `_set_mmu_ttb`, and returns into the kernel through
  `loader_jump`'s early-return epilogue.
* The stop list of this image: **11, 30, 35, 12, 44, 13, 14, 15, 16** (9 C stops, 14 arrivals with 1-5). The kernel passes the other
  checkpoints between them without stopping. At checkpoint 16 the stub holds with the final report. Stops after 16 are refused by the
  installer (the kernel's `TTBR0` changes in `arm_vm_init`).
* The report is one frame per pass (kind 13: arrivals count and last checkpoint), and at the hold the values the run is about come
  first: kernel `SP`, the kernel's `TTBR0`, `x1`, `x0`, then SCTLR, TTBR1, VBAR, TCR.

Not done by this image: anything after C checkpoint 16, no GPU, no log transport (still camera), no retry.

## Scope (exactly one image)

NAT-022 `loader-diag-xnu-ckpt3` built with `--stops 11,30,35,12,44,13,14,15,16`:

* loader `Image` SHA-256 `6072f8e4b0215e195d5c8e5ad29f6ecdd28d41277d3dbf2e9c6ce354404ad0e0`
* `Image.payload` SHA-256 `0e556d94b9921ba4cdc426d89e613dbd4e0c694391c220c9429958aae631911a` (`artifacts/nat-036/build-001/...`)
* RECOVERY image SHA-256 `c61165cb0264388098705deea0421e12d77f612791c3b2d579e46bf40abd4f0b` (`artifacts/nat-036/package-001/`, payload
  verbatim at offset 2048, 19634 pages differ from stock)
* source commit `@@COMMIT@@`; evidence `docs/procedures/nat-036/evidence.json`

The 17-stop alternative (every C checkpoint of `arm_init` up to 16) was also built: `Image` `d2b97542…`, payload `da372479…`, RECOVERY
`1654834b…` (`package-002-17stop`). It is **not** proposed: its report ends 5.5 s before the watchdog.

Sequence, as for runs 008-009: full-hash write to RECOVERY (`/dev/block/sda18`) only, full readback, one `adb reboot recovery`,
owner-operated camera recording (about 2 minutes), then restore of the pinned stock RECOVERY (`96620b8b…babf67`; through the driver if
Android returns, otherwise Download Mode and one NAT-013 session with the pyusb venv python on a device whose `iProduct` is
"SAMSUNG USB").

## Expected on screen

Stage markers to `PRE_JUMP` (`0x40`) at about 20-25 s; the five assembly passes of run 009 (one frame each now); then one pass frame
per C stop (arrivals 6-13, last 11, 30, 35, 12, 44, 13, 14, 15); the passes end at about **45 s**; then the held report at checkpoint 16:
REGS `0x0210` (`x2 = 2`, `x3 = 16`), mask `0x203e` (assembly bits 1-5 and bit 13 FINAL), arrivals 14, list length 9. Model values for
the held report (the phone's will differ where noted): `x0` = `0x9e1f90a00` (the loader log; same as run 009), `x1` = 0, kernel
`TTBR0` model `0x9e15ae000` (the phone measures it), `SP` model `0xfffffff00805fef0`, SCTLR `0x3454599d` expected (model
`…593d`), TTBR1 `0x9e15af000`, VBAR low 16 bits `0x7000`, TCR low 32 bits `0xa51a251a`. The first held values are on screen by about 67 s,
SCTLR/TTBR1/VBAR/TCR by about 69 s, the display ends at about 83 s.

Other outcomes, none a failure of the phone and none retried: a pass frame whose last checkpoint is earlier than 16 and then nothing
(the kernel did not reach the next stop: hang or fault without a report: inconclusive); the held report at an earlier stop with mask
bit 12 or 14 (the stub refused the state: nothing was resumed there); mask bit 8 (the kernel's early-exception report: ESR/ELR/FAR);
`FAIL` (the installer refused: no jump).

## Device access granted (and nothing else)

As in decision 0017 (DECON0 `0x19100000` reads and the two kick writes, the framebuffer `0xFA200000`, PMU INFORM `0xbc`, the watchdog
`0x10040000` armed for 83 s, GIC initialisation, the loader's RAM work). Changed by this decision and nothing else: the kernel's code
runs on the phone past C checkpoint 11 through the 9-stop list up to checkpoint 16, resumed by the loader's stub eight times (11 -> 30
-> 35 -> 12 -> 44 -> 13 -> 14 -> 15 -> 16); each resume writes one byte (`loader_return_entered`) and one 8-byte slot word in the kernel
copy, each with cache maintenance, and writes the kernel's own `TTBR0` (the value it had) back with `msr ttbr0_el1` through `_set_mmu_ttb`.
In the model this path touches EL1 system registers, the TLB (`tlbi vmalle1` in the stub), caches and RAM inside the loader's window
only, with no MMIO. No storage device and no partition other than RECOVERY is written.

## Not granted

Anything after checkpoint 16, any other stop list or image (the 17-stop build included), retries or a second run, any other partition,
any reset/data prompt answer, any other MMIO, GPU bring-up, kexec. Each needs a new decision. The mandatory boundary of decision 0002
is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Host evidence only (NAT-030/033/035 model, NAT-036 tests: the compiled stub resumes the kernel through the 9-stop list in the model
  and the end state equals an uninterrupted run with every register the stub does not restore overwritten and tainted; 81 mutants of the
  stub, the decision code and the report were killed). The model has no caches, TLB, barriers, exceptions, timers or devices: the stub's
  `dc civac` order, `tlbi`, `dsb`, `isb` sequence is checked only as text (their removal changes nothing in the model).
* **Never run on hardware: the C tail.** Run 009 proved the prologue, the MMU-off stores and the assembly resume. The tail adds turning the
  MMU on with `loader_jump`'s private table, a branch to a kernel virtual address and the kernel's own `_set_mmu_ttb`. A stale TLB entry,
  a cache line for `slot[2]` or the flag, or the SCTLR value restored (the hardware's bits 5/7 differ from the model) could make the
  resume fail or the kernel diverge; the first consequence would be a hang or a fault, most likely without a report.
* **The panic path is still not analysed** (`PE_panic_hook`, `loader_return`, `psci_smp_stop_others`, `redwood_*_quiesce`) and may write
  device registers. After the ADT fix the model passes `cpu_init`; the real ID registers, MPIDR, counter and timers are assumed in the
  model (`Assumed.assumed`), and a different value could reach a panic. This is the hazard disclosed in decision 0017, now with eight
  more kernel steps before the hold.
* DAIF is not restored by any primitive (all masked at every stop in the model).
* The kernel's own `TTBR0` is a model value until the phone reports it; the stub validates its shape (a table base) before use.
* A pass frame says the kernel's code ran up to that checkpoint; it does not say XNU boots.
* If the kernel hangs or faults without a report, the screen goes dark on the last marker, the 83 s watchdog fires, Download Mode and one
  NAT-013 restore session may be needed, as after runs 1-8. A run without readable markers is inconclusive.

## Choices to offer (Russian, as in 0016-0017)

* "Да, один запуск loader-diag-xnu-ckpt3 (Recommended)" — exactly the image above.
* "Нет, сначала доработать на хосте" — nothing is run.
