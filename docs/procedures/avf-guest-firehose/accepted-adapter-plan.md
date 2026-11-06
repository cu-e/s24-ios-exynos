# Original-owner firehose plan through accepted component adapter

Original owner: `codex-guest-exec-20261106-cx`, VM-020, original worktree
`worktrees/vm-020-20261106`. New experiment: AVFFH-002, initially planned.
The experiment remains planned through source-plan preparation so the same
original-owner authority can be checked before future admitted execution.
No actual component result or task completion is claimed by this document.

Root accepted MAIN `27352788619e594314a1a85a12f07e82fc279184` after 170 common
checks, evidence `c92f2b3ccbae80907df4bb1fc35b861184088331b7c172657e09ed0e582a5c6c`.
The physical immutable adapter is
`worktrees/vm-036-dz-af193-20261106/tools/build/avf_guest_components.py`, SHA256
`e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa`.
Its physical policy SHA256 is
`748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348`;
the selected prospective process boundary is the frozen VM-039-ej AF193
implementation. There is no budget-044 repin or implicit process upgrade.

After original-owner AVFFH-002 registration, run only this source-plan CLI:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -B -s \
  /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-036-dz-af193-20261106/tools/build/avf_guest_components.py \
  --mode plan --main /home/egor/dev/pet/s24-ios-exynos \
  --component firehose --task VM-020 \
  --owner codex-guest-exec-20261106-cx --experiment AVFFH-002 \
  --out /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/accepted-adapter-plan-session1/plan
```

`derive-accepted-adapter-plan.py` invokes that exact CLI as one source-only
child through accepted AF193 `run_child`, without a project budget or execution
approval. The existing common process engine supplies three stable 4 GiB
MemAvailable samples, a finite deadline, 256 MiB aggregate controller/child RSS
monitoring, owned-output Landlock and finite cleanup. No alternate process
engine is implemented. All output/log/temp/home files stay under the fresh
`accepted-adapter-plan-session1` directory. Missing admission preserves an
inconclusive resource-deferred receipt rather than starting the child.

The old unit `bounded-plan-session1/plan.json` (SHA256 `124384...`), original
three-TU source recipe `preparation-session3/compile-plan.json` (`f6c1...`), and
original provider-only filelist stay physically unchanged. The proposed future
component output `docs/procedures/avf-guest-firehose/execution-session1` must
remain absent throughout source planning. The actual adapter produces a new
`execution-plan.json` and `input-bindings.json` carrying its accepted final
adapter/process/runtime identities; this is a derived plan, not an overwrite.

Future execution must call this same frozen adapter with `--mode execute`, all
original task/owner/experiment flags, the original future execution directory,
and the exact root-created `--approval`/`--approval-sha256`. A template is saved
in the source receipt; placeholders are not authorization. Root will allocate
one serial compiler only after intake of both new component source plans.
No compiler, archiver, loader, QEMU, common check, project budget admission or
actual execution is part of the current source-only plan preparation.
