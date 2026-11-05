# Selected XNU allocator compiler metadata

KRN-005; owner codex-compiler-types-20261105-p; main checkout; baseline fc4eef9.
This is a bounded experimental source compiler component, with no full kernel,
Apple compiler/SDK/private ABI equivalence or native-device qualification.

## Result

The actual public-source Clang17 extension compiles all 17 selected generated
DriverKit implementations as arm64 Mach-O with traced E1S/private defines.
Seven concrete compile cases, six exact misuse/unsupported rejections and three
real object mutations pass. The actual allocation metadata resolves through
object relocations to these records:

| Shape, each 16 bytes | Signature | Flags |
|---|---|---|
| Pointer then data | 12 | 0x61 |
| Two data words | empty | 0x69 |
| Two pointers | 11 | 0xe1 |

The real selected header gives a 64-byte allocation view, signature offset32,
flags40 and allocation-size44. The reader checks actual sections, symbols,
relocations and bytes. A genuine object compiled with the donor's constant
fallback is rejected. No constant type signature/summary replaces the compiler
analysis in the qualified profile.

The precise reusable compiler, input/output hashes and qualification limits are
in fixtures/public/xnu-compiler-types/qualified-component.json.
The compiler remains local at artifacts/xnu-compiler-types/gnu-void-session1/clang,
SHA256 4c1e57401ad82aaa87d84e84cb7f1aa97d2613ed22c436d344840b32b0c94d9f.

## Sources and actual mechanism

Public tpoechtrager/apple-libtapi fa9443738c1a18accef4244732ec6d6ee97a8133
contains LLVM/Clang17.0.6. Original checkouts remain clean. Each component's
license is retained; actual src/clang/LICENSE.TXT and src/llvm/LICENSE.TXT use
Apache2 with LLVM exceptions, separately from older top-level notices.

The full private source inventory and 198 archive/generated-header/build-recipe
hashes bind the real build. CMake's version banner inherited the parent project
commit fc4eef9; it is not the upstream source identity. The full pinned source
witness, per-file hashes and patch hashes establish that identity.

Owned patches and XnuTypeMetadata.h in patches/compiler-types implement:
target ASTContext/ASTRecordLayout-based eight-byte granules; scalar typedef and
field semantics; summary bits; layout compatibility; dependent type lowering;
type-only parser entry points; GNU unevaluated void typeof support. Runtime
void dereference remains rejected. No selected XNU IOLib/kalloc declaration or
original KRN-001/KRN-003 implementation was altered to disable checks.

Selected public kern/kalloc.h supplies the encoding/flag rules. Apple's
[allocator explanation](https://security.apple.com/blog/towards-the-next-generation-of-xnu-memory-safety/)
is supporting primary context. No exact private compiler oracle is supplied.
PureDarwin's pinned cross-compiler recipes were inspected as source data; no
Nix activation/install, archive test or SDK build was executed.

## Preserved experiments

All TYPECOMP-001 through008 records are in state/evidence, with full local
commands/exits/diagnostics and sanitized report copies under fixtures/public.

| Experiment | Actual result |
|---|---|
| 001 | All four installed Clang profiles report four missing APIs and fail public/annotation/real allocator/metaclass uses |
| 002 | Real private build finishes all2662 Ninja targets; API queries return1, but actual uses fail at missing unary parser dispatch |
| 003 | New implementation header passes an actual host syntax check against generated Clang17 AST/attribute headers; this alone is not metadata qualification |
| 004 | Actual arm64 object using the known donor constant fallback compiles, but relocation-bound metadata inspection rejects it |
| 005 | Correct parser object/member/relink succeeds; six arm64 cases, five negative controls, three real metadata records and three mutations pass; broader scope remains inconclusive |
| 006 | E1S/private audit compiles4/17 interfaces; remaining13 expose forbidden void indirection in genuine IOLib unevaluated type checks |
| 007 | Restricted GNU unevaluated fix passes seven cases, six negatives, three metadata records/mutations and17 interfaces; harness wrongly exits1 despite component pass, so enclosing evidence stays inconclusive |
| 008 | Direct audit of unchanged recorded compiler bytes repeats the complete concrete profile and returns real exit0; bounded component pass |

The corrected parser and semantic objects are compiled in new output directories,
inserted into copied archives, independently extracted/hashed, then relinked with
the unchanged source-built libraries. Original source, generated headers,
archives, binaries, reports and failed runs remain intact. A complete compiler
rebuild is not used as a substitute for this verified incremental path.

The profile enables real allocator checks with XNU_NO_TYPE_BUILTINS=0 only after
the compiler declares all four APIs; positive behavior and negative misuse tests
must still pass. It never enables the donor's disabling/constant fallback.

## Reproduction

Use a new owned host task and register an experiment before execution. Source
checkouts must be pinned, clean and source-only expanded as in KRN-002; a fresh
sparse source-catalog fetch alone is not a complete LLVM checkout. The existing
prepared XNU/IIG/source-header witnesses are verified before reuse.

Fresh base build (expected exit1 for its retained parser gap):

    python3 tools/build/xnu_compiler_types.py --run fresh-compiler-base \
      --build-frontend --jobs 3 \
      --host-cxx /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++ \
      --clang /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang

The maintained runner writes source/build witnesses and evidence.json itself.
Record that capsule through tools/lab.py experiment record. Then use a fresh
experiment/run and its recorded --frontend-evidence:

    python3 tools/build/xnu_compiler_types.py --run fresh-compiler-profile \
      --reuse-frontend-run artifacts/xnu-compiler-types/fresh-compiler-base \
      --frontend-evidence artifacts/xnu-compiler-types/fresh-compiler-base/evidence.json \
      --expanded-controls --e1s-profile --compile-interfaces \
      --qualify-supported-profile --unevaluated-void-port \
      --clang /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang

The current existing compiler can be directly audited without rebuilding it,
using recorded state/evidence/TYPECOMP-007.json and the gnu-void-session1/clang
path with the profile/control flags. Do not omit the parent evidence check.

Full builds have a1500-second command limit; configuration has180 seconds;
normal commands have90 seconds. The optional terminal-build continuation path
is unexercised; it requires an actual failed report, unchanged source and no
live prior build/compiler process. Registry timeouts are bookkeeping, not
phone recovery/watchdogs. Never restart merely on an observation timeout.

## Handoff, acceptance and next work

The preceding IIG goal turn and this turn both made concrete progress. All build
sessions are terminal. KRN-005 acceptance is assessed in acceptance.json against
actual artifacts; component completion does not complete the full goal.

KRN-006 is the next independent hardening task. New unary AST enum fallback
paths in ExprConstant/ItaniumMangle still need explicit handling or deterministic
unsupported diagnostics, especially dependent builtin/SFINAE mangling, AST/PCH
round trips and representative whole-kernel units. Current explicit template
controls pass; unexercised language paths are not thereby qualified.

PAC/arm64e, references/member pointers, virtual bases, scalable/VLA, excessive
depth and very large layouts are unsupported. Full compiler/Apple binary ABI
equivalence, complete header/export/SDK/configuration closure, private DriverKit
interoperability and a full E1S kernel link remain separate requirements.
No previous KRN-004 ABI claim is upgraded by these compile results.

No phone command, APK install, root request, reboot, flash, Apple binary/SDK/
firmware/archive acquisition or global package/header/compiler modification
occurred. Android/native authorization stays false. Radio/userland/recovery
input gates and all prior owners remain unchanged. No optional local SDK/iOS/
RIL path has been supplied; elapsed time is not input availability.
