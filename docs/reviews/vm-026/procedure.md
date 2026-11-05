# REV-031 independent boot memory preflight review

Owner: codex-review-boot-gates-20261106-eb. Task: REV-031. Owned scope: docs/reviews/vm-026 only.

Prospective experiment REVBOOTMEM-001: review exact VM-026 metadata a47a378dac38a0e86f6e7abd66c12f28390fa245 and code ffd08db8616f7a486762b951dc69a9ace8716dea. Independently hash the immutable source/evidence, read exact pinned Scion Git blobs and prepared XNU/QEMU source constraints, and run bounded Python-only byte/parser controls against the frozen tool. Synthetic format-control bytes are explicitly not XNU or boot evidence. Save original commands, actual exits, inputs/output hashes and source locations in task-local artifacts/rev-boot-memory/20261106-review1.

Hypothesis: static layout acceptance must reject byte/address inputs incompatible with the selected ARM64 shim and source constraints, and must preserve the boundary between necessary source-derived constraints and unmeasured actual image/MMU/allocator/RAM behavior. Check entry alignment and range, segment extents/overlap, XNUP bounds, source plan arithmetic, real Image BSS/stack size and declared QEMU placement. Report counterexamples rather than changing producer files. Inspect producer matrix and current source/metadata bindings without repeating its broad matrix.

Limits: Python only, address space at most 256 MiB, prospective overall timeout 120 seconds. No compiler, link, QEMU, common checks, device, producer edits or shared artifact writes. Read-only Git uses GIT_NO_LAZY_FETCH=1 and GIT_OPTIONAL_LOCKS=0. All outputs stay in reviewer worktree. The task remains in progress until coordinator acceptance. A genuine frozen final kernel image plus measured leased boot, FDT, MMU and allocator demand remain later gates.
