# VM-026: source-derived AVF boot memory preflight

Owner: `codex-guest-exec-20261106-dh`. Worktree:
`worktrees/vm-026-20261106`, branch `team/vm-026-20261106`.

The tool validates the pinned source contract and inspects a supplied XNUP
payload without compiling or running it. Source preparation and owned parser
controls pass. A genuine final guest image, its actual FDT and kernel runtime
memory demand remain unmeasured. **256 MiB is not qualified for XNU boot.**

## Exact source contract

`fixtures/public/avf-guest-boot-memory/source-pins.json` binds four public Scion
files by canonical Git blob SHA1 and SHA256 at commit
`a6f4bc38aa244359cd365c976244a88c9d6b3304`. Guarded local Git reads disable lazy
fetch and optional locks; missing objects fail. Five selected VM-008 prepared
XNU files are matched both to their frozen SHA256 and the exact
`prepare-2/prepared-component.json` manifest. Public XNU origin is
`c54f35ca767986246321eb901baf8f5ff7923f6a`; the prepared bytes include the genuine
Scion modifications, rather than claiming those bytes are the public originals.
The existing source-built AVF Image and build report are hash-bound, including
its matching C/start/linker source identities. No E1S object/archive is reused.

The selected source is read from the immutable VM-008 `prepare-2/source/xnu`
tree. The namespace still requires independent VM-008 acceptance before any
compilation. This preflight does not regenerate headers or alter that tree.

| Source | Traced behavior |
| --- | --- |
| Scion `avf/shim/start.S`, `avfboot.ld` | MMU off, x0 physical FDT; Linux Image size includes BSS and 64 KiB stack. The qualified Image declares `0x1c000` bytes, not its shorter on-disk length. |
| Scion `avf/shim/avfboot.c` | First RAM interval; 32 MiB aligned physical window; virtual base `0xfffffff004000000`; first image segment at least 48 MiB above it; 6 GiB maximum window. |
| Same shim, layout and copy stages | Panic log reserves 512 KiB; usable end rounds down to 32 MiB. Kernel extent uses segment **vmsize**, including BSS and holes. Ramdisk rounds to 16 KiB; Apple DT capacity is 64 KiB; bootargs reserves 16 KiB. At least 64 MiB must remain after topOfKernelData. |
| Same shim, payload move | An input payload intersecting destination kernel/data is moved to the aligned top of the window before copying. Preflight checks rounded eight-byte copy bounds and the backward-copy direction. FDT is consumed before destination writes, so a later destination/FDT overlap is intentional. |
| Prepared `pexpert/pexpert/arm64/boot.h` | ARM64 LP64 declaration layout matches the shim: 736-byte boot_args, commandLine offset 108 and capacity 608. A declaration-based calculation compares every field, without a compiler. |
| Prepared `osfmk/arm64/start.s` | `start_first_cpu` preserves physical x0 as x20, reads BA_VIRT_BASE/BA_PHYS_BASE/BA_MEM_SIZE, builds bootstrap page tables and installs TTBRs. This source trace does not prove executed MMU mappings. |
| Prepared `osfmk/arm64/arm_vm_init.c` | gVirtBase/gPhysBase come from bootargs, page-rounded gPhysSize derives from memSize, avail_start starts at topOfKernelData; later physmap placement and allocation are runtime work. |
| Prepared `osfmk/kern/kalloc.c`, `kalloc.h` | Fixed/variable metadata uses __kalloc_type / __kalloc_var sections and is parsed during startup. Image inspection preserves their section extents; it does not establish metadata ABI or allocator success. |

The Mach-O parser reads bounded headers, commands and sections directly from the
kernel XNUP entry. It checks ARM64 executable identity, command/section/file/VM
extents, arithmetic overflow, nonoverlapping segments, file-backed executable
LC_UNIXTHREAD entry, section containment/displacement and nonzero file-backed
__kalloc_type. It reports __kalloc_var if present. A missing variable section is
not declared ABI-correct. Zero-fill tails are counted in RAM sizing.

Command-line construction follows the shim's defaults for debug, serial, CPUs,
console_quiet and ramdisk root, then payload cmdline and declared FDT bootargs.
Preflight rejects truncation. This console-only plan rejects shared-memory
scfb/sccam/scgpu/scsnd carveouts; those require their own source-derived window
calculation. The host plan is explicit input, not a claim that a runtime FDT was
observed. Its initial RAM/shim/FDT/payload intervals must fit and be disjoint.

## Use and limits

Run source checks and parser controls with fresh task-local output:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  tools/build/avf_guest_boot_memory.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --controls --out artifacts/avf-guest-boot-memory/NEW-controls
```

Later, after the genuine image exists, give its exact XNUP payload and an
address/bootargs plan based on the selected QEMU load configuration:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  tools/build/avf_guest_boot_memory.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --payload /absolute/path/to/owned-genuine-payload.bin \
  --layout /absolute/path/to/actual-console-plan.json \
  --out artifacts/avf-guest-boot-memory/NEW-image
```

The example plan is based on the previous synthetic 256 MiB QEMU handoff's
addresses; its FDT capacity is a declaration, not a measured final-kernel FDT.
Replace it with actual loader inputs. The declared shim size must match the
hash-qualified Image header including BSS/stack. Optional MMIO/shared-memory
carveouts are deliberately rejected. No memory size is selected automatically.

Every run writes evidence.json with exact commands/exits/times, source/tool/input
hashes and current-process `/proc/self/status` VmHWM/VmRSS. The tool imposes a
256 MiB address-space cap inherited by finite 15-second Git readers. It only
creates fresh children of its own `artifacts/avf-guest-boot-memory` directory.
It streams large payload hashes and never reads a complete kernel/ramdisk into
memory. Only the small, explicitly synthetic parser-control fixture uses whole
byte buffers. Reported HWM is the Python process measurement, not an aggregate
child-session or kernel-runtime peak.

Controls are owned format/layout fixtures, never XNU execution evidence. No
compiler, linker, generator, QEMU, SDK, native artifact, phone or MMIO operation
is performed. Main publication/common checks belong to the integrator under
`state/.integration.lock`. Completion requires independent review and acceptance.
