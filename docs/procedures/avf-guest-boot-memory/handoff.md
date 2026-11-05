# VM-026 handoff

Owner `codex-guest-exec-20261106-dh`, branch `team/vm-026-20261106`, worktree
`worktrees/vm-026-20261106`. Base MAIN commit was
`4bea9b5` when the atomic MAIN host queue assigned VM-026.

Scoped implementation commits are `b89fd23`, `d572d94`, `ffd08db`.
Only the acquired tool, fixtures directory and procedure directory are changed.
The final source freeze is `ffd08db`; later evidence/documentation commits do
not change the executed tool. No generated registry views are committed here.

The tool source binds the genuine selected Scion shim, selected prepared guest
XNU boot/MMU/allocator declarations, qualified shim Image/build report and
qualified QEMU virt/arm64 boot source. It inspects an actual XNUP kernel entry
incrementally. Its host address plan is explicitly declared input, never a
runtime observation. A passing host layout cannot prove allocator memory demand,
metadata ABI, successful MMU execution, genuine XNU boot or RAM sufficiency.

Three exploratory source-only runs are preserved under
`artifacts/avf-guest-boot-memory/run-1`, `run-2`, `run-3`. They predate the final
QEMU source binding and are superseded by the final registered experiment,
without deleting or rewriting their evidence. No compiler or guest ran.
Initial exploratory reads tried two incorrect boot.h paths and an unextracted
mkpayload.py path; each returned exit 2. The actual boot declaration was located
at `pexpert/pexpert/arm64/boot.h`; mkpayload.py was read at its pinned Git blob.
These were source-path discovery failures, not kernel/preflight measurements.

Final experiment VMBOOTMEM-001 was registered before its final command matrix.
At frozen commit `ffd08db`, all17 owned controls passed. Seven real CLI cases
preserve the source-only inconclusive result and four expected exit-2 failures:
missing kalloc section, insufficient RAM, false QEMU FDT placement and an Image
extent that excludes its BSS/stack. Both owned synthetic positives passed.
The maximum measured current-process VmHWM was23436KiB. The final matrix lives
at `artifacts/avf-guest-boot-memory/final-ffd08db/matrix.json`, SHA256
`ffc9f4464ec2b0ad01dcb3ab896de230f6ff158f5c7c7229626cfa200d82932c`.
The maintained `evidence.json` binds all exact commands, outcomes and hashes.
Ledger transactions can wait behind other writers; never start another claim or
mutate the registry file directly. The task remains
in progress pending independent review, integrator acceptance and fresh MAIN
common checks. Only the original owner may close it after acceptance.

Next integration actions: independently review the exact frozen commits and
commit-bound evidence, then publish only the scoped patch under the common
integration lock. Once a genuine linked guest image/XNUP exists, supply its exact
address/bootargs plan and run the streamed image preflight. Observe the actual
FDT and runtime allocation/MMU behavior only under accepted VM-008/compiler/
root-resource and exclusive QEMU gates. Do not infer that the 256 MiB lease is
sufficient from the small synthetic parser-control fixture.
