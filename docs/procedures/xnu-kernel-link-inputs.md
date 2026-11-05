# Genuine selected kernel archive and link-input qualification

KRN-020, owner `codex-kernel-link-inputs-20261105-ae`, parent `f5ad2a1`.
Host-only work. Preserve every original source/compiler/object/build/evidence
prefix and KRN-004/KRN-008 ownership. No phone,root,reboot,flash,SDK acquisition
or global installation. Experimental IIG/compiler and native/private-ABI limits
from IIGOBJ-007 remain in force.

The current982 direct objects have22 names without direct-object providers:
13 linker image/section/segment boundaries,six firehose/pthread imports,and
three selected source/configuration names. Validate each against actual source,
archive and linker behavior,not just its spelling. An archive or executable
fixture is not proof of the full kernel,Apple interoperability or hardware.

Pinned [MakeInc.kernel](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.kernel)
and [component rules](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.rule)
govern file lists,LIBOBJS,HIB processing,top-level object order and archive/link
flags. Copy actual982 outputs into isolated staging. Execute genuine component
filelist rules with independently verified objects marked old only for that
filelist-generation step; this performs no substitute compilation/cache pass.
HIB_FILES must be real copies because the native rule rewrites their section
segment names. Compare each resulting byte against the intended genuine edit.

Build the actual selected static-link archive using the genuine -ca/filelist
recipe and qualified source-built cctools libtool. Independently verify members
and their digests,including constructor/data/version tail order. Expand real
kernel flags/library/export requirements without dropping unavailable inputs.
Keep library-only filelist entries distinct from full-image direct objects.

The matched pure firehose provider is FHDR-006. The historical pthread archive
is OPENINPUT-004 and retains its earlier compiler/header/compatibility limits;
symbol presence alone cannot promote it to a current-profile ABI pass. Source
inspection already identifies an orphan clean_mmu_dcache global declaration,
SleepToken defined only under WITH_CLASSIC_S2R,and an iBoot stage2 array defined
only for arm64 macOS while another source references it under broader flags.
Measure the exact current configurations/objects and preserve these causes.
Do not insert CPU,boot,RPC,crypto or empty-library stubs to make linking succeed.

Register fresh experiments before running source/query/staging/archive/provider/
link/negative controls. Retain actual commands,exit codes,hashes,source/flag/
dependency/member witnesses and failed attempts. Final acceptance covers all
four task criteria and make check. Any missing required archive,tool,export,
source or ABI input remains explicit; full kernel/native qualification stays
false until evidence at that scope exists.


## Measured result and handoff — 2026-11-05

The host assessment succeeds; the full kernel link fails. These outcomes have
separate meanings. No ARM execution or phone operation occurred.

| Experiment | Actual result |
|---|---|
| KLINK-007, baseline-session5 | Pass: all982 staged direct objects;978 genuine component filelist entries;14 genuine HIB and1 KLD/KLDDATA edits;981 ordinal archive members match exact input bytes |
| KLINK-009, controls-session2 | Pass:13 real undefined ARM64 relocations resolved by source-built ld64;every pointer equals independently decoded Mach-O section/segment/image boundaries;ordinary missing provider rejected;four original TUs preprocessed and their actual symbols/relocations inspected |
| KLINK-003/006, pthread-session1/2 | Fail: all3 genuine typed pthread TUs fail under attempted BSD-consumer/kext-definition contexts;full diagnostics retained;historical archive not promoted |
| KLINK-011, link-session2 | Host assessment pass:15 selected export files plus real disabled Kasan/Kcov exports;genuine aliases and nine symbolsets;two actual full-link attempts fail without emitting an image |
| KLINK-012 | Final acceptance: reverify archive members/all982 staged objects,provider closure,real damaged-archive rejection,retained failures,all4 acceptance criteria and make check |

The genuine archive is
`artifacts/xnu-kernel-link-inputs/baseline-session5/stage/kernel.link/kernel.a`,
SHA256 `e1f4a81bffd2e0fa7d945b7a99a1b8cd836375e23f043c108f248427cb1b3be6`.
Its978 component objects follow genuine COMPONENT_LIST order:
osfmk,bsd,libkern,iokit,pexpert,libsa,security,san. The archive then appends
version.o,lastkerneldataconst.o,lastkernelconstructor.o. Genuine full-image
linking additionally needs nonlto.o,for982 direct objects. This archive was
created directly from the real native -ca recipe;the native packaging target
normally follows a successful full image. It is an input archive,not evidence
that that packaging prerequisite succeeded. BSD's distinct library-only
qsort.o was not substituted into the978 full-image selection.

The standalone query originally lacked cosmetic logging,REPLACECONTENTS and
supported-platform definitions. Copying the genuine logging/platform lines
and compiling unchanged SETUP/replacecontents/replacecontents.c with an owned
Linux getprogname diagnostic-name adapter restores those host inputs. It does
not alter target algorithms. The native sanitizer filelist now executes its
real .KASANFLAGS prerequisite. Genuine setsegname rewrites only owned copies;
independent Mach-O edits agree byte for byte. All original982 object/source
and3152 dependency witnesses remain intact. Archive members are checked by
ordinal,so legitimate repeated basenames do not collapse into one dictionary.

### The actual unresolved names

- Thirteen linker-generated names are verified by actual static ARM64 linking:
  ___dso_handle,__mh_execute_header,segment$start$__DATA,and start/end pairs
  for __DATA/__percpu,__DATA_CONST/__kalloc_type,__DATA_CONST/__kalloc_var,
  __BOOTDATA/__init_entry_set and __TEXT/__thread_starts. Synthetic names can
  disappear from the output symbol table;their13 relocated pointer values,
  rather than symbol-table presence alone,establish the result. The fixture's
  genuine-format section anchors exercise ld64;they do not supply kernel or
  boot functionality. A separate ordinary missing provider fails real linking.
