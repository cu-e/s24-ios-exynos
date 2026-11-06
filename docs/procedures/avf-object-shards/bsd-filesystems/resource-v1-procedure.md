# VM-011 accepted resource namespace source plan

Original owner `codex-guest-shard-20261106-cr`; new worktree
`worktrees/vm-011-resource-v1-20261106`, branch `team/vm-011-resource-v1-20261106`,
base MAIN `e8ec6cd5f42a8b97c81c440303a0f8a6f5078a30`.

Root's `final-resource-source-plan-instructions.json` and accepted
`resource-profile-gpu-root-acceptance.json` authorize ONE source-only plan for
the exact original 90 `bsd-filesystems` IDs. Executor is the frozen physical
VM-046 EV helper SHA256 `9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755`.
The exact profile tuple is copied from its accepted input fixture into
`resource-v1-request.json`: manifest `80cc9fe5`, qualification `eb2ca440`,
selectors `a2379193`, namespace `fdfc50d3`. Full paths/digests remain in that
request. Both prospective stages explicitly use `project-budget-v1`.

Update only the original VM-011 metadata to this worktree, then register
`VM011RESOURCEPLAN-001` and the separate future actual `VM011RESOURCEBUILD-001`
through MAIN `tools/lab.py --root MAIN`. The source experiment deadline is
120 seconds. The planned actual experiment grants no execution authority.

Run `python3 -B -s fixtures/public/avf-object-shards/bsd-filesystems/resource-v1-plan.py`
once, after registration. It is only orchestration: import the frozen shared
executor and call its qualified `supervisor` and `run_child` APIs with the
120-second / 256 MiB planner bound and real memory admission. Shared Landlock,
finite cleanup, source/config/namespace/recipe checks remain authoritative.
No separate lexical checker, compiler, generic header export, new flag or
research replay is permitted. Source child output is a new `source-001/plan`
directory under this worktree; all supervisor logs stay in its parent.

Preserve APFS's existing flag at argv243 and only the reviewed resource-root
operand at244. No old worktree, wave20 result, corrected diagnostic, source,
header root, index, sidecar or recipe is edited or credited to this profile.
Do not provide resume, approval or allocation arguments to a source plan.

Report the actual plan/hash, input-bindings/hash, selected90, original owner,
new experiments/worktree, resource/cleanup result and absent proposed actual
`resource-v1/execute-001` immediately to root. Actual compilation waits for a
separate root allocation; no kernel/guest/native/phone result follows here.
