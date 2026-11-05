# VM-020 handoff

## Outcome and ownership

Source preparation is implemented in this task's three owned paths. Owner:
`codex-guest-exec-20261106-cx`. Worktree: `worktrees/vm-020-20261106`.
Parent MAIN commit: `aac27cfbc0d71b34eda33ddf366c72427507ae0b`.
The exact delivery commit is reported in the shared ledger update and team
handoff; the evidence binds the producer and all actual output bytes.

The producer verifies genuine pinned firehose sources/configurations and
source-built executable tools, regenerates the actual kernel header, and
prepares provider/layout/interface recipes from VM008's fresh guest graph.
Four negative controls reject native board flags, source digest changes,
historical namespace substitution and shared output substitution.
No old E1S archive or object is read, copied, linked or supplied. Historical
public descriptors are used only to select source/header/tool pins.

## Evidence and preserved attempts

`preparation-session3/evidence.json` is the final successful producer run.
It includes run-local immutable probe snapshots, CPU-limit assertions and the
current builder digest. The first two successful source preparation runs are
preserved as superseded records; their recipe probe paths refer to the mutable
working fixture at that time and must not be executed or treated as final
input bindings. All three producer invocations returned exit 0.
Evidence includes real Git and unifdef commands/exits/timing, source/tool and
output hashes, and `/proc/self/status` VmHWM/VmRSS. Hashing is streamed.
Final producer memory observations: VmHWM:	   71964 kB, VmRSS:	   55772 kB.
`validate-preparation.py` independently checks the current builder and run-local
probe snapshot hashes, guest recipes, four rejections, Git/unifdef-only child
commands, absence of objects/archives, and `git diff --check` (exit 0).
Its exact command and hashes are in `validation.json`.
No repository common checks were run by this worker.

Two earlier read-only discovery commands failed and changed no input: a JSON
inspection assumed the 1080-row manifest was a dictionary and exited 1 with
`AttributeError: 'list' object has no attribute 'keys'`; a subsequent inspection
correctly read it as a list. An `rg -n 'libLLVM|libclang|library_sha256'` search
included absent MAIN `tools/build/avf_kernel_objects.py`, returned exit 2, and
then the qualified compiler descriptor was read directly. These are discovery
failures, not compile attempts. The earlier successful runs are preserved rather than overwritten after
adding layout assertions and immutable per-run probe snapshots.

## Boundaries and next step

No compiler, archive, QEMU, ADB, physical phone, shared Git source hydration,
MAIN publication or common-check action occurred. Guest layout and provider
symbols remain unmeasured. VM008 acceptance and root resource admission are
required before compilation. VM009 owner confirmed the common executor has
no accepted arbitrary-component CLI yet; integration must adapt these exact
recipes to the reviewed common process engine, including tool-runtime
verification, without inventing guest-graph rows or duplicating supervision.

Send this source-preparation commit to kernel integrator `/root/lab_worker`
and root. Independent review, actual admitted compilation, guest layout and
symbol/dependency checks, archive creation, integration and fresh MAIN checks
remain outstanding. Original owner alone may close the task after acceptance.
