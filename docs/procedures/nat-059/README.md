# NAT-059: XNU C checkpoints 17..21 (after `arm_vm_init`) over the USB log engine (host-test image)

Evidence kind: **host-test**. Nothing in this directory has run on the S24. The image below was built and exercised only in the unicorn-based
simulators of NAT-036 (resume model) and NAT-047 (DWC3 device model + the unmodified NAT-041 collector), in a host build of the derived C file and
in static reads of the XNU payload. A simulated host seeing a simulated device is not hardware evidence, and unicorn is not an Exynos model.

## Why

NAT-058 (decision 0024, native-device) delivered all 22 stop notes of `loader-diag-xnu-ckpt3-usb` to the computer without a camera: the kernel ran to
C checkpoint 16 and was held there. The last checkpoint of that list is the call that precedes `arm_vm_init`; NAT-035/NAT-036 refuse stops after it
because `arm_vm_init` ends with `set_mmu_ttb(*_invalid_ttep & 0xffffffffffff)` and so changes the kernel's `TTBR0_EL1`, which the stub gave back as the
value it measured at assembly checkpoint 5 (`0x9e15ae000`, confirmed on hardware by NAT-058). The owner asked to stop preparing and put the system on the phone:
this task extends the same image to the five checkpoints that follow `arm_vm_init` in `arm_init`, so that the next run shows how far XNU gets after the
virtual memory setup (the first point after which the kernel can map I/O and use the console/platform code).

## What was built

`build.py` is NAT-052's build (NAT-036 + NAT-044 + NAT-047 + the NAT-052 glue; its compile flags, link, payload fix and packaging are used unchanged)
with two differences: the image name `loader-diag-xnu-ckpt4-usb`, and one more patch step, `patch_ckpt59.py`, run over the derived tree after NAT-052's own
last patch. The patch rewrites only the derived `ckpt3.c` and `ckpt3.h` with exact-anchor hunks (each anchor exactly once, all or nothing); the proven stub
assembly `ckpt3_stub.S` is untouched and its assembled hash is pinned equal to the NAT-052 build record by a test.

* the stop list is the 22 NAT-052 stops plus `17,18,19,20,21` (arrivals: 5 assembly + 22 C, ending at checkpoint 21, where the stub holds);
* `nat059_resume_ttbr0`: a stop with an id in 17..21 (`NAT059_POST_VM`) resumes the kernel with `TTBR0 = *_invalid_ttep & 0xffffffffffff`, read by physical
  address after `dc civac` from `_invalid_ttep` (VA `0xfffffff0071ac3e0` in the payload), instead of the stored `kernel_ttbr0`;
* `nat036_check` verifies at install time that the 5 instruction words at the end of `arm_vm_init` (`0xfffffff007433b64`) are the pinned ones; a list that
  contains a post-`arm_vm_init` stop with other words is refused (`NAT059_VMTTB_BAD`);
* `nat059_resume_decision`: if a C resume would give back an implausible `TTBR0` (no table-base bits 12..47, or any of bits 1..11 set; an unreadable
  `_invalid_ttep` reads as zero), the stop holds with mask bit 12 (`NAT036_MASK_BAD_TTBR0`) instead of resuming; the note shows the `TTBR0` given back (`kttbr0=`), so
  the host sees it;
* the note format is unchanged (`CK n= arr= last= x2= x3= mask= sctlr= sp= kttbr0= vbar= setups=`), so NAT-052's decoder is used as is.

## Bug found and fixed by the host tests

The first version of the patch classified "post-`arm_vm_init`" as `checkpoint >= 17`. The `arm_init` checkpoint ids are **not** numerically ordered
(`10,11,30-35,12,40-44,13-16,[arm_vm_init],17..21`), so ids 30..44 were wrongly treated as post-VM and would have been resumed with `_invalid_ttep`. The Host
layer caught it (a regression test over ids 30..44 now exists); the patch uses the range `17 <= id <= 21` (`NAT059_POST_VM`), and the image was rebuilt
(the buggy `build-001`/`package-001` were deleted; `build-002`/`package-002` is the fixed build and `build-003`/`package-003` an identical rebuild, whose record (`build-003/build.json`) the hashes below are copied from).

## Pins

* RECOVERY SHA-256 `60147f1f6190c688b89ea63ac1f56816e977db692eb3864bf2aaa404ea868dd1` (100663296 bytes, `artifacts/nat-059/package-002/loader-diag-xnu-ckpt4-usb/recovery.img`, the package the driver reads; `package-003` holds the identical file,
  19634 4 KiB pages differ from the stock RECOVERY).
* `Image.payload` SHA-256 `3bb6e5d14368ef3627288f44aeff9c00c1e510915395db5988de600402b0af20` (21857888 bytes at offset 2048); loader-only `Image` SHA-256
  `4af99c079e151c446a7a3644788b00492b98910298ac68954c60707f5acc0e1b` (303104 bytes). The payload, ADT and the stub are those of NAT-052 (same ADT size fix).
* Derived `ckpt3.c` `03a5256080571f54607ad5f41c8f9cded905b51888680b373c9d6dc64ece32b7`, `ckpt3.h` `7d2f834d9859771c1c164a3c2c842a4b7abcabb5c096562b4232270d72501600`;
  `patch_ckpt59.py` `e3a31b9293384ded995262d092939720a1c37e7922c11aa22c6565182f8ab333`, `build.py` `ecdf3229c912af4351f7dd7a53a4107482806260de25698af9df1bba053991d9`.
* Reproducible: two builds gave the same hashes (`artifacts/nat-059/build-002` and `build-003`, packages `package-002` and `package-003` with identical RECOVERY/payload).

## What the host tests establish (and what they do not)

