# Experimental compiler AST hardening

KRN-006; owner codex-compiler-hardening-20261105-q; main checkout at cc02b10.
This procedure qualifies bounded host compiler behavior. Full Apple ABI, kernel
link, ARM execution and native iOS support remain unqualified.

## Measured result

The original TYPECOMP-008 compiler traps (SIGTRAP, actual exit -5) on direct
summary AST evaluation. Two dependent template uses compile with missing
operator bytes in their symbols, which LLVM's demangler cannot parse. The
compatible-type trait instead emits an explicit unsupported-mangling error.
These real failures are preserved in HARDEN-001.

The new source-built AST archive fixes summary/signature evaluation and emits
public vendor expressions for all three builtin spellings. Actual object
symbols demangle to the correct builtin and Word type. Independent pointer/data
cases give summary2/4 rather than sizeof8, and signature1/2. Unsupported raw
reference cases return evaluation failure without trapping. Source-level
reference, virtual-base, member-pointer, VLA and arm64e cases retain the exact
experimental unsupported-layout error.

C11/C++17 header creation and consumption pass with real PCH files. Textual and
PCH inclusion produce identical arm64 object bytes. Target layout/type and
signature assertions, scalar pointer annotations and true/false SFINAE overload
selection survive serialization. Separate caller/definition translation units
agree on all three template symbols. Truncated PCH and arm64e target mismatch
are rejected; a real installed LLVM19-generated PCH receives an explicit format
error. This qualifies the same experimental schema, with no foreign/compiler
serialization or Apple private ABI claim.

The hardened compiler also retains the original seven concrete metadata cases,
six misuse/unsupported rejections, three actual object mutations and all17
selected E1S/private generated interface compiles (HARDEN-005). Its real allocator
records remain mixed12/0x61, data-empty/0x69, pointers11/0xe1, all16 bytes.

The reusable compiler is local at
artifacts/xnu-compiler-hardening/ast-patch-session1/clang,
SHA256 3e00352f47a31504c731e70e592a3d407ac3a6176c59b1638cbb7b8f98a3bd27.
See fixtures/public/xnu-compiler-hardening/qualified-component.json for exact
parents, patches, qualification evidence and limits. The previous component's
manifest and all consumed bytes stay unchanged.

## Actual kernel units and remaining configuration

With the partial E1S/private include/define profile, genuine
libkern/c++/OSData.cpp compiles to arm64 Mach-O (17 warnings, no errors).
This is a whole source translation unit, with XNU_NO_TYPE_BUILTINS=0 and no
rewritten kernel declarations. Its warnings and every command are retained.

The other real attempts fail before object creation: kalloc.c reports missing
vm_map_entry_t declarations, and pe_identify_machine.c reports undeclared
ml_io_map. These are not evidence of a missing external SDK: the corresponding
declarations are in the actual prepared source, behind component private defines.
The exact required recipes at line19 of each component conf/Makefile.template are:

| Component | Additional actual recipe |
|---|---|
| osfmk | -include meta_features.h -DMACH_KERNEL_PRIVATE -DMACH_KERNEL |
| pexpert | -include meta_features.h -DPEXPERT_KERNEL_PRIVATE |
| libkern | -include meta_features.h -DLIBKERN_KERNEL_PRIVATE -DOSALLOCDEBUG=1 |

SETUP/config/mkheaders.c generates meta_features.h from real selected component
configuration. No fake feature header or arbitrary feature values were supplied.
Complete RELEASE/ARM64/E1S configuration/export inputs, CURRENT_MACHINE_CONFIG_LC,
CONFIG_DEFINES and SEED_DEFINES must be traced and generated before a full profile
claim. HARDEN-006 binds these source bytes and retains all actual diagnostics.
KRN-007 owns this next work in fresh output paths; KRN-001/003/004 owners and
reserved implementations remain unchanged.

## Provenance and preserved experiments

Preserve TYPECOMP-008 and its compiler bytes. Verify its registered evidence,
the complete source inventory and all original archive/generated-header/recipe
witnesses before reuse. Register each HARDEN experiment before executing it.
Use new run names; never run a mutating Ninja build in a recorded prefix.
The public source pin is tpoechtrager/apple-libtapi
fa9443738c1a18accef4244732ec6d6ee97a8133 (LLVM/Clang17.0.6). Each source
component retains its own license, including Apache2 with LLVM exceptions.
The inherited fc4eef9 version banner is not the upstream source identity.

