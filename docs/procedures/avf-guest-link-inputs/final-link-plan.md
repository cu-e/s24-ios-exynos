# Genuine DEVELOPMENT final link plan

This is a read-only VM022 preparation under the original cu owner. Implementation
commit d66758627d54144a414ae9a2366538ce7482dbe5 and the exact executed builder have
SHA256 21af2536f639c10ab655d0a6d64348398f8d5a771675d248a4553100a3d0c8db.
The authoritative machine plan is
worktrees/vm-022-20261106/artifacts/avf-guest-link-inputs/link-plan-2/final-link-execution-plan.json,
SHA256 a14c985397c125f99ae94007454021bd6b17a5ad10166c1441fb6b9eead4567c.
It contains every exact future argv,1080 ordered copy mappings and the complete
missing-input checklist. Its executed and ready_for_link fields are false.

Current consumable bytes were checked against the pinned passing raw executor
capsules, per-object sidecars, saved expanded execution-plan argv/input keys,
actual source/object/depfile SHA256 and ARM64 MH_OBJECT headers:

| Producer | Actual objects | Existing owned output root |
| --- | ---: | --- |
| VM018 platform-support | 13 | worktrees/vm-018-20261106/artifacts/avf-object-shards/platform-support/execute-001 |
| VM015 osfmk-machine | 77 | worktrees/vm-015-20261106/artifacts/avf-object-shards/osfmk-machine/execute-001 |
| VM013 iokit | 104 | worktrees/vm-013-20261106/artifacts/avf-object-shards/iokit/execute-001 |

Under each root, actual objects are objects/EXACT_ID, dependencies are
dependencies/EXACT_ID.d, and expanded commands are in execution-plan.json.
The three raw capsule SHA256 values are respectively
cacbf88ca57491cac477e186da8293a1e99c813fb3ec4758609890685eda6f80,
781466df96b2c38d81f486e1183b658a00e679089f337c221493f2f35eca8494 and
d280910f050ef5ea0eaa8261ed6ab78d4e381cf68fc86310014e07dca397433c.
These194 products remain unchanged; no staging or segment rewrite ran here.
Seventeen actual IIG implementation objects do not qualify Apple's private ABI.

The other886 IDs retain exact task/shard ownership and canonical
OUT/objects/EXACT_ID templates: VM010222, VM01190, VM012226, VM01477, VM016125,
VM017123 and VM01923. The common executor owner confirms there is no globally
assigned future execute root. Seven OUT values therefore remain unresolved until
new registered-owner/root receipts exist. No execute-001 path was invented for
these producers. The map contains null actual paths and explicit future-root
placeholders for those rows, preventing their promotion to available inputs.

The genuine command chain, entirely unexecuted, is:

1. After complete input admission and a root production lease, create only the
   proposed new VM022 execute-link-001 tree. Copy hash-qualified original objects
   into owned objects/COMPONENT/DEVELOPMENT paths and copy the accepted source-text
   all-kpi.exp, all-alias.exp, symbolsets.plist and version.c into stage. The plan
   records all1080 finite cp argument vectors; missing roots/hashes block886.
2. Run eight genuine configured component filelist recipes against copied
   objects, preserving exact component CONFIG_DEFINES, object order,14 HIB and
   bootstrap.cpo KLD/KLDDATA transforms. Mark only the already-qualified object
   and command-stamp targets old so filelist production cannot recompile them.
   LOG_LDFILELIST=: changes cosmetic host logging only. Record transformed hashes
   separately, and concatenate filelists in the genuine eight-component order.
3. Under a separate explicit compiler lease, compile genuine fresh version.o,
   lastkerneldataconst.o, lastkernelconstructor.o and nonlto.o from the retained
   top-level recipes. Preserve their actual empty inherited CONFIG_DEFINES context.
   Apply the genuine DATA-to-LASTDATA_CONST setsegname operation to the owned
   lastkernelconstructor object. No historical tail object is a guest input.
