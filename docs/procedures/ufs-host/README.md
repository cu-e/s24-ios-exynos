# UFS/MCQ host admission procedure

DRV-004, owner `codex-team-ufs-host-20261105-aw`. This is bounded host
preparation for DRV-002, not a kernel dependency bypass or native driver.
Only owned code and ignored local artifacts are changed. Main references are
read-only with `GIT_NO_LAZY_FETCH=1`.

Before implementation tests, plan a laboratory experiment. Inspect pinned E1S
UFS patch and Samsung UFSHCI, UPIU and MCQ declarations. If a public source blob
is absent from the sparse/promisor checkout, fetch its exact pinned raw text
into owned artifacts and verify its Git blob object hash against pinned
`git ls-tree`; never silently fetch into the main reference checkout.

Implement a pure host C admission boundary for bounded READ(10) descriptors,
read-only direction, caller-qualified LUN/partition extents, buffer overflow,
DMA lease ownership and stale/error completion. No arbitrary command emission,
MMIO, write/erase/format opcode, reset, DMA synchronization or phone operation.

Compile independently extracted genuine primary declarations to qualify exact
layout and offsets. Test actual owned C boundaries with source-built byte
records, malformed inputs and lifecycle failures, then execute real ASan and
UBSan tests plus deliberately faulty negative controls. Compile owned code to
ARM64 only; no hardware execution or XNU linkage is implied. Preserve source
licenses and exact source/compiler/command/exit/hash evidence. Stop with an
exact missing-input report if source qualification cannot be established.

BYH3-specific source, real PHY/IOMMU/MCQ state, DMA mapping/cache coherency,
controller quiescence and encrypted userdata access remain unqualified.

Reproduce using the exact verified local source cache (a fresh run name is
required; runtime artifacts are never overwritten):

```sh
python3 src/platform/storage/ufs/check.py --run fresh-name --lab-root /home/egor/dev/pet/s24-ios-exynos --source-cache /home/egor/dev/pet/s24-ios-exynos/worktrees/drv-004-20261105/artifacts/ufs-host
```

The runner does not fetch or alter references. It verifies source cache bytes
against tracked SHA256, exact pinned tree Git blob SHA1 and current reference
HEAD; missing inputs are explicit errors. Cache entries are the unmodified
public sources below `source-session1` and `source-session2`. The first cache
contains four exact public inputs absent from the sparse/promisor checkout;
the second adds the genuine UPIU header. One attempted repeated raw read was
interrupted by `IncompleteRead(11024 bytes read, 4562 more expected)` before
writing any replacement bytes. Existing verified inputs were retained and the
additional header was fetched separately and checked against its tree object.

All generated primary source copies and oracle source remain ignored. Native
host Clang18 at `/home/egor/.local/bin/clang` supplies the existing Linux
ASan/UBSan runtimes. Deliberately faulty heap and signed-overflow controls must
exit nonzero with their expected ASan/UBSan diagnostics. An ARM64 object is
compile-only: no SDK, XNU link, controller operation or ARM execution occurs.