| Experiment | Recorded outcome and meaning |
|---|---|
| HARDEN-001 | Fail: actual SIGTRAP, invalid unary symbols and compatible-trait diagnostic |
| HARDEN-002 | Pass: actual incremental AST object/archive/member/relink, three mangles and six raw evaluator controls |
| HARDEN-003 | Fail: C/C++ PCH controls pass; runner misinterprets MIG manifest keys as filenames before kernel attempts |
| HARDEN-004 | Pass: corrected manifest resolution, PCH/negative controls, actual OSData object and precise two unit failures |
| HARDEN-005 | Pass: complete prior allocator/interface profile on unchanged new compiler bytes |
| HARDEN-006 | Fail: new SFINAE assertions and all preceding controls pass; foreign PCH correctly rejected but diagnostic predicate expects different wording |
| HARDEN-007 | Pass: foreign-only rerun checks the exact actual format rejection; no compiler change |

An enclosing failed experiment is never rewritten as pass. The later targeted
run establishes the corrected diagnostic gate; HARDEN-006's measured SFINAE and
unit commands remain actual zero/nonzero results in their original capsule.
The unchanged historical regression runner still lists dependent fallback work
as a limitation; the newer HARDEN evidence resolves only the bounded paths here.

The runner first reproduces dependent unary mangling and raw constant evaluator
paths. Its host AST harness uses the actual Clang17 AST and source-built
libraries. It constructs the new unary AST nodes directly because ordinary
nondependent source expressions are lowered by Sema before reaching those
fallback paths. This is a compiler API boundary test, not a claim that normal
source reaches every path.

Source changes are small patches against the witnessed compiler source. Compile
only changed translation units using their original CMake argv, insert them in
copied archives, verify extracted member bytes, and relink to a new compiler.
Retain corrected Parser/Sema archives from KRN-005. Original inputs stay intact.

Dependent expression mangling may use the public Itanium vendor expression
grammar `u <source-name> <template-arg>* E`, as used by Clang's __alignof__.
See the [primary ABI specification](https://itanium-cxx-abi.github.io/cxx-abi/abi.html#mangling-expressions).
Demangling, independent expected builtin/type distinctions and separate source
declaration/definition agreement must be checked. This does not establish an
exact match to Apple's private extension or platform ABI.

Additional checks cover actual C/C++ metadata, dependent templates and PCH
serialization/consumption. Reject malformed/wrong-target PCH and unsupported
type layouts. Attempt genuine selected XNU source units with traced E1S/private
defines and witnessed header roots; retain exact missing exports/configuration
rather than inserting invented stubs or disabling metadata checks.

No phone commands, APK installation, root, firmware/SDK acquisition, reboot or
flash are part of this procedure. Android-app/native scopes remain false.

## Reproduction

    python3 tools/build/xnu_compiler_hardening.py --run fresh-baseline --mode baseline

Baseline is expected to return1, preserving real unsupported/invalid behavior.
After recording it, build the correction in a fresh registered experiment:

    python3 tools/build/xnu_compiler_hardening.py --run fresh-ast --mode harden

Record its evidence capsule, then select its exact absolute compiler path and
registered experiment ID for independent serialization/configuration checks:

    python3 tools/build/xnu_compiler_hardening.py --run fresh-pch --mode qualify \
      --compiler /home/egor/dev/pet/s24-ios-exynos/artifacts/xnu-compiler-hardening/ast-patch-session1/clang \
      --compiler-evidence HARDEN-002

For the existing component, the retained full regression command is:

    python3 tools/build/xnu_compiler_types.py --run fresh-hardened-regression \
      --clang /home/egor/dev/pet/s24-ios-exynos/artifacts/xnu-compiler-hardening/ast-patch-session1/clang \
      --frontend-evidence state/evidence/HARDEN-002.json \
      --expanded-controls --e1s-profile --compile-interfaces \
      --qualify-supported-profile --unevaluated-void-port

Normal commands have90-second limits and host compiles/links180 seconds.
The maintained runner terminates its host process group on timeout; core dumps
are disabled. No observed build timed out, and all sessions are terminal.

## Acceptance and handoff

The four KRN-006 criteria are assessed in acceptance.json against actual artifacts
and immutable evidence. Generated task views reflect registry state only; they
do not attest a live agent or prove an experimental result.

Next: inspect the real selected configuration generator and component config
recipes in KRN-007; build in new paths and compile the genuine units with actual
generated inputs. Preserve all previous witnesses and failures. Do not change
the original owner's prepared source/build task or invent kernel declarations.

Full Apple/private compiler ABI, complete export/SDK closure, selected DriverKit
interoperability, kernel linking and recovery remain separate gates. No physical
phone, APK, root, reboot, flash, downloaded Apple archive/SDK/firmware or global
compiler/header/package modification occurred. Radio/userland input gates and
all native GPU/Wi-Fi/SIM/eSIM capability claims remain unchanged.

This goal turn made concrete independent host progress. No external input is
needed to start KRN-007, so the overall research/implementation goal stays active.
