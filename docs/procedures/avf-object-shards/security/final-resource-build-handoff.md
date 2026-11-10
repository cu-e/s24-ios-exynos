# VM-019 actual final-resource security build handoff

Original owner: `codex-guest-exec-20261106-dd`; task VM-019 remains in progress.
Branch/worktree: `team/vm-019-resource-final-20261106` /
`worktrees/vm-019-resource-final-20261106`, base
`e8ec6cd5f42a8b97c81c440303a0f8a6f5078a30`. Only the original security fixture
and procedure paths are changed. No worker publication/common checks, task
closure, global queue release, link, QEMU or phone operation occurred.

The exact new root31 direct `python3.12 -s` launcher argv ran once under the
separately planned actual `VM019FINALBUILD-002`, with canonical EV9929, unchanged
1200-second launcher64e7 and explicit `project-budget-v1`. Source plan ced65 was
reused unchanged by explicit root instruction; no source-plan rerun, resume,
old-object credit, source/cap/flag change or automatic retry occurred.

PID/session 172089, start_ticks 59876070, observed `/proc` start
`2026-11-06T07:40:46.700000+00:00`, are preserved in wave31-launch-record.json.
Engine start metadata is `07:40:47.749213+00:00`. All 23 real compiler commands
exited 0; their first/last starts are `07:40:58.166537` /
`07:42:04.648478` UTC. The direct launcher exited 0 and all 23 actual ARM64
Mach-O object records pass. There are 7,227 actual dependency edges over 394
distinct paths and 2,775,784 object bytes. Object/dependency/sidecar hashes were
streamed and matched their existing engine records; no object was recompiled.

Exact immutable authorities and outputs:

- Root grant31 receipt SHA256 `12dcd2b72949a0c0717a6eda4a5ba592f35ffa3ea40bb98ea43052b5bb9352b9`.
- Allocation SHA256 `61dd3304959b01194da5599356a466df4c81fe491060a875778ec1f7c59bd09e`.
- Approval SHA256 `3300a3e696f47d4bffa2ce73d078d7f7b2e10f6b38a175412be64c448c9094e5`.
- Source plan SHA256 `ced65ff92f11b4faa70c07678f8d1a224d34cca080b6500d8c5b9678fd0c8ff7`.
- Actual plan SHA256 `3189868c3e0cc5ac17021f8d2e73a09bbcff1b3d69627e33d9303281d48db35f`.
- Actual/source input-binding SHA256 `295e6edab63199b6ee1bcd245d43ede66dcb1c1429edc599389bc53f10307406`.
- Raw engine evidence SHA256 `887a65812790c87a00f26cd058c53fcf53aede6100a30b355e73bb17c3e8df4b`.
- Conventional capsule SHA256 `cdb45d30ee1fbbaee15c6da78718a1f6008b7e9f2d92f04701327073a13f35ad`.
- Object manifest SHA256 `96f2d01eefbc152a478400e94e617eb07cd6841fb90482d1ee8b834cdbdac952`.

Raw evidence is under
`artifacts/avf-object-shards/security/final-resource-execute-002/runner/evidence.json`.
The conventional capsule is `final-resource-build-evidence.json` in this directory;
the object manifest is `fixtures/public/avf-object-shards/security/final-resource-objects.json`.
All exact source/profile/helper/namespace pins, actual command references and
compiler dependency/record hashes remain in those capsules.

Terminal raw stdout SHA256 is
`d4f7b7e8f0832c2b57577954840151e36465e8c35260ba23de7dd2b236efc914`;
stderr is empty. Current executable image VmHWM is 176,787,456 bytes; maximum
command controller-plus-child RSS is 234,897,408 bytes. Maximum observed project
RSS is 787,324,928 bytes and project swap is zero. All command cleanup sets are
empty, own reservation status is complete and an independent retained PID/start/
session scan found no live process. The worker did not release the global queue.
Terminal raw hashes, cleanup and reservation facts were sent to root/CN before
this documentation. Final terminal snapshot SHA256 is
`a913fbc0c2111b9a1eed24aba594e195a77330fba83a87eb748d83484db2e2d9`.

Preserve grant30's BUILD001 pre-compiler refusal separately: raw evidence a4cceb18
and its original output remain unchanged and recorded FAIL. Grant31's initial
receipt-reader KeyError occurred before execution; it is preserved in the launch
record and the actual invocation count is one. An initial terminal metadata
approval-label typo is retained in its original snapshot and corrected in a
separate final snapshot. Raw engine evidence and authority files were unchanged.

CN is assigned independent actual-object review. Keep VM-019 open until that
review, integrator acceptance/current common checks and explicit original-owner
closure authorization. These 23 objects do not establish a full kernel link,
provider/private ABI closure, XNU console, PID1, PSCI stop or native-device result.
