# Independent next components after VM-008

These are proposed work boundaries for the coordinator, not execution permission
or new task claims. No component below was built/linked/run by this handoff.
All paths below are read-only inputs. MAIN is
/home/egor/dev/pet/s24-ios-exynos. H is
MAIN/worktrees/vm-008-20261105/artifacts/avf-kernel-headers.

## Direct guest object executor

Consume H/handoff-1/next-full-object-manifest.json, SHA256
afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd.
It is a JSON array of 1,080 genuine guest object records. Row fields are id,
component, target, language, source/source_sha256, generated_input,
genuine_expanded_recipe, cwd, configuration/configuration_sha256,
bound_source/bound_source_sha256, status,
next_owned_compile_argv_template and
execution_requires_new_plan_and_resource_lease=true. Exactly 55 records are
generated: 34 osfmk MIG, 4 BSD (systrace_args/init_sysent/syscalls/newdoconf ioconf),
17 IIG. Source+recipe binding is not an object build pass. Replace
@NEXT_OBJECT_DIR@ and @NEXT_DEPENDENCY_DIR@ with new owned output roots and create
per-component directories; never write the published input cwd/namespace.
Inspect retained genuine recipe flags and source hashes before execution.

Use H/handoff-1/handoff-component.json and generated-export-manifest.json for
all 75 genuine generated raw exports. The complete unfiltered include namespace is
H/handoff-1/EXPORT_HDRS. Kernel core recipes retain raw private kernel interfaces;
do not replace them globally with the filtered installed framework namespace.
H/prepare-2/source/{xnu,scion} and
H/prepare-2/configuration/COMPONENT/DEVELOPMENT are the genuine source/config
roots; every current generated config product hash is in
H/handoff-1/guest-configuration-products.json. Fresh MIG modes live in
H/mig-1/{internal,export}/osfmk. Actual setup is H/setup-7/setup/include and
H/setup-7/build/osfmk/assym.s. Fresh candidate IIG pairs are in
H/iig-1/build/iokit/DriverKit. All 17 genuine IDLs generated, but only the actual
OSObject implementation is in this task's bounded successful compile set;
selected Apple RPC/private ABI remains unqualified.

The hash-qualified real-builtin compiler is
MAIN/artifacts/xnu-compiler-cxx-storage/source-build-session2/clang,
SHA256 7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82.
Board-neutral public tcsh/unifdef/mig/migcom are under
MAIN/artifacts/xnu-host-tools/generators-session2/prefix/bin, with hashes in
MAIN/fixtures/public/xnu-host-tools/generators-session2.json.
Do not reuse native 982 E1S objects or claim full compile/link from the ten actual
representatives. An executor can split component groups into separate owned
output directories; one integrator must establish a single coherent manifest,
actual errors and compatible selected tool/header/source contract before link.

## Firehose provider and header export

Use public source MAIN/references/xnu-kernel-firehose, pin
a641558f447659d90ad002ef0ee6f0212273fbfc. Relevant real files are
src/firehose/firehose_buffer.c, os/firehose_buffer_private.h and the source
kernel xcconfig. The source/recipe/probe reference is
MAIN/fixtures/public/xnu-kernel-firehose-headers/qualified-component.json and
MAIN/tools/build/xnu_kernel_firehose_headers.py. Stage fresh source/header outputs,
retain actual kernel/spi unifdef flags, and derive guest MAX_CPUS/cluster/layout
from the selected BCM2837 board context. The historical and current E1S archives
are read-only native evidence, not guest providers. Qualify actual guest provider
imports/layout before adding its archive to any guest graph.

## Pthread kernel component

Use public source MAIN/references/xnu-kernel-pthread, pin
a6c70ca0e544347a0377babf748f831577ec24f9. The already reviewed source ports and
source-only copy are under
MAIN/artifacts/open-kernel-inputs/typed-pthread-session1/pthread; the exact source
witnesses are MAIN/fixtures/public/open-kernel-inputs/typed-pthread-session1.json.
Retain source licenses and replay/copy only hash-qualified source contributions
into new owned storage. Actual recipe/callback/alias context is in
MAIN/tools/build/xnu_kernel_pthread_profile.py and
MAIN/fixtures/public/xnu-kernel-pthread-profile/qualified-component.json.
Do not invoke that existing CLI unchanged: it hardcodes native E1S product roots.

The new guest installed framework roots are
H/headers-final-1/installtree/System/Library/Frameworks/Kernel.framework/Versions/A/
Headers and PrivateHeaders. These are the proper filtered interface candidates
for this external component. Requalify callback types/layout, guest imports and
VM aliases against actual guest object definitions; old native callback/provider
success does not transfer by assumption. No old pthread .o/archive is a guest
input. Coordinate only new helper/output paths so this can run independently of
the direct-object executor without writing this header implementation.

## Archive/link and remaining provider integration

Board-neutral source-built linker/libtool/setsegname provenance is in
MAIN/fixtures/public/xnu-kernel-link-inputs/qualified-component.json; exact binaries
are under MAIN/artifacts/xnu-macho-tools/macho-session4/prefix/bin and
MAIN/artifacts/xnu-kernel-direct-tail/build-session3/setsegname. Rehash tools and
retain genuine guest DEVELOPMENT filelist/ordering/section rules. Generate fresh
guest tail/version/nonlto inputs coherently; old E1S archives/tails are references.
This graph does not include top-level direct tails/provider archives as compiled
products. Their real guest recipes/tool compatibility remain a separate stage.

Existing crypto executors own their public source/provider adapters. Consume
reviewed source-qualified inputs through a new guest provider assessment rather
than taking over their reservations, pruning native exports, inventing crypto
fallbacks or declaring native missing 37 resolved. Guest development's selected
requirements must come from its actual source/profile/object/link graph.

A genuine linked XNU image is still absent. Only after actual guest providers,
all required objects, link/image/entry layout and AVF shim/board contract are
qualified can a separately authorized bounded runtime task test first XNU
console, owned PID1 and PSCI stop. QEMU virt/source/compile results or a synthetic
payload cannot substitute for that execution. No phone/native device operation,
full SDK/private ABI success or VM-002 completion is implied.