* **Derivation**: the hunks apply once each; only `ckpt3.c`/`ckpt3.h` differ from NAT-052's tree; the stub assembles to NAT-052's hash; exact removed lines.
* **Words** (static, against `artifacts/nat-020/build-003/payload.bin`): the pinned words at the end of `arm_vm_init` decode as the call
  `set_mmu_ttb(*_invalid_ttep & 0xffffffffffff)` independently of the patch; `_set_mmu_ttb` is `dsb; msr ttbr0_el1,x0; isb; ret`; there is one `_set_mmu_ttb`
  call and one `_set_tcr` call in `arm_vm_init`; the checkpoint calls in `arm_init` are in the order above and 17..21 come after `arm_vm_init`.
* **Host** (ctypes build of the derived `ckpt3.c`): the list rule, the install check (including ids 30..44), the `TTBR0` given back for each of the 22 stops,
  the holds for implausible or unreadable `_invalid_ttep`, and the old 17-stop list unchanged.
* **Run** (`test_nat059_run.py`, 21 tests): the session driver (NAT-057's, with the pins, the decision glob and the registry preconditions changed) and
  `analyze_nat059.py` (27 note positions, ending at checkpoint 21) on archives written by the real NAT-041 collector from the DWC3 model: PASS only for a
  complete stream, PARTIAL names the last note, EXCEPTION carries `esr/elr/far`, BAD_TTBR0 / BAD_STATE holds are named, a synthetic archive never gets a plain
  verdict, and a stop with the wrong checkpoint value or a `kttbr0` that is wrong for its position is a PARTIAL reason.
* Mutation check (`mutants.py`, 27 mutants of the patch, analyser and driver): run 001 killed 24 and left three survivors, M8, M11 and M13; M11 and M13 were mutants that did not
  change behaviour (an unused Python constant; the numeric value of an enum nobody pins) and were rewritten to mutate the C literal / give a bad `arm_vm_init` the success code; M8
  (`nat036_ckpt_c` shows the stored table instead of the given-back one in the note) pointed at a weak test: `nat036_ckpt_c` sits under the aarch64-only guard and cannot be built
  on the host, so the Derivation layer now checks its exact statements (a source-level guard, not a behavioural test; the analyser's `kttbr0` rule is the behavioural check on
  the real run). Run 002 of those three: killed. Totals and logs: `evidence.json`.
* **Not established on hardware**: what the kernel does between checkpoint 16 and 21 on the S24 (below).

## Limits, disclosed

* The kernel code between checkpoints 16 and 21 has never run on this phone and is **not modelled**: `arm_vm_init`, `patch_low_glo`, `PE_consistent_debug_inherit`,
  `serial_init`, `kernel_startup_initialize_upto`, `kprintf`/`PE_parse_boot_argn`/`PE_create_console`, `PE_init_printf`, `cpu_machine_idle_init`,
  `PE_init_platform`, `ml_map_cpu_pio`, `cpu_timebase_init`, `kptimer_curcpu_up`, `PE_init_cpu`, `fiq_context_init`, the SecureDT lookups, `early_random`.
  The static direct-call closure from those roots is 3000-5900 functions with indirect branches not followed (`artifacts/nat-059/analysis/reach-17-21.json`),
  so no bound on what the kernel touches is claimed.
* After `arm_vm_init` `vm_initialized` is set, so platform code can call `ml_io_map`. The payload's ADT has `arm-io` ranges (`0 -> 0x10000000`, size `0xf0000000`)
  and a `gic` node (`reg` `0x200000/0x10000` and `0x240000/0x140000`, i.e. GICD `0x10200000` and GICR `0x10240000` on this map): kernel code may therefore map and
  read or write interrupt-controller registers (`pe_arm_init_interrupts` and friends). `sweet-ufs` (`0x17100000`) is only used by IOKit, which this run does not
  reach. There is no UART node in the ADT. Nothing here claims that storage is not touched; the claim is that no code path to it was found in the stops 17..21.
* The assumption that nothing else changes the kernel's `TTBR0` between checkpoints 17 and 21 is not proven; the hardware run decides.
* The kernel's vectors are not given to the loader's engine between stops except through the stub's swap; an exception inside the kernel while its vectors are
  installed is reported only by the stub's early-exception path (NAT-052). The 83 s watchdog is the fail-safe (`SEC_UPLOAD` and an automatic restart were seen
  once on 2026-11-11); Download Mode by keys is the fallback.
* The time budget (27 arrivals at about 0.4 s each plus the loader's start) is unchanged from NAT-058: 22 arrivals took about 10 s.

## Commands

* Build: `python3 -I docs/procedures/nat-059/build.py --out artifacts/nat-059/build-NNN --loader-source <copy of artifacts/nat-052/build-003 source>`; package:
  `python3 -I docs/procedures/nat-047/package.py --build artifacts/nat-059/build-NNN --out artifacts/nat-059/package-NNN`.
* Tests: `<venv with unicorn+capstone>/bin/python -W ignore -I docs/procedures/nat-059/test_nat059.py` and `... test_nat059_run.py`, `TMPDIR` on a disk with a few hundred MB
  (the user `/tmp` tmpfs is nearly full on this host; `artifacts/nat-059/tmp` was used).
* Mutants: `... docs/procedures/nat-059/mutants.py --json OUT [--only M5]`.
* Run on the phone (not done): `docs/procedures/nat-059/session_nat059.py --image loader-diag-xnu-ckpt4-usb --out artifacts/nat-060/run-001 --execute`, gated by decision 0025
  (`decision-draft.md`), a native permit citing it and the one-shot marker; analysis `analyze_nat059.py`.

## Next

NAT-060: one native run under decision 0019 (owner confirmation recorded before the launch), restore of the stock RECOVERY and the Android check, then analysis.
