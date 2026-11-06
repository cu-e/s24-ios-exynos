# VM-048 bounded allocator retention controls

Owner codex-guest-allocator-witness-20261106-fc. Worktree vm-048-20261106,
base723df34de5a26861904b5bdb8a1922021e35e437. Reserved only the new tool,
fixtures/public/avf-allocator-retention and this procedure directory.

Register VM048RETENTION-001 before the first control run. Run constrained Python
`LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s fixtures/public/avf-allocator-retention/check.py --main /home/egor/dev/pet/s24-ios-exynos --out docs/procedures/avf-allocator-retention/runs/controls-001`.
The checker imports only exact pinned CU snapshot API source0631a7d8 and the new
owned module; no producer corpus/tool execution. Deadline90s, minimum4GiB host
available, current image HWM256MiB, small genuine object copies, streamed hashes.

Verify selected exact allocator/zone/loader/relocation/compiler/link sources and
real OSData fixed64, OSArray variable80 and kalloc16boundary references. Use
mutated owned real byte copies to exercise positive/negative signed inline
addends (including a real substring), unsupported type/width/local/pcrel/pairs,
missing pointers/live_support, signature/flags/version/reserved fields and bounds.
Preserve originals and every failed run. The initial VM033 ADDEND parser failure
and disclosed ignored-inline-addend resolver are historical facts, not repaired
in that foreign tool.

Build explicitly SYNTHETIC linked-layout fixtures by copying the real metadata
and cstring bytes and rewriting only pointer VAs to the controlled image. These
are parser controls, never Apple-layout invention, actual linker products,
compiler outputs, runtime measurements or product qualification. Exercise final
VA/file resolution, readonly placement per exact selected segprot r--/r--,
fixed/variable boundaries/count/section ordinal/stride, required identity minima,
missing required vs legal optional removal, empty requirement incomplete result,
unsupported fileset/auth/fixup semantics, stale digest and source/layout/proof
corruption. Required liveness is a controlled proof input, not inferred from an
object's membership or source receipt. CU must validate genuine actual lineage
and independently accepted actual required-record proof before product adoption.

Exercise borrowed coherent FD growth/truncation/path replacement/symlink refusal,
owned read resource cleanup including failure and repeated snapshots. No lazy
handles may escape; output is serialized JSON primitives after context closes.
No actual compiler, link, archive, section utility, QEMU, allocation, phone,
MAIN publication or common check. Independent review/current-HEAD integration
and actual root-leased genuine image remain separate gates.
