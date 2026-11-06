# STR002 implementation handoff

Owner codex-e1s-memory-20261106-sr2, branch team/str-002-e1s-memory-20261106,
base951f233. Claimed and inspected actual STR002 card. Only four reserved paths
are edited: attributed patch, public actual-C fixture/pins, preparation checker,
and this procedure directory. No pinned/shared source or existing builder edit.

Concrete changes: validate FDTv17 header/block/string/tree bounds before legacy
traversal, include the mandatory header reservation map, reject incomplete or
capacity-truncated memory/reservation tuples and overflowing endpoints, preserve
supported parent-cell addressing and valid gap choice, reject unsupported
reservation translation/dynamic/nested semantics, and remove payload-RAM fallback.
The checker stages actual donor C plus exact patch/extracted selection body and
emits six prospective commands only; it cannot compile or execute them.

Final selected source-only preparation: artifacts/e1s-loader-memory/prepare-5/
plan.json, SHA a436b8b280bda37ba49bcfb01a0c886e9435340055c4d5f9a1697e915b7ac3d9.
Earlier prepared plans remain immutable and unselected. No actual compile/control
has run. Await root exact small admission and accepted supervisor selection;
then run the six frozen commands once, preserve failures and assess actual C
and AArch64 results. Register STRMEM001 before execution. No hardware proof or
known-safe physical RAM is asserted; readable S-Boot DTB backing remains an ABI
precondition. Keep actual log/framebuffer/firmware state limitations explicit.
