# VM-013 handoff

Owner: `codex-guest-exec-20261106-cv`. Worktree:
`/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-013-20261106`.
Branch: `team/vm-013-20261106`. Base: `aac27cf`.

The atomic MAIN queue returned VM-013. It owns exactly 104 `iokit` IDs in the
coordinator selector and the two task paths. No other shard is modified.
The inventory is 103 C++ inputs and one C input (`iokit/IOStringFuncs.o`),
with 17 generated IIG implementations and 87 direct sources. The pending
VMIOKITPREP-001 plan hypothesis used inaccurate C++-only shorthand; the actual
language inventory supersedes that wording without changing source selection.

Implementation commits are `6265fbe` and `23338fb`. The inspector only reads
source/config/recipe/header/tool inputs and publishes a fresh selected report.
It checks exact graph/selector pins and all selected source/config/compiler
hashes, flags and outputs. Search ordering, missing directories and shadowed
literal/forced header candidates remain observable. Recipe arrays are referenced
by hashes rather than reconstructed or copied. The shared VM009 runner owns
future compilation. Neither dependency closure nor IIG private ABI is qualified
by lexical include observations.

Experiment VMIOKITPREP-001 was submitted once to the MAIN ledger. Execution
waits for successful registration; pending lock waits are not measurements.
The earlier exploratory schema-introspection command assumed an object-shaped
manifest and exited 1 with `AttributeError`; the real manifest is a JSON array.
That failed exploratory read made no project changes and is not a positive
source-admission result. A subsequent bounded inventory read succeeded.

No compiler, linker, QEMU, physical phone operation, old E1S object reuse,
shared source write, artificial include directory or MAIN publication occurred.
The next step is the registered finite source-only positive inspection and
changed-manifest/selector/existing-output rejection controls, preserving each
actual exit and output hash. Then provide exact source-stage commits/evidence
to root and the kernel integrator. Actual compilation additionally waits for
VM008 and independently accepted VM009 plus explicit root resource admission
and heavy lease. Keep VM-013 in progress until acceptance is real.
