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

Experiment VMIOKITPREP-001 was submitted once and registered in the MAIN ledger.
The first source-check attempt failed before admission: naming the script
`inspect.py` shadowed Python 3.14's standard-library module imported by argparse.
The exact failed commands, tracebacks and input hashes are retained in
`source-checks-attempt1.json`; its negative exits are not counted as successful
rejection controls. The helper is renamed `source_admission.py` before retrying.
The second attempt retained two successful changed-input rejection controls but
failed positive admission on the real C recipe's argument ordering:
`IOStringFuncs.o` places `-o` after its source; the 103 C++ recipes place it
earlier. The source must occur exactly once, rather than being the final argv
token. `source-checks-attempt2.json` preserves this failed assumption, and the
fix preserves every genuine input argument and output placeholder.
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
