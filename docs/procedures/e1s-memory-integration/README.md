# E1S builder memory patch integration

STR-003 follows accepted STR-002, whose exact patch is
23b31c44ed9dba9c2da2e5b56ccbe97cd67fa41efff3ec032130eabca6718ae1,
frozen in6a1c05d4119acd5146d56d7fc9070742584140cd. Only the existing E1S
builder and this procedure directory are reserved. Pinned references, producer
patch/checker, compiler flags and product format remain untouched.

Source-only verification may read the current donor through existing
sources.verify, check exact patch identity and run git apply --check against an
owned three-file donor copy. This creates no target objects and does not invoke
the builder, Zig or any compiler. A real builder run requires separate explicit
root admission after exact source freeze/review. There is no phone/MMIO action.

Source freeze: only14 added lines in build(). Existing sources.verify is still
called before new output creation and still enforces origin, exact revision,
clean checkout and reviewed file identities. Existing run()/CLI/compiler flags
and product commands remain unchanged. After donor copy the builder reads the
patch once, checks exact23b31 identity, snapshots those bytes in fresh output,
records original patch path/source task/source commit/actual SHA/snapshot/target
and applied=false, then runs the check and apply through its existing logged
runner. applied=true is recorded only after both commands succeed. Missing,
changed or nonapplicable patch raises into the existing failed report path before
any target compile. No producer patch or reference checkout is modified.

Read-only git apply --check --verbose succeeded against an owned three-file
copy under this worktree; Git checked the intended nested copied paths. Donor
and copy hashes stayed unchanged. Syntax and diff checks pass; AST comparison
finds only build() changed. These checks do not execute the builder or establish
an actual build result. source-evidence.json is source-review evidence only.

Root next action, after exact source review/resource admission: invoke this
frozen existing builder with --root /home/egor/dev/pet/s24-ios-exynos and a new
--run identifier. The output report must show source_patch.applied=true, matching
snapshot SHA23b31, check/apply commands before every targetcompile and actual
loader/probe product results. Keep failures and all historical unpatched build
outputs. Root controls full build/compiler admission; this author has not run it.

Root requested one planned measurement STR003BUILD-001. build-plan-001.json
contains exactly one invocation of the frozen45522ff candidate builder, --root
MAIN and fresh --run str003-memory-20261106-001. It pins actual /usr/bin/python3,
/usr/bin/zig, /usr/bin/git, candidate builder/sources.py, MAIN sources.py, patch
and source registry; PATH is explicitly /usr/bin:/bin. Root's proposed budget is
2GiB aggregate RSS, one serial builder,600-second whole deadline and the existing
120-second child timeouts. This is a request, not an active lease or execution
grant. The author only registers the plan; root must admit and supervise it.
Probe+loader qualification remains distinct from an XNU kernel or physical boot.
