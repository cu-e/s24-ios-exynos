# VM-040: lineage-bound genuine kernel collector preparation

REV-037 correction is prepared separately in `worktrees/vm-040-lease-20261106`.
The original physical worktree, source and control capsules remain frozen.
The original19 passing host tests did not detect a pre-spawn lease window or
invalid source predicates in the authored FDT. See `lease-regression-002.md`
and `fdt-regression-003.md` for the prospective focused corrections. A corrected
authored fixture is source-valid host data, not actual QEMU FDT qualification.
The final root-child/consumer-selection follow-up is separately frozen in
`worktrees/vm-040-consumer-20261106`; see `consumer-regression-004.md` and the
leading final-correction section of `handoff.md`. Both earlier physical source
and evidence freezes remain unchanged.

Owner `codex-guest-collector-20261106-eh`, branch
`team/vm-040-eh-20261106`, worktree `worktrees/vm-040-eh-20261106`, base
`d596c07d5bbb1ef8f8bca1107a4bbc0c7db7ac42`.

The current genuine kernel image is absent. The committed descriptor has an
empty `image_admissions` allowlist; both planning and execution refuse before
launch. There is no default spin payload, fake kernel, marker writer, external
admission override, production packager or build command in this collector.
Historical source worktrees, PID1 binaries, shim witnesses and blocked VM-002
remain read-only. This task prepares implementation and host controls, not XNU
execution. No compiler, QEMU or phone is used in its experiment.

The collector reuses accepted VM-026 memory/Mach-O/entry-alignment rules,
VM-027 Apple-tree parser, VM-028 console diagnostics, VM-029 timer/IRQ source
checks, VM-030 source preflight and frozen offline classifier, VM-025 exact
compiled-candidate admission, VM-024 raw mockfs verifier and VM-004 owned-session
sampling/cleanup helper. Exact helper/fixture/source tool hashes are pinned in
[`inputs.json`](../../../fixtures/public/avf-kernel-boot/inputs.json).

The exact VM-022 final execution plan is pinned as a source-supported future
route: raw ARM64 DEVELOPMENT/BCM2837 Mach-O -> genuine `mkpayload.py` XNUP kernel
entry -> the existing matched source-built shim Image as QEMU `-kernel`, with
XNUP as `-initrd`. All thirteen compiled shim source/license hashes must still
match the frozen VM-008 donor. VM-022's plan is not an available linked image;
its missing-input and execution boundaries are retained. The collector does
not produce objects, archives, an image, XNUP or a root filesystem.

Before a future admitted plan can exist, an independently reviewed allowlist
entry must bind an exact image descriptor, independent review and root acceptance
by path, size and SHA256. The descriptor must bind kernel, XNUP, raw ramdisk,
PID1 executable/candidate descriptor, package.json, Linux FDT, layout plan,
source-to-link evidence, independent image qualification and a **new image-bound
paused/cont stop protocol**. Its profile is ARM64/DEVELOPMENT/BCM2837. Caller
booleans cannot substitute for these independently pinned artifacts.

Source-to-link evidence must bind the raw Mach-O, source graph, complete ordered
1080-object map, actual immutable source bytes, original producer objects and
raw compile receipts/dependency files. It must also bind the genuine link argv,
cwd, actual exit and stdout/stderr, all staged/transformed/tail/provider/filelist
and qualification inputs. Independent image review must assess that complete
link closure and transforms, not infer it from a successful command or a header.
The collector rehashes the bound inputs; it cannot replace that review with a
generic linker-success flag. No real complete lineage exists to measure yet.

The XNUP parser compares the embedded kernel and ramdisk extents byte-for-byte
by streaming hashes with their exact admitted files. It admits only kernel,
ramdisk and cmdline entries. The raw mockfs verifier must find the identical
compiled PID1 bytes, /sbin/launchd mapping and padding. Compiled ABI acceptance
is preserved as compiled-only; it is not runtime admission. Mach-O four-byte
entry alignment, file-backed execution, metadata, segment/BSS and source-derived
256MiB RAM/window/relocation/bootargs extents remain mandatory.

