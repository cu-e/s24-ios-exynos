# Selected Apple ARM64 C++ storage

KRN-017, owner `codex-cxx-storage-20261105-ab`, parent `4cdb083`.
Host-only work; every original compiler, source, fixture and evidence prefix
is retained. No SDK, phone, root, installation or native boot is involved.

The selected MiniIOSurface class contains IOExternalTrap entries with an
ordinary object pointer and IOService member-function pointer. Both selected
IONVRAM format handler classes store an OSSharedPtr<OSDictionary> reference.
KDECL-008 records these as the only two available-source compile failures.

The public compiler source is apple-libtapi revision
`fa9443738c1a18accef4244732ec6d6ee97a8133` (Clang17). ASTContext.cpp reference
storage, CodeGenTypes.cpp and CGRecordLayoutBuilder.cpp lower reference fields
to pointers independently of language sizeof(reference), which observes the
referent. ItaniumCXXABI.cpp in AST assigns two ptrdiff_t words to method
pointers; the AppleARM64 CodeGen ABI inherits ARM method-pointer encoding.
The two integer words carry code address/vtable offset and this-adjustment
with a virtual flag. Selected kern/kalloc.h defines pointer granules as 1 and
non-pointer scalar granules as 2. These justify stored reference granules 1
and method-pointer granules 22 in this experimental public-source model.
No private Apple compiler comparison or runtime ABI compatibility is claimed.

New handling requires C++, AppleARM64 C++ ABI and 64-bit default pointer and
ptrdiff_t width/alignment. References are supported only as actual C++ record
fields with default-address-space object referents, not root reference types.
Reference/member-pointer annotations, data-member pointers, nondefault address
spaces, function/scalable referents, virtual bases and PAC/arm64e remain outside
the qualified extension. Ordinary function-pointer handling is unchanged.

Pinned primary source locations:

- [Reference storage and effective ABI](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/AST/ASTContext.cpp).
- [Member-pointer AST representation](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/AST/ItaniumCXXABI.cpp).
- [Reference LLVM type](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/CodeGen/CodeGenTypes.cpp)
  and [record field storage](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/CodeGen/CGRecordLayoutBuilder.cpp).
- [Apple ARM64 method-pointer CodeGen](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/CodeGen/ItaniumCXXABI.cpp).
- [Public allocator granules](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/kern/kalloc.h)
  and [genuine IOExternalTrap](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/iokit/IOKit/IOUserClient.h).

The runner uses a fresh artifacts/xnu-compiler-cxx-storage prefix per run.
Modes: baseline, build, controls, consumers, kernel and audit. Baseline measures
stock Clang19 layout and the retained compiler rejection. Build patches only
the copied helper, recompiles all three real helper consumers, verifies archive
members and retained Parser/mangler objects, then relinks the actual compiler.
Controls exercise independent representations, real allocator records, direct
AST evaluation, templates/PCH and code/relocation mutations. Kernel retries all
962 current recipes with checks enabled; audit independently binds commands,
source/output/dependency bytes and the entire 982-known-direct-object inventory.
Full archive/link, missing IIG/private ABI, crypto and native-device support
remain separate requirements even if every available recipe compiles.

The final compiler is source-build-session2/clang, SHA256
`7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82`.
Its selected parent is VCOMP-002's vector/atomic compiler, SHA256
`3b11f867131e9a22a3671101ffb09dcecaf2b6831e5fd2c384b95075f29008a3`.
All three real helper consumers are rebuilt: SemaExpr.cpp, SemaExprCXX.cpp and
ExprConstant.cpp. The Parser and Itanium mangler members are retained exactly.

Baseline CXXST-001 independently measures: char& language size1, int& language
size4, two-reference record size16/alignment8, method-pointer size16/alignment8,
trap size24 and method field offset8. The method-pointer data words and actual
code relocations agree between Clang17 and independent Clang19: null(0,0),
direct(code relocation,0), first virtual slot(0,1), and multiple-inheritance
adjustment(code relocation,8), corresponding to a four-byte this adjustment.
The metadata extension expects stored reference1, method22 and trap122/summary6.
Packed reference overlap and incomplete/rvalue/vector object referents are
checked separately; referent bytes are never traversed as stored reference data.

