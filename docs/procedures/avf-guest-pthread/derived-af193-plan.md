# Original-owner plan through the accepted AF193 component adapter

AVFPTH-004 is a newly planned actual VM-021 component experiment owned by
`codex-guest-exec-20261106-cy`. It must remain **planned** after source-plan
derivation because the accepted adapter requires that exact status for a later
execution. Source-plan evidence does not record a successful component build.

Root accepted MAIN `27352788619e594314a1a85a12f07e82fc279184` and the 170-test
common capsule SHA256
`c92f2b3ccbae80907df4bb1fc35b861184088331b7c172657e09ed0e582a5c6c`.
The primary root marker permits fresh original-owner source plans and explicitly
withholds actual compilation and budget044 repinning.

The exact physical adapter is
`worktrees/vm-036-dz-af193-20261106/tools/build/avf_guest_components.py`, SHA256
`e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa`.
Its policy SHA256 is
`748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348`.
The selected physical process engine remains VM-039/ej AF193, SHA256
`af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.

After registering AVFPTH-004 in MAIN, invoke the adapter with `--mode plan`,
`--main MAIN`, `--component pthread`, `--task VM-021`, the exact original owner,
`--experiment AVFPTH-004`, and a fresh owned artifact output. The small launcher
`derive-af193-plan.py` performs only that one source-only child call through the
accepted AF193 `run_child` helper. Admission requires three stable 4 GiB samples;
the child and controller share a 256 MiB RSS ceiling and a 120-second child
deadline. There is no broker budget/approval flag and no compiler/archiver,
loader, QEMU, common check or publication command.

Historical raw source plan `96065...`, canonical freeze `bfb88...`, unit
`35d7...`, and original filelist bytes remain immutable. The original
`compile-1` component execution output must remain absent. Derived plan/input
binding files are new intake artifacts and bind the final adapter/policy/process.
Root will inspect both original-owner component intakes before granting a later
serial compiler allocation. This procedure grants no execute authority.