The proposed QEMU append string is:

```text
cpus=1 -v serial=3 -enable_kprintf_spam console_quiet=0 disable-uart-irq=1 avf_exit=1
```

This is explicitly not the complete kernel argument vector. VM-026 reconstructs
shim defaults, the XNUP cmdline and FDT append. The collector then validates the
complete combined string, including `debug=0x8` and `rd=md0`, and later requires
exact equality with the shim's single printed boot-args line. Consistent repeated
arguments are retained; conflicting or unsupported values reject. DEVELOPMENT
kprintf needs `-enable_kprintf_spam`; explicit console_quiet0 replaces the shim's
quiet1 default. No argument grants a guest lease.

A future run uses exactly one TCG cortex-a76 CPU, virt/GICv3,256MiB, no network,
storage, display or passthrough, the exact qualified QEMU/shim/payload/FDT files,
`-no-reboot` and `-S`. The **actual final argv retains -S**. Root must grant a
single fresh lease binding owner/task/protocol, collector/image/plan digests,
canonical run directory,256MiB guest/512MiB total owned RSS,60-second deadline
and bounded issued/expires timestamps. Three memory samples >=4GiB with acceptable
pressure precede spawn. The same exact lease and resource floor are checked
throughout the run. Atomic new output-directory creation prevents reuse of that
lease/output by a second invocation.

The deadline begins at spawn and includes paused admission. The collector verifies
the owned Unix QMP socket, typed greeting/replies/IDs and bounded transcript. It
sends stop/query-status, then saves a40-byte header and bounded exact-length
**Linux input FDT** from its source-derived load address. Header/body lengths,
root cell widths,256MiB RAM, HVC, GICv3, PL011, timer PPI27, bootargs and initrd
extents must match before cont. Those bytes are not Apple's serialized tree.
Only a later unique shim tree-complete console checkpoint permits an optional
paused Apple-tree capture at the independently computed address/extent. The
VM-027 parser handles those later bytes; absence before guest shutdown remains
explicitly unmeasured, and a race/failure remains diagnostic evidence.

Stop is checked before each QMP operation and cont, before spawn and between
preparation stages. SIGINT/SIGTERM request Stop. Finite deadlines, bounded files,
QMP frame/total/message budgets and resource limits cause owned cleanup. The
accepted session cleanup policy records each actual signal attempt and result,
then checks the owned session for survivors. It never signals other sessions.
Normal completion captures guest-origin QMP SHUTDOWN separately from host quit,
signals, timeout, panic, reset, firmware refusal and failed admission.

The frozen VM-030 classifier still receives the actual `-S` argv and combined
args and retains its rejection. No legacy descriptor is rewritten or waived.
The new image-bound protocol permits only single-boot observations: repeated
kernel/identity/panic/stop markers or duplicate shutdown events reject. Merely
using first occurrences is not a repeated-boot protocol. Even a complete collected
sequence is `consistent-observations-awaiting-review`, with genuine kernel and
PID1 runtime qualification false. Actual execution acceptance is a separate
future experiment and independent review; controls cannot establish it.

Registered source/host control command, always using a fresh output:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -s \
  fixtures/public/avf-kernel-boot/controls.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-040-eh-20261106/artifacts/avf-kernel-boot/NEW-controls
```

Future CLI shape, currently guaranteed to refuse for absent `current` admission:

```sh
python3 -s tools/run/avf_kernel_boot.py plan --main MAIN --image current \
  --run-dir OWNED-NEW-RUN --out OWNED-NEW-PLAN.json
python3 -s tools/run/avf_kernel_boot.py run --plan OWNED-PLAN.json --lease-id ROOT-ID
```

Planning/execution is never authorized by these examples. Future concrete image
admission and exact plan need independent review, integrator common checks,
root lease and a separately registered actual-guest experiment. This producer
will run no QEMU trial, build, or common checks under VM-040.
