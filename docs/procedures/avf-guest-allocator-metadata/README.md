# Guest allocator metadata preflight

VM-033 independently inspects the immutable VM-008 guest objects. Run this
read-only source/object check with constrained stdlib Python:

```
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s tools/build/avf_guest_allocator_metadata.py --main /home/egor/dev/pet/s24-ios-exynos --output docs/procedures/avf-guest-allocator-metadata/local-runs/preflight-1
```

The tool streams every file hash, checks the frozen guest manifest and compiler
source descriptor, verifies recorded successful compile commands and dependencies,
and parses ARM64 Mach-O sections, symbols and relocations independently. OSData
must have its genuine 192-byte `__DATA_CONST,__kalloc_type` section, six relocations,
and the `S_ATTR_LIVE_SUPPORT` flag. kalloc.c is the section consumer and need not
emit its own allocation record; its object must refer to all four fixed/variable
section boundary symbols.

The primary kalloc.h contract requests `regular, live_support`. Mach-O's public
loader.h defines that attribute as blocks live when they reference live blocks;
it does not mean unconditional retention. kalloc.c consumes start/end symbols and
iterates these records during startup. MakeInc.def enables dead stripping for LTO.
A complete guest link must preserve reachable allocator records, their referenced
name/signature storage, four boundary symbols, and record extents. This preflight
cannot establish that a final linker retained them. Actual final kernel linking,
LTO behavior, boot-time consumption and allocator runtime remain unmeasured.

Controls modify bounded copies of the actual OSData object in this run directory:
a renamed section, cleared live-support flag and removed relocation table must be
rejected. Their bytes remain local and never replace source objects. A fourth
control rejects the historical distinct stock compiler's provenance. Its original
real OSData compile failure, command, diagnostics and hashes are independently
bound as historical evidence; no compiler is executed by this preflight.

Preserve all runs. The program never invokes a compiler, linker, generator or guest.
Compilation requires accepted VM-008 namespace and explicit root resource admission.
Only the integrator may publish MAIN or run common checks under its shared lock.
