# Experimental fixed arithmetic-vector metadata

KRN-011, owner `codex-compiler-vectors-20261105-x`, main at parent `00f106c`.
The bounded compiler component passes; full kernel/native iOS support remains
incomplete. No phone command, SDK acquisition, global installation or old
compiler/source/build/header-prefix mutation was performed.

The new compiler emits **953 component objects plus version.o: 954 known direct
ARM64 objects**. Every current 962 source recipe was retried; all 953 prior
successful direct objects still compile. The formerly failing status.c now
compiles with actual allocator/type checks enabled. Of 978 component entries,
25 remain unresolved: 8 failures and 17 missing IIG sources. Three other top-level
objects are unattempted, so 28 of 982 known direct objects remain unresolved.
Archive members, link metadata and final/native qualification remain separate.

## Source and chosen rule

The actual selected arm_act_context contains arm_neon_saved_state64 union fields
with arrays of `uint64x2_t` and `uint32x4_t`, declared with ext_vector_type in
`osfmk/mach/arm/thread_status.h`. ATCOMP-008 traced this real metadata failure.
The selected XNU source is
[`c54f35ca767986246321eb901baf8f5ff7923f6a`](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a)
with recorded E1S patches/fixes.

Pinned [LLVM/Clang 17.0.6](https://github.com/tpoechtrager/apple-libtapi/tree/fa9443738c1a18accef4244732ec6d6ee97a8133)
ASTContext computes vector width from element width/count, then rounds storage
and alignment with target alignment limits. CodeGenTypes creates the actual
fixed vector with the original lane count. A three 64-bit-lane value has 24 bytes
of lane payload in 32 bytes of target storage; alignment is 16 on this target.
Independent Clang 19 and source Clang 17 agree on these sizes/offsets, including
packed records and alignment gaps.

[Apple's allocator overview](https://security.apple.com/blog/towards-the-next-generation-of-xnu-memory-safety/)
describes layout granules and explicit usage annotations. The selected public
`kern/kalloc.h` provides the exact current granule encodings/masks used here.
The vector-specific rule below is our bounded source-backed implementation,
not a matching private Apple compiler measurement.

The helper supports GenericVector/NeonVector with real builtin arithmetic
integer/floating lane types. It checks actual target storage/payload extents,
classifies only lane value bits as data, and leaves additional storage as padding.
For three 64-bit lanes the signature is `2220` and summary 5, while sizeof is 32.
A vector plus a pointer preserves alignment gaps, trailing padding and the
pointer's actual offset. Packed overlap and unions retain the existing OR rules.
No numeric vector data is inferred to be a pointer.

Explicit vector-level semantics and annotated lane typedefs remain unsupported.
Boolean/predicate, polynomial, fixed SVE/RVV and sizeless forms are rejected.
Sizeless checks occur before querying a target size. Reference/member-pointer,
virtual-base, PAC/arm64e, VLA, aggregate annotation and existing bounds remain.
The 1 MiB storage, 131072 element and 128 depth limits are retained. These scope
limits avoid asserting semantics that were not established by source/controls.
See [patch attribution](../../patches/compiler-vectors/README.md).

## Actual source rebuild

The new source compiler is
`artifacts/xnu-compiler-vectors/source-build-session1/clang`, SHA256
`3b11f867131e9a22a3671101ffb09dcecaf2b6831e5fd2c384b95075f29008a3`.
Its parent is the immutable ATCOMP-004 compiler/helper/archives.
Every actual helper consumer is rebuilt with original CMake argv:
SemaExpr.cpp, SemaExprCXX.cpp, ExprConstant.cpp. Source GNU void, AST constant
handling and all atomic/array fixes remain. Extracted Sema/AST archive members
match real rebuilt objects; copied Parser and AST mangler members match their
qualified original objects. The full recorded relink retains all other inputs.
No mutating Ninja runs in an original build prefix.

Input checks verify the 10889-file compiler source, 198 original build inputs,
5111-file prepared kernel tree and registered HARDEN/KCONFIG/KOBJECT/ATCOMP/
KSETUP inputs. New fixtures are copied before execution. Failed baselines and
all original report/source/fixture bytes remain unchanged.

Register fresh VCOMP experiments before execution:

```sh
python3 tools/build/xnu_compiler_vectors.py --run NEW_SOURCE_BUILD --mode build
python3 tools/build/xnu_compiler_vectors.py --run NEW_QUALIFICATION \
  --mode qualify --compiler "$PWD/artifacts/xnu-compiler-vectors/source-build-session1/clang" \
  --compiler-evidence VCOMP-002
python3 tools/build/xnu_compiler_vectors.py --run NEW_FULL_PROFILE \
  --mode kernel --compiler "$PWD/artifacts/xnu-compiler-vectors/source-build-session1/clang" \
  --compiler-evidence VCOMP-002 --jobs 2
python3 tools/build/xnu_compiler_vectors.py --run NEW_OBJECT_AUDIT \
  --mode audit --compiler "$PWD/artifacts/xnu-compiler-vectors/source-build-session1/clang" \
  --compiler-evidence VCOMP-002 --profile-evidence VCOMP-004
```

A fresh source-build experiment must be recorded before its own evidence ID can
replace VCOMP-002. Reuse verifies exact binary/archive/helper/source provenance;
a version banner alone is insufficient. Full argv/cwd/exits/diagnostics remain
in hashed reports; capsules label any representative command sample.

## Measured controls and regressions

| Experiment | Actual result |
|---|---|
| VCOMP-001 | Fail: both independent target-layout compilers agree; old actual metadata rejects fixed vectors |
| VCOMP-002 | Pass: all 3 consumers rebuilt, copied members/relink bound, atomic/vector/negative/raw/PCH and genuine status.c pass |
| VCOMP-003 | Pass: new vector PCH, code/relocation mutations, dependent mangling and direct raw AST evaluation pass |
| VCOMP-004 | Pass for partial closure: 954 real ARM64 objects from 962 actual recipes, zero prior 953 regressions |
| VCOMP-005 | Pass: retained 7 profile cases/6 negatives, actual 3 allocator records with mutations and 17 selected IIG source compiles |
| VCOMP-006 | Pass: retained ordinary C/C++ PCH, SFINAE/separate-TU symbol agreement and foreign/truncated/wrong-target/layout negatives |
| VCOMP-007 | Pass: extended actual NeonVector, annotated-lane rejection and updated independent layout/raw/PCH fixtures |
| VCOMP-008 | Pass: independent 954 headers, 962 exact recipe/source associations and 3086 actual dependency files |

Scalar/array/atomic/annotation controls remain intact. Vector controls distinguish
value lanes from tail padding, alignment gaps, packed data/pointer overlap,
unions and arrays. Genuine selected kern/kalloc.h allocation records retain
strict symbol/layout/relocation validation. The separate retained suite's 17 IIG
compiles do not substitute for missing full-recipe/private-ABI integration.

The raw host AST harness creates real target VectorType/ExtVectorType nodes and
actual custom trait expressions. It gets summary 4/signature 22 for two lanes and
summary 5/signature 2220 for three, with sizeof 16/32 respectively. It also exercises
Native NeonVector and rejects boolean, polynomial, fixed SVE, sizeless,
excess-element and reference types gracefully. This executes the actual linked
AST evaluator rather than relying solely on Sema's source lowering.

Vector PCH serialization loads annotated/dependent metadata types and instantiates
new types. Actual named-function bytes and normalized call relocations agree
with textual inclusion; legal function reordering is observed separately.
Real code-byte and relocation-target mutations are rejected. The fixture-specific
reader requires exactly one nonempty text section and three actual code symbols.
The dependent vector expression demangles. Retained ordinary PCH checks remain
byte-identical, and separate-TU template symbols agree. No foreign/private Apple
AST schema or mangling equivalence is inferred.

The whole profile reuses unchanged KSETUP-004 source/header/cwd/per-file flags,
including its hash-bound startup source port. Only compiler/object/dependency
outputs change. All 961 component attempts plus direct version.o are repeated;
there is no source-only cache reuse after changing the compiler. Actual checks
remain `-DXNU_NO_TYPE_BUILTINS=0`, with no constant fallback or blanket `-w`.

## Component handoff and remaining work

The [compiler/object component](../../fixtures/public/xnu-compiler-vectors/qualified-component.json)
binds patches, source consumers, archives, compiler, exact parents and full
regression/audit results. Local prefixes:

- `artifacts/xnu-compiler-vectors/source-build-session1`: real rebuilt compiler and archives.
- `artifacts/xnu-compiler-vectors/qualification-session2`: latest immutable extended fixtures/raw/PCH controls.
- `artifacts/xnu-compiler-vectors/full-profile-session1`: all 962 actual current compile recipes.
- `artifacts/xnu-compiler-vectors/object-audit-session1`: independent full object/source/dependency audit.

[Compiled objects](../../fixtures/public/xnu-compiler-vectors/compiled-objects.json)
include version.o; [unresolved objects](../../fixtures/public/xnu-compiler-vectors/unresolved-objects.json)
include all 25 remaining component entries and three additional top-level objects.
These are new manifests, not rewrites of earlier partial profiles.
LLVM verifies all 954 arm64 headers and 29002 defined code symbols. Actual input
witnesses bind 3086 files plus each object's dependency graph. Exact compiler,
command, header, source-port and dependency bytes are required for reuse.

Remaining failures are 4 missing-header cases, 2 unsupported metadata layouts
and 2 other source/profile issues. KRN-014 owns genuine firehose headers (3
consumers); KRN-015 owns matched ARM NEON compiler resource headers (1 APFS
consumer). C++ member pointers in MiniIOSurface and reference fields in IONVRAM
remain unsupported. The mc_provider printf macro conflict and undeclared
proc_pid remain. Seventeen selected IIG sources, other direct objects and
archive/link closure are additional prerequisites under their existing owners.
Native boot/recovery, Apple userland, GPU, Wi-Fi and SIM/eSIM operation remain
unqualified and device scopes are unchanged. Final repository and bounded task
acceptance are recorded as VCOMP-009.
