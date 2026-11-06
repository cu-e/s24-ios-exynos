# VM-047 versioned Clang driver correction

Original FB owner, new WT `worktrees/vm-047-driver-contract-20261106` from frozen
`3a330d6e9ca115b20b734bb7fdb0135231d66de9`. The original380 source,65 controls,
0631 borrowed API evidence and FD44/33 review remain physically unchanged.
Root authorized this separate driver-aware correction after the concrete125a
recipe mismatch was found. The genuine command runs Clang7972, uses native
`-filelist`, direct tails, `-lcc_kext` and source-qualified runtime resource lookup.
It is not a direct ld command with archive path operands.

Register VM047-DRIVER-001 before the one focused control batch. Run
`timeout 120s env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s fixtures/public/avf-runtime-linkmap/driver-controls.py --main MAIN --out NEW_OWNED_OUTPUT`.
Hard256MiB address space, three one-second4GiB floor samples, current `/proc`
VmHWM, no target tool/driver/compiler/linker/archive/section tool/QEMU/allocation.
The suite hashes14 actual/reference driver source files and the real qualified
compiler without invoking it, then tests only new forwarding, sealed-filelist,
source-proof and complete observed selection boundaries. Synthetic image/map
and staged-object bytes remain synthetic, with zero actual execution credit.
Use corrected frozen CU9f80 borrowing at6bf9 for this new batch only; original
producer65 checks stay honestly attributed to0631. Preserve failures; no retry.

## Driver contract v2

`avf-runtime-linkmap-contract-v2` requires `command_kind:clang-driver` and
`selection_scope:all-observed-live-runtime-members`. Other fixed lineage,
descriptor, map/image/archive/catalog/object-list bindings retain v1 semantics.
Optional `required_members` is an additional source-supported expectation;
selection itself is always derived from every actual map live runtime member.
An empty runtime selection is an explicit fact, without forcing archive loads.

`avf-guest-link-object-list-v2` uses exact `actual_driver_argv` and rejects an
`actual_link_argv` field. `derived_linker_operands` contains
`kind:forwarded-driver-operands-only`, the diagnostic subset `argv`, and
`source_proof:{path,sha256}`. This is a source-derived diagnostic projection,
never observed or complete child argv. It does not infer resource library
resolution, archive membership or all driver-generated linker arguments.
Runtime/archive membership instead comes from CU's authenticated staging/command,
the actual map, exact allowed archive manifest and qualified physical bytes.

The pinned `driver-forwarding-source.json` qualifies Options.td flags,
LLVM comma/separate parsing and RenderAsInput behavior, Darwin AddLinkerInputs,
and the specially rewritten --no-demangle exclusion. Production diagnostic
forms are `-Wl,-map,PATH` and `-Wl,-why_load`; consecutive canonical Xlinker
equivalents are also supported. Ambiguous/reordered/duplicate/nonadjacent map
forwarding, response files and native unqualified diagnostic spellings refuse.
No alias/export/provider-selection flags are changed.

CU seals `filelists:[{path,sha256,ordered_object_paths}]` and exact ordered
`objects:[{id,path,sha256}]`; archives retain exact role/path/hash/member rows.
CU passes borrowed `driver_source_snapshot` and `filelist_snapshots` (mapping
exact path to CoherentFile) as new keyword arguments to `validate`. The module
checks filelist bytes/hash/ordered expansion and native actual driver filelist
operands; additional staged tail paths must be explicit actual driver operands.
CU independently authenticates object bytes, staging lineage and actual command.
Libraries resolved by `-l` are not guessed to be literal archive argv operands.

The v2 witness returns every `selected_live_member_ordinals`, explicit
`empty_runtime_selection`, and bounded `selected_member_symbols` records with
physical ordinal/name/hash and unmodified catalog defined/undefined lists.
CU can check all selected-member undefined declaration names against its same
final defined nlist, recording source/map attribution where available. This is
definition availability, not a per-live-callsite edge claim. Conservative import
candidates remain separate. The module still returns product authority false,
execution authentication false and import/callsite/LTO closure unmeasured.

Optional `atom_queries:[{object_path,name}]` contains at most512 unique exact
admitted path/name pairs derived and authenticated by CU. During the same
validated streaming map pass, the witness reports all matching live atoms as
`queried_live_atoms:[{query_index,object_path,file_id,name,address,size}]`, at
most4096 matches. Dead atoms grant no query liveness credit. These are generic
map facts only, `queried_atom_qualification:false`; CU/FC own source-object
nlist lineage, allocator-record ranges/fingerprints and any retention decision.

After source/evidence freeze, FD independently reviews this correction. CU wiring
and actual command execution wait independent acceptance and root authorization.
No MAIN/common, actual link or whole VM022 closure belongs to this task.
