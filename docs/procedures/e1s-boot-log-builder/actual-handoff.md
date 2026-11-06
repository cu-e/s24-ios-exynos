# STR031 actual host handoff

The ordinary builder now applies the exact RAM, framebuffer and loader-owned log
overlays in order. Its original21 recorded run() vectors are preserved, with only
two log patch check/apply calls added. The genuine ROOT101 invocation completed
all23 builder records, eight target compiles and eight ELF/Image/boot/tar products.
The source-hook harness separately passed eight cases. Source verifier Git queries
and tools' internal subprocesses are additional provenance, not part of that23.

Original STR031BUILD-001 remains recorded FAIL: its final inspector assumed ELF
entry and flat Image header base must both be0. Read-only accepted-old/current
products showed both genuine pipelines have ELF entry2048=_start, while the flat
header begins at0 with B targeting2048. The source/header/linker/native flags were
not changed. ROOT99's earlier Python inspect shadowing failure, all rejected
source proposals and old approvals are also preserved. Controller-P plus frozen
PYTHONSAFEPATH1 isolates the corrected launch; required helper/source imports are
explicitly bound, with no implicit fixture sibling dependency.

The separately preregistered STR031INSPECT-002 ROOT103 run used the exact retained
ROOT101 products. It passed the corrected inspector and all12 original invalid
artifact/vector/source controls without rebuilding or replaying source controls.
The root independently observed normal exit0, no stop reason and zero survivors;
the adapter also recorded zero surviving sessions and no cancellation signals.
Root owns and released the resource lease; no author resource action occurred.

The actual loader log is a writable initialized object of65300bytes at linker
relative extent[134944,200244), aligned16, in merged output .data. Its record fits
before actual payload/_end200704 and is disjoint from normal stack[52944,118480),
exception stack[118480,134864) and empty BSS[200256,200256). ELF/Image bytes,
header image_size, padding, initial magic/zeroed fields/extra terminator agree.
The actual payload_addr ADR at2300 targets200704. One hundred log relocations
were checked against actual object and linked instructions: ten ADRP, five ADD
low12,83LD/ST low12, one relaxed NOP+ADR and one corresponding relaxed ADR.
These numeric addresses are linker offsets, not verified phone physical mappings.

The snapshot inspector binds expected ELF/Image report digests and retained
measured report/object digests to the same immutable captured bytes used for
parsing, controls and result hashes. All17 source-local C/ASM/header/linker/
packager inputs remain pinned, and all36 inspection-plan bindings remained
unchanged across ROOT103. This preserves payload/video/boot_args/start, FDT/UI/
choose_window and legacy2MiB numerical exclusion source behavior. The existing
extent helper's nine accepted STR020 host arithmetic cases are reused unchanged;
no C/sanitizer suite was replayed. No target compiler MD or Apple SDK/runtime
closure is invented; the existing ordinary pipeline emits no MD.

The descriptor and evidence qualify host-built artifact layout/source behavior.
No phone/target execution, kernel payload, physical ownership, validated writable
mapping, early retrieval, cache/reset persistence, recovery, GPU/WiFi/SIM or
private Apple runtime is qualified. Fixed kernel0011/0012 marker writes and the
original probe's physical/MMIO assumptions remain unresolved native gates.
Independent actual review, root integration/common checks and explicit acceptance
precede original-owner completion. No further implementation task is claimed.
