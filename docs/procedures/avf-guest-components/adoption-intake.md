# VM-036 once-only process-policy adoption intake

Prepared by original owner `codex-guest-next-executor-20261106-dz` in the separate
`worktrees/vm-036-dz-intake-20261106` worktree. This is documentation and input
intake only. The adapter, policy, original component units and all frozen
worktrees remain unchanged. No new controls, component plans, broker reservation,
compiler, archiver, loader, QEMU, common check or task closure is authorized here.
The machine-readable bindings are in `fixtures/public/avf-guest-components/adoption-intake.json`.

## Accepted source inputs and pending publication

INT-003 independently accepted adapter source
`d5553d007ff1da656b3702ce84f92b67df77ce5b`, documentation through
`fd5ae5588033e53a0b85b705b56969977db667c1`, in review commit
`fa310c575da8d638f06a22b9f025ccfcccd12fd4`. Its 21 targeted actual regressions
passed; all three P2s are closed, with no bounded P0/P1/P2 outstanding.
This reuses that verdict and the author's existing 38/88/12 checks; no matrix
was repeated. Source acceptance does not establish actual component products.

The adapter's frozen physical path is
`worktrees/vm-036-dz-fix2-20261106/tools/build/avf_guest_components.py`, SHA256
`3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f`.
Its capsule is `artifacts/avf-guest-components/handoff-003/evidence.json` in that
worktree, SHA256
`903370a0613e1e3c1c415d9910916d93645ec325879bf788f636b9b1afad8454`.
The independent acceptance capsule is the platform integrator's
`docs/integration/platform/component-adapter-review-20261106/evidence-pass2.json`,
SHA256 `1d45e2fb59d237b3e4315d1d90ed813fad3e34d4642d825cb7a50a0f5bad378a`.

The one future engine pin is the physical VM-039 file
`worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py`, SHA256
`af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.
Its source commits are `74ada78601a16938ba4fdf9414054e937b703f22` and
`852ad47eb4a8fe917cbc60675e7f2ae1f847d2e5`. REV-036 source acceptance is capsule
`7e970c90e4b50337d53ef0fa6c0297c53923ef4eab3ff8308c05c4115fd7156b`.
That review independently established that the accepted EFE budget API/guard
ASTs remain unchanged, including `ProjectBudget`, `project_approval`,
`load_project`, stable admission and `run_child(..., budget=...)`.
No intermediate 42f/6caa/EFE pin will be adopted by this adapter.

INT-002's reviewed publication candidate is
`75fe3857c443c7e631bbd8cf838f7e48cc315844`; its plan SHA256 is
`1b562c2d5f3f5a06011bef8d909e898c95f4827f21b53737227b9fcb387e77b0`.
A prepared candidate and independent source verdict are not publication or
common acceptance. The actual publication receipt, common PASS capsule and
explicit root acceptance remain null in this intake. Wait for those exact
receipts before any policy adoption. Do not infer acceptance from HEAD movement.

## Preserve source units; derive new execution plans

INT-003 explicitly prefers the existing layered contract:

1. Keep the full raw four-command units `1243849185135bb9ab7f861faf4d8fe2fed0c9dcae1e57165a2e9ff7a86008dc`
   (Firehose) and `35d7f9a7f2db1db41d8c5c0e83423c1d0d00feff3788d16e3b086bb362f0699b`
   (pthread) as immutable historical recipe inputs. Preserve original source
   plans, filelists, source/cwd/header/tool bindings, experiments and old outputs.
   Their historical process metadata is not current execution authority.
2. After the exact VM-039 publication/common/root acceptance, dz prepares one
   narrowly reviewed policy update selecting the physical AF193 path/hash and
   its accepted engine receipts. Only then can the policy acceptance flag and
   corresponding policy digest constant change. Freeze the resulting adapter.
3. Original cx/cy owners generate NEW derived source-only execution plans using
   that exact final adapter. The plan already separates the historical unit pin
   from `executor_sha256` and `process_policy`; record the new raw plan hashes.
   The adapter owner never writes their plans, experiments or task metadata.
4. Root/integrator accepts the final adapter publication/common boundary and
   approves the exact new plan hashes, final caller digest and engine digest in
   the one shared allocation/approval contract before actual component execution.

Do not add the final adapter digest to a raw unit that the adapter itself
hard-pins: that would create a circular hash dependency. The final caller digest
belongs in the new derived plan and external root approval. Accepted *engine*
receipts precede the adapter freeze; later adapter publication/root acceptance
stays in the external acceptance/allocation chain. No self-referential receipt
is embedded in its own source policy.

The source recipe units retain their exact argv and namespace bindings. An
AF193 process pin alone grants no component header/profile/root substitution,
no synthetic 1080-row graph admission and no old object reuse. Any genuinely
needed component recipe/input change requires separate exact original-owner
preparation and independent qualification; it is outside this narrow adoption.

## Original owners and execution boundary

Firehose remains VM-020, owner `codex-guest-exec-20261106-cx`, worktree
`worktrees/vm-020-20261106`; pthread remains VM-021, owner
`codex-guest-exec-20261106-cy`, worktree `worktrees/vm-021-20261106`.
The original fresh output roots are recorded by the source units, and the
executor must recheck live MAIN task ownership, literal paths, planned
experiment, canonical ancestry, absence and exact output identity before mkdir.
New original-owner experiment/plan/root-slot references remain null here.
No component execution directory was created by this intake.

Reuse the one accepted shared project broker and exact API. Components retain
one serial child, a 256 MiB controller-plus-child RSS cap, a separate 2 GiB
virtual-address cap, three one-second >=4 GiB memory samples, <=120 seconds per
compile/archive and <=30 seconds per trusted loader observation. Root supplies
finite whole-attempt expiry and cleanup authority. The global six-job/6 GiB
ceiling includes the broker's light-work reservation; it is not six jobs per
component. No eight-job trial is granted here.

Before root allocates execution, the platform intake must bind final adapter/
engine/source-plan digests and unchanged command/filelist/source/header/runtime
identities. Actual loader mappings, dependencies, ARM64 objects/probe records,
exact archive member bytes, swaps/RSS/command exits and cleanup must still be
measured in the original owners' later experiments. Source acceptance does not
qualify callback/layout/VM aliases, kernel linking/startup, private Apple ABI,
native hardware, FIPS or side-channel behavior. VM-036 remains `in_progress`;
closure needs the separate explicit integration/common/root acceptance.
