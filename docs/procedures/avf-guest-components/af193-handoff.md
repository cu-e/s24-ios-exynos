# VM-036 final accepted-process policy handoff

Original owner: `codex-guest-next-executor-20261106-dz`; keep `in_progress` until
explicit integration/common/root acceptance. Worktree
`worktrees/vm-036-dz-af193-20261106`, branch `team/vm-036-dz-af193-20261106`.
All earlier physical sources/capsules, including fix1/fix2 and the pre-adoption
intake, remain frozen. No compiler, archiver, loader, guest, broker reservation,
common check, publication or original-owner task/plan write occurred here.

## Exact source and receipts

Adoption source: `c931581ef7cb0bb2dc9e0874c98226443b2d1113`, following the
metadata-only intake `299ef75f5d0df20857c51e549cd00a332795dd94`.
Adapter SHA256: `e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa`.
Policy SHA256: `748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348`.
The only source changes are its policy digest constant and four accepted-receipt
names in `prepare`; every other existing function is byte/AST-identical to the
independently accepted `d5553d0`/`3ae89e8a` source. Policy changes select the one
final accepted process and four actual receipt pins; all old source/unit/tool/
namespace/compiler/archiver/component metadata remains unchanged.

The physical process is
`worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py`, SHA256
`af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.
Actual MAIN publication is `75fe3857c443c7e631bbd8cf838f7e48cc315844`.
Common capsule SHA256:
`0b494bff69df774ff8047864077b88117632ab99b196e132776fca952e769a26`.
Root marker SHA256:
`e3de989a256bcbba27815c1ea244f7b5b8469cf5002ed5fed5dfabe69b2fe237`.
These are actual 170-test/exit-0/empty-owned-after/lease19-released receipts,
not inferred source acceptance. The policy acceptance flag applies only to
this accepted process API; no component lease or product is implied.

## Actual focused evidence

`AVFCOMP-003` passed 24 focused checks in 1.4036 seconds, sampled combined peak
127,475,712 bytes, zero owned survivors. It verifies exact source delta/API/
receipt bindings, wrong actual policy/acceptance bytes, wrong engine digest and
caller rejection, unchanged old recipe/cwd/filelist/input-binding bytes, and
stale real-plan rejection before reservation/mkdir. The last guard uses an
explicitly labeled negative-only budget/authority dependency fixture comparing
two actual retained CLI plans; it neither impersonates owners nor reserves a
real slot. Historical 88/12/38/21/86 matrices were not repeated.

One actual source-only CLI plan pair passed under the serial light supervisor:

| Component | Plan SHA256 | Input-binding SHA256 | Child elapsed / sampled total peak |
| --- | --- | --- | --- |
| Firehose | `5221e312a27f3a73eb808148c19f8b05ad9a3d06ad747096dca59f976b3bbd7b` | `eee4fa11fb99d4775c63693fbefe7d702c102dff52dbc5364f44f39d8242b9ba` | 2.1650 s / 120,930,304 B |
| pthread | `288b255bfb5d38798a6889a7569596e5f04401752f3230e60c470017cbaa94bc` | `683311bdafbd5d9c5b33462bb4ab7dc14eb5840944c31327b0dea731319ec44f` | 1.6603 s / 80,314,368 B |

Plans are VM036-owned review inputs in
`artifacts/avf-guest-components/af193-plans-001`; they are not cx/cy's execution
plans. Full input-binding bytes equal the historical pair. The raw four-command
units124384/35d7, source argv/cwd and filelists remain immutable, avoiding the
unit/adapter digest cycle. Originals must derive their own new plans/experiments
after the final reviewed adapter, and root must bind those hashes in its grant.

Final capsule:
`worktrees/vm-036-dz-af193-20261106/artifacts/avf-guest-components/handoff-af193-001/evidence.json`
SHA256 `5f611bab6b11db8fe5af3595fc362882c4a3d6dcc2f994b6c9709dac6525a48d`.
It indexes 25 new/reused direct artifacts and links the accepted prior capsule
without rehashing/replaying its complete historical matrix. Source and policy
hashes are stable before/after controls. INT-003 separately reported 20 narrow
independent adoption checks PASS, with no bounded P0/P1/P2; its formal final
review packet is being finalized against this frozen source and capsule.

## Remaining boundary

Actual API signatures are unchanged: `ProjectBudget(args, data, executor_sha256)`,
`project_approval(args, data, *, executor_path=None)`,
`load_project(path, expected=None, maximum=67108864)`, and
`run_child(argv, cwd, out, label, supervise, timeout=120, admit=True, budget=None)`.
No second allocator or process engine was introduced. Components retain a serial
256 MiB slot and original typed product/report schema. Absent product descriptors
remain absent; the later actual execute report provides real object hashes/
file sizes/dependencies/depfiles/probes/definitions/imports and exact ordered
archive member hashes/definitions only after successful commands.

INT-003 may stage the exact source/review series on accepted75fe while the six
compiler wave runs. Publication/common must wait for root's next serial boundary.
Actual cx/cy component work still needs final adapter/common/root acceptance,
new original-owner plans/experiments and an exact shared allocation/approval.
Actual load mappings, component products, callback/layout/alias ABI and full
kernel/native/private-ABI/FIPS qualification remain unmeasured or unqualified.
