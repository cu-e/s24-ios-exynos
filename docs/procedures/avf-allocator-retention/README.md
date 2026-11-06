# Source-qualified allocator retention byte validator

VM-048 adds `tools/build/avf_guest_allocator_retention.py`. It leaves original
VM033 tool/witnesses unchanged. This implementation is a working object/final
image parser; it grants no product, runtime or full-kernel qualification.

The pinned genuine kalloc.h and zalloc.h define ARM64 LP64 fixed records64B:
four zone_view pointers, signature pointer32, flags40, size44 and unused48/56.
Variable records80B have version0, header size2, type size4, stats8, name16,
next24, uint16 heap32,22 one-byte zones34, header signature56, type signature64,
flags72 and trailing alignment padding76. The22 zones follow the selected
32768/32 log2 calculation. Actual OSData has three fixed records; actual OSArray
has three variable records. The latter's header signature pointers are null,
consistent with the three-argument macro. Empty emitted signatures remain valid
for data-only/VM types; selected compiler signatures use hexadecimal digits.

Object pointer inspection supports external defined-symbol ARM64_RELOC_UNSIGNED,
width8, non-PC-relative only. It resolves `symbol.value + signed64 inline_addend`
inside the actual target cstring section. This fixes the disclosed original
VM033 resolver omission, including genuine-copy substring and compensated
negative-addend controls. Local/absolute/undefined/subtractor/authenticated or
other pointer relocations explicitly refuse. ARM64_RELOC_ADDEND signed24 payloads
are treated as instruction addends, checked with same-address PAGE21/PAGEOFF12
followers, never interpreted as section indices. The real kalloc consumer has
16 references to the four fixed/variable start/end symbols and17 ADDEND pairs.
The historical initial VM033 `relocation target out of range` failure remains
preserved in the original handoff.

The final parser checks actual boundary values/section ordinals, absence versus
empty range, nonoverlapping metadata,8-byte alignment/strides, zero runtime and
reserved fields, metadata version/flags/sizes, final unslid64 pointer-to-file
mapping, names/signatures and selected segment protections. Source contract125a
selects DEVELOPMENT/BCM2837 USE_LTO0, no dead_strip and DATA_CONST r--/r--; the
validator enforces that tuple. It rejects a changed LTO/dead-strip profile until
a new independently qualified source contract exists. MakeInc.def's conditional
LTO/dead-strip rule is explicitly preserved as source evidence. Dyld rebase/bind,
dynamic relocation tables, chained fixups, arm64e/auth pointers and filesets are
unsupported, with explicit failure instead of raw-pointer guesses. Boot-time
write arrangements and later lockdown remain unmeasured.

CU owns the controller and product gates. The agreed APIs are:

- `source_contract({source_name: borrowed_CoherentFile, ...})` checks all exact
  selected source/semantic/link-contract hashes and returns detached layout facts.
- `inspect_object(snapshot, view, source, *, symbol_at)` returns bounded semantic
  fingerprints/counts and resolved-pointer facts from actual ARM64 object bytes.
- `boundary_references(snapshot, view, *, symbol_at)` reports actual consumer refs.
- `validate(snapshot, view, contract, *, symbol_at)` returns JSON primitives;
  CU passes its reviewed `macho_symbol(snapshot, view, raw_nlist_ordinal)` callback
  while still inside `macho_snapshot(path, image=True)` context.

The contract has `source`, `selection`, `witnesses` from `inspect_object` and
`required`: each required row has `object_sha256` (distinct actual witness hash
list), `fingerprint`, positive `minimum`, and `liveness_proof_sha256`. Minima must
not exceed summed genuine witnessed multiplicity; repeated source digest credit
is rejected. CU must independently verify the exact reviewed producer, selected
object list, source/config/profile and image lineage, then validate a real
required-record liveness proof. A digest supplied here is an explicit proof
binding, not verification of its contents or authorization. VM047 supplies
member/runtime facts and does not prove live allocator callsites. That missing
actual liveness proof remains a closed gate.

Only explicitly required minima are compared with final records. The module
never assumes all emitted records survive linker selection/dead stripping, or
that all records in a historical object are selected/live. Conversely a missing
required fingerprint/count fails. An empty required set returns
`incomplete-no-required-record-proof`. Even a passing parser/minima result says
`product_qualification: not-granted-by-byte-validator`. CU's actual productive
completion pins remain empty until separately accepted actual evidence exists.
No caller boolean or source-only receipt can turn synthetic controls into a
qualified image.

Ranges are bounded through borrowed CU FDs (one MiB maximum read). Strings have
a4096-byte terminator bound, object/required identities a4096-row combined bound,
relocations a2million bound and final metadata a1million-record bound. Final
records stream one at a time with only requested fingerprint counters retained;
no whole-image dictionary, unbounded string/symbol expansion, or lazy FD result.
Changing a bound requires a new review, not silent fallback.

The final source-only control run uses CU lifetime correction9f80e323 at commit
6bf9c0eef728f24c9bb76d040b98d3631edeecf0, explicitly delivered by CU. Earlier
0631a7d8 controls and the initial failed fixture run remain preserved. Neither CU
source freeze grants productive authority before independent review/publication.
The checker never invokes compilers/linkers/archive/section tools or guests.
Copied synthetic linked-layout fixtures are labeled parser controls and use real
record/cstring bytes; they are never reported as linked images. See immutable
procedure.md and source-api-amendment.md for registered commands and scope.
