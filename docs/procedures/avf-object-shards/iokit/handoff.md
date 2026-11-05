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
The final source-only attempt3 passed: all104 input bindings, changed-manifest,
changed-selector and existing-output exact-reason rejection controls. Positive
admission exited0 in2.544s with current-image VmHWM71032KiB. All three memory
samples exceeded4GiB. Source report SHA256 is
`7804e01a0d8e5cb55c245340b7cda7bac049f717acc6f460a9e03e898892284a`.
The report records three genuine missing search roots,1143 lexical include
observations and597 shadowed occurrences (all identical bytes). The21 unresolved
lexical observations are in conditionals/comments; no active missing dependency
is established. `source-observations.json` records context and limitations.
No profile weakening, search-root creation or argument removal occurred.

`evidence.json` binds tested implementation `f4f9507`, source/tool/outputs, exact
commands/exits/time, resource samples and both retained failures. The remaining
step is independent review and root/kernel-integrator source-stage acceptance.
Actual compilation additionally waits for
VM008 and independently accepted VM009 plus explicit root resource admission
and heavy lease. Keep VM-013 in progress until acceptance is real.
