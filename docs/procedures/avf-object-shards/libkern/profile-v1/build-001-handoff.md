# VM-014 wave20 object result and accounting qualification

Original owner `codex-guest-exec-20261106-cw`, experiment
`VMLIBPROFILE1-001`, worktree `worktrees/vm-014-profile-v1-20261106`, branch
`team/vm-014-profile-v1-20261106`. Root granted exactly one 77-object attempt
under `guest-kernel-six-wave-20261106-20`, immutable allocation SHA256
`9281d907b5e2e11788f1bc1e5da31be2ac6841ddd8c304e65019da67cdb3ab13` and
VM014 approval SHA256
`6156b8293850119dbb5dc9581eabf5a81f8a27bd8173fb94cd9d94294e0e608c`.
The invocation used accepted AF193 helper bytes, root's pinned 442b launcher,
explicit `project-budget-v1`, the sealed new-profile source plan e7092f34 and
fresh `profile-v1/build-001` output. There was no resume, retry, input change,
extra compiler tool, QEMU, MAIN/common check or global queue release.

All 77 actual compiler commands exited 0 and produced 77 validated fresh ARM64
Mach-O objects with 648 unique actual dependencies. Every object record,
object and dependency-file digest was streamed against its recorded identity.
Both historical OSKext.cpo and log.o failures now have genuine successful
compilation and actual dependency entries for the exported Firehose header
SHA256 `14be8d31d66882894037431ec5df75a88e39e2100e8246a7df20ac2f708b6cb2`.
The old worktree's 75 successes/two failures remain unchanged and receive no
new-profile credit. The machine-readable new object catalog is
`fixtures/public/avf-object-shards/libkern/profile-v1/build-001-objects.json`,
SHA256 `155c596c6a54911886e8e929473eeee1907a919363cb728b10065a002135a904`.

The unchanged raw shared-engine capsule is
`artifacts/avf-object-shards/libkern/profile-v1/build-001/evidence.json`, SHA256
`31d820a4413a8a5711ac1e20481bd1086576cd75f9e7eacda7dbd85376698c00`.
It reports pass and no top-level or reservation-release error. These literal
fields do **not** establish that every project-budget boundary passed:
INT002 independently found one preserved command-level accounting error at
zero-based command index 12, OSKext.cpo:
`project_after_error = ValueError('Project budget lock acquisition timed out')`.
The compiler exit, object validation and recorded owned-child cleanup pass;
the post-child accounting sample failed. The other 76 commands have no such
error. Root and the VM044 author/reviewer were informed; this worker does not
patch the shared consumer or rerun any source. All original bytes are retained.

The separate object-level result `build-001-result.json`, SHA256
`16b114c45d92ac6eddffb81ccbf5eacd6dd6f7ab631b87ac7bfe2bf9bb00b5e5`,
documents the actual object/hash/dependency success. The authoritative qualified
experiment result is `build-001-accounting-result.json`, SHA256
`be209e98bec308ceed6c4627b5670285ad15f41219adf10c4a3f7979def03b68`,
with overall outcome **inconclusive** pending root's bounded accounting
acceptance/common. It preserves and links the raw pass rather than rewriting
or silently reclassifying the measurement in place.

Observed combined executor RSS peak was 254,070,784 bytes; current-image
controller VmHWM was 130,363,392 bytes. Minimum recorded admission memory was
13,276,766,208 bytes; all commands obtained three-sample admission. No child
reported a resource/deadline stop. Project observations during this executor
peaked at 1,320,714,240 bytes RSS with zero sampled project swap; they are not
the complete six-job-wave peak or proof of host swap causality. All 77 recorded
child after-lists and session PID checks are empty/absent, controller PID
3492551 is absent, and the outer tool session 99784 exited 0. Root retains all
authority over the global queue/allocation. No blanket all-budget-boundaries
pass is asserted.

Keep VM-014 in progress. Record VMLIBPROFILE1-001 with the qualified inconclusive
result, retain the exact positive object catalog for integrator intake, and
await explicit root bounded acceptance/common before any original-owner task
closure. No linked kernel/archive, full SDK/private ABI, guest/console/PID1/stop
or native phone result is established by this shard.
