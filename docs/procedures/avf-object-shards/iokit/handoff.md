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

## Accepted shared runner plan

Root resumed the original owner for the next wave after VM008 and VM009 were
accepted/done. VM013BUILD was registered in MAIN and remains planned for later
actual root-authorized execution. No build result is recorded prematurely.

The accepted shared runner (SHA256 13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47)
produced a fresh mode=plan in
`artifacts/avf-object-shards/iokit/shared-plan-1/runner`. Shared run_child/supervisor
and the root in-process launcher install(120) supplied finite source-only
admission, aggregate RSS monitoring and owned-child cleanup. No additional
executor or source checker was authored or invoked.

Plan PASS: exactly 104 selected rows, preserving all 17 genuine generated IIG
implementations; zero compiler starts. Plan SHA256 is
`9682a4b1db4a9e289242c1096c99afd3f4f5ac605531c1acc904aa14461d90c8`.
It retains every input_key, source/config pin, recipe-template digest and expanded
argv. Input-bindings SHA256 is
`60f7b4774bcec32ff83093629d5f1fa00ade24ecddbd4c64a2d6e96c8d75221e`.
The measured whole guard took 99.639 s with 123822080-byte peak total owned RSS,
three stable >=4 GiB samples and zero surviving owned processes.
`shared-plan-evidence.json` binds exact plan/runner/guard/source-evidence hashes
and all 104 selected input keys/template digests. Original source evidence bytes
remain unchanged.

Actual 104-object compilation, conditional compiler dependencies and historical
IIG compile uncertainties remain unmeasured. The next step requires explicit
root heavy group lease and exact approval binding. Then use only the accepted
shared mode=execute, fresh owned artifacts, existing 600 s in-process guard and
one serial compiler. No private ABI qualification follows from this plan.

## Actual wave2 execution

Root explicitly activated VM-013 slot in guest-kernel-wave2-20261106-11 alongside
VM-015, with exact approval SHA256
`3727e69a2dbf4d973ad742ebaa670c92d393f48bf0e851748fd357e0e8992091`.
The original VM013BUILD experiment was still planned. One invocation used the
same physical reviewed MAIN runner and direct same-process reviewed launcher
(600 s), fresh `artifacts/avf-object-shards/iokit/execute-001`, one compiler,
120 s per command and <=256 MiB sampled controller+child RSS. No source edits,
profile weakening, reruns, resume reuse or cap changes occurred.

Actual result: runner exit 0, all 104/104 ARM64 Mach-O objects and their actual
compiler dependency bindings PASS, including all 17 generated IIG implementations.
The final unchanged-namespace closure also passed. This resolves the historical
16 remaining generated-IIG compile uncertainties in the frozen guest context;
selected private RPC/IIG ABI and link/runtime interoperability remain unqualified.

Raw shared-executor evidence SHA256 is
`d280910f050ef5ea0eaa8261ed6ab78d4e381cf68fc86310014e07dca397433c`
at `artifacts/avf-object-shards/iokit/execute-001/evidence.json`. Every actual
compiler command exited 0; all commands admitted on exactly three stable samples,
minimum admission MemAvailable 13148397568 bytes. Peak aggregate controller+child
RSS was 244248576 bytes, controller exec-image peak 129486848 bytes, zero surviving
owned children. Largest actual compiler-command elapsed time was 3.076 s.

`build-object-index.json` indexes each actual object/dependency/sidecar hash and
actual dependency count without adding a validation engine. `build-evidence.json`
binds the raw capsule, exact source/tool/profile/plan/approval/launch pins and
resource results. The at-launch approval and full two-slot lease snapshot remain
in `artifacts/avf-object-shards/iokit/execute-001-launch/authorization-at-launch.json`.
No private records, SDK or E1S products were introduced.

Root was asked to release ONLY VM-013's slot after the runner exited and cleanup
was verified. The worker never edits either VM-015's slot or the whole group.
VM013BUILD record was submitted in MAIN with the immutable raw executor evidence.
Keep VM-013 in progress pending independent review, integrator acceptance and
fresh MAIN common checks. No link, QEMU, console, PID1 or device result is claimed.
