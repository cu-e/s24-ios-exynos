# VM-009 guest object executor

Owner codex-guest-executor-20261106-co; branch team/vm-009-20261106; base aac27cf.
Only tools/build/avf_kernel_objects.py, fixtures/public/avf-kernel-objects and
this procedure directory are owned. MAIN is the sole registry. No common checks
or publication run here; integrators use state/.integration.lock.

Consume the exact 1,080-row VM-008 manifest SHA256
 afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd
and ten disjoint shards in MAIN/artifacts/team-coordination/20261106-team/object-shards.json.
The genuine ARM64/DEVELOPMENT/BCM2837 QEMU recipes and their source/config/header
namespaces stay immutable. Only @NEXT_OBJECT_DIR@ and @NEXT_DEPENDENCY_DIR@ output
tokens are substituted, into a fresh owned output tree. No shell, Make, native
E1S recipe reconstruction, source patching, SDK fallback or provider invention.

Initial experiment covers source-only graph/shard validation, bounded streaming
hashes, actual prior guest-object/dependency/metadata inspection, malformed-input
and resume rejection, and real write-confinement/finite-process controls. It
starts no compiler, linker or guest. Any compiler execution waits for VM-008
acceptance, independent runner review and explicit coordinator resource lease.
One serial job; all project compilers share two jobs/2 GiB new RSS; each light
compiler/controller <=256 MiB; three >=4 GiB memory samples one second apart,
finite admission/command/cleanup, no unrelated process or host-memory changes.

Child filesystem writes are confined to the owned output tree with unprivileged
Linux Landlock (ABI>=3 required, fail closed), including truncation/rename.
Read/execute access to immutable tool/source inputs is retained. Only standard
compiler recipes are admitted. The Linux primary interface is documented at
https://docs.kernel.org/userspace-api/landlock.html; no privilege escalation or
system policy change is performed. Negative controls target only owned fixture
sentinels, never shared source paths.

Source/config/tool/namespace/dependency/object hashes and real command exits are
required for successful object publication or unchanged-only resume. Failed and
resource-deferred attempts remain distinct. Genuine Mach-O and allocator metadata
checks do not establish a linked XNU image, console, PID1, stop, full SDK/private
ABI or hardware compatibility. No phone/ADB/MMIO/device action is authorized.

## Frozen interface and actual source-only result

CLI arguments (all paths explicit; sha values are full SHA256):

```
python3 tools/build/avf_kernel_objects.py --mode plan \
  --main MAIN --task VM-XXX --owner ORIGINAL_OWNER --experiment PLANNED_MAIN_ID \
  --manifest FROZEN_MANIFEST --manifest-sha256 FROZEN_SHA256 \
  --qualification VM008_DESCRIPTOR --qualification-sha256 DESCRIPTOR_SHA256 \
  --selectors ROOT_SHARDS_JSON --selectors-sha256 SELECTORS_SHA256 \
  --shard SHARD_NAME --out ORIGINAL_WORKTREE/artifacts/NEW_ATTEMPT
```

`execute` has the same arguments plus `--approval FILE --approval-sha256 SHA`.
The approval must bind the independently reviewed exact executor SHA, real root
lease text, runner_reviewed=true, max_jobs_per_executor=1,
max_total_project_jobs=2 and max_total_project_rss_bytes<=2147483648. The MAIN
VM-008 task must be done. A descriptor records authorization; writing booleans
is not permission. Integrators/root publish that binding after independent
review. The caller must honor the actual lease, including expiry/stop requests;
this tool is a serial compiler executor, not a global lease scheduler.

Optional `--resume REPORT --resume-sha256 SHA` uses a new output directory and
reuses only successful exact input keys. It verifies the original record hash,
object hash/ARM64 metadata, dependency-file hash, source membership and all
current dependency/namespace hashes. Reuse copies bytes without modifying the
prior output; its preserved dependency rule still names the original compiler
output and is explicitly recorded as dependency_original_target. Failed or
changed work is never silently reused. Original command provenance stays in the
sidecar. There has not yet been an actual VM009 compiler/resume execution.

Sources, config products, tool and include namespace bind before any child.
New or missing files that can change header resolution invalidate the namespace.
Missing genuine optional -I roots are retained as absence bindings, not repaired
or deleted; their later appearance invalidates the key. Required cwd/source and
resolved compiler dependencies must exist. Actual execution discovers its own
conditional dependencies; a source plan does not claim that every TU compiles.
Only the two declared output tokens change. Compiler flags, order, source path,
cwd and genuine custom builtin capability remain intact.

Each command has three >=4 GiB samples one second apart, a finite45 s admission
window and120 s command deadline. Current controller plus owned-session RSS is
sampled every25 ms, bounded256 MiB and checked for floor/deadline stop. Linux
VmRSS/VmHWM gate the current exec image; inherited launcher ru_maxrss is separately
reported because it can exceed1.7 GiB before this process allocates anything.
Large binary/source hashes stream through bounded buffers. A successful child
must leave a genuine ARM64 MH_OBJECT with bounded load/section/relocation/symbol
extents and nonempty allocator metadata for OSData. Actual failures and partial
artifacts remain hashed, and all remaining live owned children are stopped.

`fixtures/public/avf-kernel-objects/check.py` ran source-only experiment
VMOBJCTRL-002: **1120 checks passed**. The actual plan bound6721 source/config/
header/tool inputs,32 existing search/source roots,4 absent genuine optional
roots and all1080 source recipes, selecting23 security IDs as the emitted plan.
The ten-shard test separately verified full union/disjointness and all1080 exact
output substitutions. Current plan exec-image VmHWM was101539840 bytes;
controller+child peak125526016 bytes. Fixture controller VmHWM75341824 bytes is
separate from inherited ru_maxrss1803624448 bytes. No compiler/linker/QEMU started.

Validation inspected real archived VM008 OSData/startup ARM64 objects and real
compiler dependency files, including nonempty allocator metadata, mutated real
object bytes/architecture/load commands, host ELF rejection, malformed/changed
cache/dependency/selection/output inputs. The authored cache-sidecar test wraps
an actual prior compiled object; it is explicitly a boundary fixture, not an
invented historical VM009 compile or production-resume claim. Actual Linux
Landlock denied direct and symlink truncation of owned outside sentinels while
allowing inside writes; real exit7 and a real0.4 s timeout were retained with
complete cleanup. The first schema-lookup failure is preserved in controls-session1.

The qualified-runner.json descriptor points to exact source/control hashes and
pending review boundaries. Provider/PID1 helpers outside the frozen1080 graph
may reuse reviewed `run_child(argv,cwd,owned_out,label,supervisor,timeout<=120,
admit=True)` plus streaming sha and object/dependency helpers. Their producer
must separately validate owned output, genuine tool/source/profile bindings and
root execution authorization; that function alone is not a provider plan ABI,
PID1/executable validator, QEMU launcher or authority to execute. No provider
rows are invented inside this direct-object manifest.