- Five firehose names are exported by the actual matched FHDR-006 pure
  component. All11 of its external imports have providers among the982 direct
  objects. This is the previously qualified source/header profile,not Apple's
  private implementation or a hardware logging test.
- _pthread_start exists in the historical OPENINPUT-004 archive. Its undefined
  names must first subtract definitions from its own members:59 external
  imports remain,of which _mach_vm_allocate,_mach_vm_map and _vm_fault are
  absent from the982 graph. The raw baseline's required_not_in_direct_objects
  field deliberately includes archive-internal references;use acceptance's
  provider_import_closure for external closure. Historical compilation used
  fake allocator type metadata. Current compiler attempts use real metadata
  checks and retain header/type conflicts. They establish failure under those
  attempted contexts,not impossibility of a genuine pthread port. A coherent
  selected kext header/configuration profile and those three real providers
  remain necessary.
- _clean_mmu_dcache is an orphan global in caches_asm.s:the selected assembly
  defines actual _CleanPoC_Dcache code,but never the former label. Its object
  retains the undefined global. Qualify an intended real alias against callers
  and ARM cache semantics before changing the source.
- _SleepToken is declared global in start.s,while its label/storage is guarded
  by WITH_CLASSIC_S2R. The actual selected macro is undefined,so #if evaluates
  to zero. No label/storage remains in preprocessing;the object still carries
  the undefined global. Qualify configuration-consistent declaration scoping,
  including the enabled path;do not invent an unused boot-storage stub.
- _iBoot_Stage_2_version is referenced by real model_dep.c panic reporting,
  while pe_init.c defines the128-byte array only for TARGET_OS_OSX plus arm64.
  The measured iOS provider preprocessing excludes it. Determine intended
  firmware provenance and consistent producer/consumer guards;do not insert
  a fabricated firmware-version provider.

### Genuine metadata and full-link limits

KLINK-011 expands config/Makefile's exact selected EXPORTS_FILES and invokes
its genuine export,alias,newvers,symbolset and combined-symbolset scripts on
owned copies. Source hashes and all actual commands are in report.json. The
combined SymbolsSets array has nine entries and the real
WeakRefFallbackSymbol=_gOSKextUnresolved. Python stdlib plistlib serializes the
genuine XML to binary1 and verifies a semantic roundtrip. This host converter
has no native Apple plutil oracle;that limit remains explicit.

Both full-link attempts use current source-built Clang and an explicit path
to qualified source-built ld64. The -### output proves actual linker selection.
They retain every selected target,segment/section rename/order/protection,
export/alias/symbolset flag,all982 direct objects and -lcc_kext,
-lfirehose_kernel,-lpthread_kext. The first fails at -lfirehose_kernel in the
unavailable SDK search paths. The second adds an isolated directory containing
only the actual FHDR-006 archive and reaches the missing -lpthread_kext input.
No historical pthread archive,empty library,SDK placeholder content or feature
removal is supplied. No image is emitted. The required cc_kext archive is also
unsupplied;the first diagnostic does not prove it is the sole missing input.

No claim follows for full export/alias closure,segment capacity/relocations,
constructor ordering in a completed image,all-source runtime behavior,Apple
private IIG/type metadata ABI,full crypto/KEC FIPS or iOS interoperability.
The existing crypto shim still has missing callbacks;it is not a qualified
corecrypto replacement. SDK/profile provenance,private headers/library ABI,
full link,exports,crypto and runtime checks precede native work. Recovery,
real unlock/root state and separate native authorization remain unverified.
GPU/Wi-Fi/SIM/eSIM and a complete iOS userspace are not established by any
of these host artifacts.

KRN-008 retains full integration ownership;KRN-004 retains private ABI/oracle
ownership;KRN-003 retains SDK/library dependency work. This procedure and the
qualified-component manifest are their handoff;no frozen paths were changed.
KRN-021 is a narrow proposed follow-up for the three measured selected source
symbol gaps,with real caller/configuration controls in fresh source copies.
Pthread requires an independent coherent kext profile/header/provider task,
not reuse of the old archive as a current-profile pass.

### Preserved failures and replay

KLINK-001 retains missing logging expansion;002 retains the too-narrow HIB-only
verifier;004 retains the missing real sanitizer REPLACECONTENTS input;005
retains the missing standalone supported-platform query input.003/006 retain
pthread compile failures.008 retains a harness expectation that incorrectly
required an explicit WITH_CLASSIC_S2R=0 rather than its actual undefined state.
010 retains the initial full link without the qualified external archive path.
Original failures are immutable and recorded before corrected fresh attempts.

Register fresh experiment IDs before these examples;run names must be unused:

```sh
python3 tools/build/xnu_kernel_link_inputs.py --run fresh-inputs --mode baseline
python3 tools/build/xnu_kernel_link_inputs.py --run fresh-pthread --mode pthread-kext
python3 tools/build/xnu_kernel_link_inputs.py --run fresh-controls --mode controls
python3 tools/build/xnu_kernel_link_inputs.py --run fresh-link --mode link
python3 tools/build/xnu_kernel_link_inputs.py --run fresh-acceptance --mode acceptance
```

The builder intentionally consumes pinned local qualified parent prefixes and
registered evidence;it does not fetch proprietary inputs,rebuild every parent
or install anything globally. Commands,exit codes,source/tool/header/object/
member hashes,commit and existing artifact paths are captured in each fresh
report.json/evidence.json. Maintained files and public manifests are English.
