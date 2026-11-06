# VM-014 final resource source plan

Original owner `codex-guest-exec-20261106-cw` continues VM-014 in fresh worktree
`worktrees/vm-014-resource-final-20261106`, branch
`team/vm-014-resource-final-20261106`, based on actual current MAIN
`e8ec6cd5f42a8b97c81c440303a0f8a6f5078a30`. MAIN is the sole registry.
Register new experiment `VMLIBRESOURCEFINAL-001` before the single plan.

Root accepted VM-046's canonical physical executor
`worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py`, SHA256
`9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755`,
source commit `d0ffda0a38a344e9d679757b5b9f5fd0ec1502d5`. Use the exact resource
tuple from its `fixtures/public/avf-resource-profile/inputs.json`: manifest
80cc9fe5, qualification eb2ca440, selectors a2379193 and namespace fdfc50d3.
Full paths/digests are sealed in this task's `resource-final/request.json`.

Run `plan-001.py` once with constrained stdlib Python. The small wrapper only
imports the hash-qualified canonical executor and invokes its accepted
`run_child`/`supervisor` API around the exact source-only CLI with explicit
`--resource-profile project-budget-v1`. The qualified supervisor owns finite
120-second process cleanup, 256 MiB combined controller/child sampled RSS and
three stable >=4 GiB memory samples. Child writes are Landlock-confined to the
fresh guard tree, with planner output at `plan-001/runner`. No duplicate binder,
lexical checker, source matrix or compiler is introduced.

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -s \
  docs/procedures/avf-object-shards/libkern/resource-final/plan-001.py
```

The planner must select exactly 77 libkern IDs from the complete accepted
resource graph and produce zero objects/commands/compiler starts. Preserve
all failed outputs. Send its plan path/hash, input-binding hash, count, new
experiment, owner/worktree and still-absent future actual output to root and
INT002 immediately after completion. Keep the experiment planned for future
actual execution; source planning does not consume a compiler allocation.

Future proposed actual output is
`artifacts/avf-object-shards/libkern/resource-final/build-001`. It stays absent
until a distinct exact root allocation/approval. No resume, old-key adoption,
old-object credit, input/tool/flag edits, actual compiler, QEMU or worker
publication/common check is authorized. Preserve old worktrees and all old
objects/raw receipts, including OSKext's incomplete post-child accounting fact.
No retroactive repair or complete resource-trial claim is made. VM-014 stays
open until explicit original-owner closure authorization.
