# VM-035 review handoff

Original owner codex-guest-namespace-cost-20261106-dt; worktree/branch
worktrees/vm-035-20261106 / team/vm-035-20261106; base36c7dce7c18a2cefbf5ae41032915b2a8a5a8006.
Own only tools/build/avf_kernel_objects.py plus the namespace-cost fixture/docs.
Original physical VM009132135 helper and all existing jobs/artifacts remain
unchanged. No MAIN source/publication/common checks, compiler, QEMU or phone
operations. Do not publish/adopt until a root-approved BUILD BOUNDARY.

One five-line expansion changes only the final namespace missing-index scan:
parse each index name once, compare full root-part prefixes. All normalization,
absence/shadow/symlink/missing checks, current stat/ctime/digest behavior, flags,
metadata builtins, source/profile/tool hashes, input keys, output/role policy,
resource/lease policy and resume checks remain byte-identical elsewhere.

Actual immutable VM018 context:53976 index entries,32 existing roots,4 absent
roots,6721 bindings. cProfile original178.243359 s wall/175.927211 CPU versus
candidate7.802603 s wall/7.011098 CPU. Original is_relative_to1,633,334calls/
170.252371 s cumulative. Thus the bottleneck was measured, not inferred from a
synthetic filesystem. Like-for-like profiled bind is~22.84x faster; no claim is
made for unprofiled future workloads or overall kernel-build/boot performance.
Actual SHA/stat/resolve/get counts match. Memory guard peaks126488576 and
126656512 bytes with no survivors; no cross-run validation cache exists.

PASS19 equality/real-FS checks cover exact fresh namespace/input-binding bytes,
the actual frozen13-ID selected plan and all1080 validated graph input-key/argv
projections through the unchanged bind tail. Only owned output roots normalize.
The projection is a value-equivalence proof, never operational selector expansion
or compiled-object evidence. All actual files are independently rehashed after
measurements. Missing/shadow/changed, symlink, component-prefix, absent-root
appearance and real ctime-after-restored-mtime controls preserve behavior.

Artifacts under worktrees/vm-035-20261106/artifacts/avf-namespace-cost:
original-session1 and candidate-session1 each contain reviewed-supervisor
commands/exits/cleanup/RSS, measurement JSON, raw cProfile and actual binding/plan
bytes. equality-session1 retains the comparison-fixture relative-path failure;
equality-session2 is PASS. No measured run was repeated or relabeled. The old
physical reviewed132135 source is rehashed before/after and kept unchanged.
Qualified fixture descriptor carries exact source/report hashes.

Ready for independent review, integrator common checks/publication at an approved
boundary and explicit root acceptance. Task remains in_progress until accepted;
original dt alone completes. No new task claim or operational build lease is
inferred. Full1080 compilation, production cross-version resume, kernel link,
console, guest stop, private Apple ABI, SDK or native hardware are unqualified.
