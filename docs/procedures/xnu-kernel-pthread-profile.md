# Genuine pthread static component qualification

KRN-022, 2026-11-05. Owner `codex-kernel-pthread-profile-20261105-ag`.
Host-only source, build and object qualification. No phone operations occurred.
The component is ready for selected kernel link integration. A complete kernel,
selected Apple private ABI, runtime and native iOS support remain unqualified.

## Inputs and correction

Pinned libpthread: `a6c70ca0e544347a0377babf748f831577ec24f9`.
Pinned XNU: `c54f35ca767986246321eb901baf8f5ff7923f6a`, with the already
witnessed E1S source preparation and SGAP-001 coherent 982-object graph.
Primary recipes are [kext.xcconfig](https://github.com/apple-oss-distributions/libpthread/blob/a6c70ca0e544347a0377babf748f831577ec24f9/xcodescripts/kext.xcconfig),
[MakeInc.rule](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.rule)
and [MakeInc.def](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.def).
Local exact Git blobs and tool hashes are in the actual evidence capsules.

Earlier KLINK-003/006 mixed internal/raw kernel headers with kext inputs.
The genuine kext sets XNU_KERNEL_PRIVATE, MACH_KERNEL_PRIVATE,
ABSOLUTETIME_SCALAR_TYPE, NEEDS_SCHED_CALL_T and __PTHREAD_EXPOSE_INTERNALS__.
Its installed Kernel.framework headers nevertheless first pass native unifdef
rules that remove XNU-only implementation bodies. Later compiler definitions
cannot restore those removed bytes. This work reproduces that install context.

The historical three missing VM imports are native export aliases:
`_mach_vm_allocate` to `_mach_vm_allocate_external`, `_mach_vm_map` to
`_mach_vm_map_external`, `_vm_fault` to `_vm_fault_external`. All genuine
providers exist in SGAP-001. The external vm_fault signature has seven
arguments; the internal function has eight. No VM stub was introduced.

## Actual results

All artifact paths below are under `artifacts/xnu-kernel-pthread-profile/`.
Original failures and source/build prefixes remain untouched.

| Experiment | Actual result and artifact directory |
| --- | --- |
| PTHP-001 | Native header selection: 107 directories, 1906 entries; `inventory-session1` |
| PTHP-002/003/004 | Retained failures: syscall include namespace, literal double-slash make targets, generated prerequisite namespace; `headers-session1/2/3` |
| PTHP-005 | Native installed subset: 1794 installed entries, 36 native empty-filtered entries, 76 explicitly unavailable generated inputs; `headers-session4` |
| PTHP-006 | Retained missing public Availability.h failure; `compile-session1` |
| PTHP-007 | Three actual ARM64 translation units and real archive; all 61 external imports have current kernel/native-alias providers; `compile-session2` |
| PTHP-008 | 15 callback, metadata, wrong-header/type and alias checks; `controls-session1` |
| PTHP-009 | Actual real VM code aliases and wrong-real-provider negative; `aliases-session1` |
| PTHP-010 | Retained native MIG relative-component namespace failure; `native-mig-session1` |
| PTHP-011 | Four fresh native SDK-context MIG headers match installed bytes exactly; `native-mig-session2` |
| PTHP-012 | 21 final acceptance checks revalidate coherent capsules, actual object bytes and integrated common checks; `acceptance-session1` |

Native install recipes use real unifdef, decomment and replacecontents.
The explicit Linux adaptation omits BSD install's unsupported `-S`; file mode
remains 0444. Native literal double-slash make targets are preserved while
filesystem paths are canonical. Missing generated headers are never replaced
by empty files. The malformed native recursion token `bsd/skywalk/nexus/\`
is retained as an unresolved inventory entry. This is a source-generated
Kernel.framework subset, with 76 unavailable entries, not a complete SDK.

The three unchanged public Availability headers are independently bound to
pinned XNU Git blobs; TargetConditionals.h is the earlier pinned open-source
public contribution from OPENINPUT-004. Raw private-header fallback and fake
allocator metadata are forbidden. Actual current compiler SHA256:
`7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82`.

The real archive is `compile-session2/libpthread_kext.a`, SHA256
`d5f047488be1806e7e30af166312173b08f56bbbcff85340c1c5f3d28514b0d1`.
All three members match actual ARM64 objects byte-for-byte. There are 39
external definitions, 61 external imports, zero unresolved imports after
native aliases, and zero duplicate definitions against the current kernel.
Two witnessed namespace remaps preserve genuine bodies. BUILD_LTO=0 matches
the selected measured kernel integration; native Xcode's normal LTO=true is
recorded. This is not a stock Xcode release archive.

Full actual TUs, rather than invented stand-in tables, supply 45 function-table
fields and 95 callback-table fields. All 140 declarations and 284 size,
alignment, offset and field-size values agree between kext and kernel;
independent Clang19 agrees. Table sizes are 1016 and 1296 bytes. Allocator
layout is `[64,32,40,44]`; the two actual descriptors have sizes248/56, flags97,
summaries6/6 and distinct genuine type signatures. Executed controls detect a
changed field layout, reject a wrong function-pointer type, detect historical
fake signature `12`, and reject a compiler lacking the real metadata builtins.

The alias probe relocatably links actual vm_user.o/vm_fault.o and compares
actual symbol section/address pairs. A wrong alias still naming a real
provider is detected. This is a two-object alias check, not a full kernel link.
Four consumed Mach headers (mach_port, task, mach_vm, thread_act) were regenerated
using native SDK MIG recipes and exact component context, then unifdef-installed;
their bytes match those consumed by the qualified archive.

## Reproduction and acceptance

Use fresh run names. Actual producers register experiments before running.
The builder requires previously qualified local tool/source capsules; it does
not install or download a proprietary SDK.

```sh
python3 tools/build/xnu_kernel_pthread_profile.py --run new-inventory --mode inventory
python3 tools/build/xnu_kernel_pthread_profile.py --run new-headers --mode headers
python3 tools/build/xnu_kernel_pthread_profile.py --run new-compile --mode compile
python3 tools/build/xnu_kernel_pthread_profile.py --run new-controls --mode controls
python3 tools/build/xnu_kernel_pthread_profile.py --run new-aliases --mode aliases
python3 tools/build/xnu_kernel_pthread_profile.py --run new-native-mig --mode sdk-mig
python3 tools/build/xnu_kernel_pthread_profile.py --run new-acceptance --mode acceptance \
  --integration-evidence artifacts/team-coordination/20261105-ah/integration-002/evidence.json
```

Header/object defaults refer to recorded PTHP-005/PTHP-007; override
`--header-profile`/`--object-profile` for new registered inputs. The final
acceptance mode deliberately audits the named five original qualification
capsules and every recorded artifact hash. It re-decodes actual object layouts,
re-extracts archive members and imports, checks all source/header dependencies,
native aliases and MIG byte identities, and checks common-test artifact hashes.

All four task criteria are satisfied for this component: pinned genuine native
source/header context; three actual compiler builds; complete object/provider,
callback and metadata checks with executed negatives; coherent witnesses and
explicit system limits. Primary integrated `make check` passed146 tests at
`f18eba26816d8fa1ce93d4ebb60496a1607ee4ed`; evidence is the command argument
above. An initial coordinator check deadlocked on a nested board lock, was
terminated, and remains in `integration-001`; `integration-002` removes that
external lock and passes. Later integration must run common checks for its
new commit. The public qualified-component manifest contains metadata and
hashes only; Apple headers and binaries stay local.

## Handoff and remaining gates

Next link integration can consume this exact archive and native alias list
alongside current 982 genuine objects and matched firehose. KRN-023 separately
traces the genuine corecrypto registration/provider and missing callbacks.
KRN-025 separately qualifies the cc_kext compiler-support runtime. No empty
library or successful crypto/RPC/CPU stub may fill either gap.
Full link/layout, complete SDK, DriverKit private ABI (KRN-004), complete crypto,
runtime and native-device evidence remain absent. Preserve KRN-003, KRN-004,
KRN-008 and blocked recovery owners and their paths. Native GPU, Wi-Fi, SIM,
eSIM and return to Android require their own authorized tasks and evidence.

The KRN-024 driver audit corrects the earlier cc_kext/corecrypto inference.
In the actual selected compiler source at
`fa9443738c1a18accef4244732ec6d6ee97a8133`,
[Driver.cpp](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/Driver.cpp#L482)
rewrites `-lcc_kext` to its reserved compiler-driver option;
[Darwin.cpp](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/ToolChains/Darwin.cpp#L2839)
selects `libclang_rt.cc_kext_ios.a` and adds it only if the resource file exists.
The library spelling alone identifies neither a corecrypto implementation nor
its startup registration. KRN-023's unsupported crypto callbacks remain a
separate source-backed limitation. KRN-024 also preserves the actual driver
expansion and its omission, while KRN-026 investigates export-only symbol gaps.
These corrections do not alter any recorded pthread object or passing capsule.
