# STR-026 BSD shard c preparation

Original owner: `codex-e1s-native-objects-20261106-sr26`. MAIN atomic
`task claim-next` exited 0 and assigned STR-026. This worktree is
`worktrees/str-026-e1s-bsd-c-20261106`, branch
`team/str-026-e1s-bsd-c-20261106`, based on MAIN
`415c9a1fcad73cb47affcedbb037520ce973f888`.

`fixtures/public/e1s-native-objects/bsd-c/selection.json` seals the actual
STR-016 BSD ordered OBJS half-open slice `[340:508]`: 168 unique identities,
from `bsd/subr_xxx.o` through `bsd/bsd_stubs.o`. Its SHA-256 is
`9a65df0a8ba15a1d4658da2e58e8ab34d88557cd4b7cc802cbf47fe0eb492a51`.
`selection-provenance.json` records the bounded source verification and
has SHA-256
`8321a968c09ec28886be0b8b596220c8050a78953dbab933b3056552655e0df7`.

The qualified interface is `c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579`;
partitions are `2519966081d650108e62e10734f8b23ac4bda51008930e7ec7dec8e53a98e31a`;
the consumer context is `00a9d47cb973d0a3bb32426d8218f01bfe1b51038bcef39829e6a65c3780f638`;
the explicit portable profile is `a65f70a1daf01c26399ca1034ff41dafbf790ef86bccc3caa8f84acd0df27581`.
All absolute paths and complete pins are in the manifest. The derived
STR-014 source manifest is
`f85b699020a36635a65f1e4304c218c2d216526835168ec02e397973a97101ac`.

Verification read and hashed the pinned descriptors, derived source index,
168 original recipe receipts and 168 actual selected source bindings. It
checked exact equality with the original ordered BSD slice. There are 165
C recipes and three assembly recipes; all 168 selected original vectors
contain `-DXNU_NO_TYPE_BUILTINS=0`. No vector was rewritten. The selected
sources include two materialized context inputs; their exact context kind,
original producer path and hash are retained beside the original graph
row. Historical graph status fields remain unchanged. The pinned consumer
context supplies actual source bindings, including generated placement.

Root's reviewed STR-030 native caller and source-plan budget are the next
gate. This preparation created no caller source plan, private CWD projection,
compiler child or target product. Consume the one reviewed caller with
existing unchanged generic resource helpers after root releases it; do not
create another executor. Future compilation needs a separate root allocation
and private fresh outputs, one compiler with a 512 MiB owned-tree cap inside
the root's global six-job/6 GiB budget with 2 GiB light reserve. Preserve
failures, actual MD closure, command/input/output hashes, resources and owned
cleanup. The global allocation remains root-owned.

This receipt qualifies selection/provenance only. Full input closure, fresh
Mach-O objects, MD closure, compiler completeness, full kernel/link/provider
closure, private ABI, runtime, boot, image and hardware remain unqualified.
No compiler, generator, probe, linker, common check, QEMU or device action was
run. Prior RELEASE/BCM/guest objects receive no credit. The original
Make-selected `bsd_stubs.c` identity is preserved; no new fake headers or
stubs were introduced.
