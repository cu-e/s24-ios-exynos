# ROOT97 root-owned lease correction

Source review 19b00ecfc32c4f4d334ae9543d840804b0d70166bb0478dc3d8613c78061b2fe
found three P2 issues in prospective adapter7d71513: reservation write preceded
cancellation/finally setup; blocking locks and in-place queue writes lacked finite
atomic invariants; late cancellation signals were not recorded and could leave a
pass outcome. No runtime reproduction or actual work occurred. Original commits,
packets001/002, source evidence and unchanged accepted plan remain preserved.

The new adapter has no resourcequeue write, reservation/release, integration lock
or flock operation. Root independently establishes one exclusive heavy lease and
creates its separately hashed, unexpired approval before launch. Read-only lease
checks require exact id/task/owner/experiment/plan_sha256/runner_sha256/output and
resource fields from the approval, with no light_compile/QEMU lease. The same
checks run before every stage. Root alone independently inspects owned sessions
and releases the lease after zero survivors, including preflight or cancellation
failure. Adapter evidence explicitly states root ownership and no self-release.

The original owned_cancellation and deferred cleanup scope encompass creation of
the fresh measurement namespace, setup, all work and terminal publication. Signals
are retained as cancellation_signals; any observed cancellation forces failure,
including signals arriving in postwork/hashing/finally. The handler remains active
through evidence publication and terminal output. Root must require an actual
normal exit0, passing capsule and independent zero-survivor result; a pass capsule
alone never substitutes for actual process termination. A final observed signal
also changes the exit to1 and persists failure. Only a successfully created owned
measurement namespace may receive writes.

Everything else remains the reviewed packet: plan1df5078c, 26 frozen source/tool
pins, three exact existing supervision helpers, eight source-hook controls, one
ordinary23-command builder with old21 vectors plus log check/apply, genuine
ELF/Image inspection and twelve negative derivatives. Work guard600seconds,
external root690seconds, combined controller/descendant RSS2GiB, one serial
compiler, inner child120seconds, explicit private environment and fresh outputs
are unchanged. No new timer, engine, builder/inspector/source controls or target
flags were added. This preparation executed only source AST/hash checks.

The adapter's --root-grant and --root-grant-sha256 require a root-created approval
with id e1s-loader-log-builder-20261106-97; task STR-031; original SR31 owner;
experiment STR031BUILD-001; approved_by root and approved true; frozen plan SHA;
latest runner SHA; exact measurement output; max_jobs1; max_owned_rss_bytes2147483648;
whole_seconds600; external_seconds690; actual future timezone-aware expires_at.
The active root heavy record must carry matching id/task/owner/experiment,
plan_sha256/runner_sha256/actual_output/max_jobs/max_owned_rss_bytes/whole_seconds.
Root may copy the actual approval into its own atomic lease record. The inactive
source grant-template is documentation and cannot authorize execution.

Object/report are observed post-build same-byte content bindings; no prior object
manifest/current-path identity is invented. Kernel0011/12 physical ownership,
phone/native execution, mappings, persistence, retrieval and recovery remain open.
