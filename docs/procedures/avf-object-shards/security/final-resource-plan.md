# VM-019 final accepted resource source plan

Original active owner: `codex-guest-exec-20261106-dd`; no new claim.
Fresh branch/worktree `team/vm-019-resource-final-20261106` /
`worktrees/vm-019-resource-final-20261106` starts at accepted MAIN
`e8ec6cd5f42a8b97c81c440303a0f8a6f5078a30`. All earlier physical worktrees,
plans, receipts and failure history remain preserved under their original pins.

Root's `final-resource-source-plan-instructions.json` and
`resource-profile-gpu-root-acceptance.json` authorize one source-only final plan.
The accepted canonical helper is the EV physical file
`worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py`, SHA256
`9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755`.
The frozen EV fixture SHA256 is
`8946b29eb8760c1224b5f8a84b67cdb4f0cfb83811f5cdcc35c518fd4877009c`.
Use its exact 80cc manifest / eb2 qualification / a237 full selectors / fdfc
namespace tuple, with explicit `--resource-profile project-budget-v1`.

First attach this fresh worktree in the sole MAIN registry under the original
DD owner and register `VM019FINALPLAN-001` against this procedure. Only then run:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/avf-object-shards/security/plan_final_resource.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --experiment VM019FINALPLAN-001 \
  --out artifacts/avf-object-shards/security/final-resource-plan-001
```

The adapter reuses the canonical accepted helper's qualified process supervisor,
with a 256 MiB aggregate RSS limit, 120-second command deadline, stable three
memory samples, write confinement and finite cleanup. It adds no engine,
namespace, recipe or compiler flags. One `--mode plan` child validates the full
accepted namespace and emits exactly 23 security keys. No compiler, research,
generator, approval, allocation, resume or old-profile key credit occurs.

The proposed actual output is
`worktrees/vm-019-resource-final-20261106/artifacts/avf-object-shards/security/final-resource-execute-001/runner`.
It must remain absent before and after this source-only plan. Root receives its
full path, the exact source-plan and input-binding hashes, actual registered
experiment and original owner/worktree. A later second-wave build requires a
separate root allocation and registered build experiment; this phase grants none.