CXXST-003 retains two failed test assumptions and an implementation gap.
arm64 watchOS uses AppleARM64, so that triple cannot stand in for a foreign ABI.
An explicit -fc++-abi=itanium probe showed that the guard must use
ASTContext::getCXXABIKind, which includes the language override. CXXST-007
rebuilds all three consumers with that corrected guard; both ordinary Sema
and raw AST paths test the explicit override. The new PCH fixture initially
emitted __compact_unwind, outside the retained canonical comparator's schema.
Only that fixture now consistently uses no-exception/no-unwind flags to compare
its three actual function bodies and external call relocations. Original
atomic/vector PCH fixtures retain their flags and tests.

Fresh run examples (register a new experiment ID before execution):

```sh
python3 tools/build/xnu_compiler_cxx_storage.py --run fresh-build --mode build
python3 tools/build/xnu_compiler_cxx_storage.py --run fresh-controls --mode controls --storage-evidence CXXST-007
python3 tools/build/xnu_compiler_cxx_storage.py --run fresh-retained --mode profile --storage-evidence CXXST-007
python3 tools/build/xnu_compiler_cxx_storage.py --run fresh-full --mode kernel --storage-evidence CXXST-007 --jobs 2
```

The retained historical profile runner still describes all reference/member
pointers as unsupported in generic prose. Its unchanged concrete negatives
are root references and data-member pointers, which remain rejected. The only
old concrete negative intentionally changed here is vector-reference, now a
positive actual field-storage test. Component qualification always includes
the new precise scope controls in addition to the retained profile.

## Result and integration handoff

CXXST-008 passes **117 actual checks**. These include independent storage/IR/
relocation agreement, supported metadata, precise unsupported controls, retained
atomic/vector/allocator/raw-AST/template/PCH controls, genuine IOExternalTrap,
three new genuine allocator records and actual allocator/code/call mutation
rejection. CXXST-009 separately preserves all seven original profile controls,
six negatives, three allocator mutations and 17 standalone IIG compiles.
The standalone interface tests do not supply the 17 missing component sources
or establish a private DriverKit ABI.

CXXST-010 retries **all 962 current recipes**, producing 961 component objects
plus version.o, with every prior 960 direct success retained and both genuine
MiniIOSurface/IONVRAM failures resolved. No source/header/per-file configuration
or type-check suppression was added to these recipes. Only the compiler and
fresh output/dependency paths change from KDECL-008. First-candidate CXXST-005
also emitted 962 objects but is retained as history, not the final component.

CXXST-006 independently verifies every current command/source/output/depfile,
**3131 unique dependency files**, and **29740 defined code symbols** (17655 T,
12085 t). The complete known direct inventory remains 982: 962 emitted, 17
missing IIG component sources and three unattempted top-level direct objects.
No available-source compile failures remain in this bounded profile.
KRN-018 is queued for nonlto.o, lastkerneldataconst.o and
lastkernelconstructor.o, including the genuine no-LTO/profiling exclusions
and setsegname/LAST processing rather than a bare compile-only substitute.

Reuse qualified-component.json, compiled-objects.json, unresolved-objects.json
and the recorded object/dependency manifests. Existing KRN-008 retains object/
archive/link integration ownership; KRN-004 retains private IIG ABI ownership.
The current source ports (KDECL-004), generated resources (RHDR-002), firehose
header/provider (FHDR-003/006), MIG/syscalls/setup inputs and every original
5111-file kernel/10889-file compiler/198-input build witness remain unchanged.
The patch's blank context line is normalized in the maintained patch; final
replay must reproduce the exact compiled helper bytes.

This completes a compiler/object-building step. It supplies no full kernel
archive/link proof, complete private SDK, full crypto/runtime behavior, recovery,
boot, rendering/GPU, Wi-Fi or SIM/eSIM hardware qualification. Android and native
scopes remain false; no phone command was issued.