4. Link mach.development.bcm2837.unstripped using the exact source-built Clang,
   explicit qualified ld, all genuine DEVELOPMENT flags, aliases, symbolsets,
   segment order/protections,1080-object filelist and four fresh tails. Keep
   -lcc_kext, -lfirehose_kernel and -lpthread_kext. Do not add RELEASE export flags
   or unresolved-symbol suppression. All sources/tools/text/provider bytes and
   resource leases must be checked again immediately before execution.
5. The original Make dependency builds the optional static link archive after
   the image. Its exact genuine libtool recipe would contain1083 members and
   exclude nonlto.o. It is not a prerequisite for the console-only payload.
6. Independently validate the real image's bounded Mach-O commands, segment file
   extents, VM order/protections and nonzero LC_UNIXTHREAD PC in executable memory.
   The shim requires nonempty segment VM addresses >=0xfffffff007000000. Actual
   image/payload/ramdisk physical extents must fit the matched shim's memory
   formulas under the separately leased256MiB guest. No image exists to validate.
7. The pinned source route is raw64-bit ARM64 Mach-O -> xnuloader/mkpayload.py
   XNUP kernel entry -> existing source-built AVF shim Image supplied as QEMU's
   -kernel, with XNUP as -initrd. No kernelcache, IM4P, SDK utility or proprietary
   container conversion is part of this route. The finite console-only packager
   vector uses --no-version and --cmdline=-v avf_exit=1, avoiding metadata subprocess
   discovery. Packaging itself still needs bounded memory/file-size admission.
8. A separate explicit root QEMU lease may use the recorded qualified binary,
   virt/gic-v3, TCG cortex-a76, one CPU and256MiB, with a60s timeout and5s owned
   cleanup escalation. No QEMU command ran here. Actual console, timer, MMU,
   device-tree, PSCI and stop gates remain required. Timeout is not boot success.
   The upstream wrapper's2GiB default is not used.

All thirteen compiled shim source/license hashes match the frozen VM008 donor.
The existing35,368-byte Image at
worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/Image has SHA256
283f6740424011959ebe03e71ce910a81bbfa3b7ba31c6395ab6f8aab77eaf87.
The qualified QEMU binary is
worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build/qemu-system-aarch64.
Their existing synthetic CPU handoff qualification does not establish XNU boot.

VM023's real287-member cc_kext archive is hash-bound at
worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive/lib/darwin/libclang_rt.cc_kext_ios.a,
SHA256 67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5.
The final driver vector adds its exact resource-positive directory at LINK ONLY.
VM023 measured the real driver's unconditional -lcc_kext rewrite; missing resource
silently omitted the archive even with exit0. Preserve source/header resource
selection during object compilation. Its47 archive-wide import candidates remain
visible, and actual pulled-member imports depend on the real link. This is a
compiler runtime, not a substitute for a crypto or pthread provider.

VM020 and VM021 archives are absent and unadmitted. The platform integrator's
current proposals, recorded in link-plan-inputs.json, are respectively
worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/execution-session1/libfirehose_kernel.a
(provider.o only), and
worktrees/vm-021-20261106/artifacts/avf-guest-pthread/compile-1/libpthread_kext.a
(kern_init.o, kern_support.o, kern_synch.o). Both need actual fresh
DEVELOPMENT/BCM2837/MAX_CPUS8/MAX_CPU_CLUSTERS1 profile/dependency/object/archive
and import/layout/alias review plus their own execution leases. The pthread
MACH_ASSERT/DEBUG/LTO-off policy and remaps remain its owner's responsibility.
Old native/E1S archives are not substituted.

The minimal blocking inputs are886 accepted objects and their seven receipted
roots, four fresh tails, both accepted fresh providers, actual complete symbol/
selected-runtime-member closure, independent plan review/root leases, and the
actual final image layout. Full VM002/PID1 additionally needs a reviewed owned
mockfs root/PID1 and valid runtime ABI. The source permits omitting optional
ramdisk for a console-only attempt; that omission cannot qualify PID1 or full
VM002 acceptance. No private ABI, provider fallback, fake image or boot result is
claimed. The task remains with original cu ownership and in progress.
