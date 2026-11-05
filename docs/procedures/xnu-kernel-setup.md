# Selected assembly offsets and local version metadata

KRN-013, owner `codex-kernel-setup-20261105-w`, main at parent `303c50d`.
The bounded setup component passes. Full kernel/native iOS qualification remains
incomplete. No phone command, SDK acquisition, global installation or original
compiler/source/header prefix modification was performed.

The direct full recompile produces **952 component arm64 objects** from 961
actual attempts, preserving all 939 prior successes. All thirteen former
assym/version-header consumers compile, including all eight assembly units.
The genuine direct `version.o` also compiles: **953 known direct objects** are
built. Of 978 selected component entries, 26 remain unresolved: 9 compile errors
and 17 missing IIG sources. Three further top-level objects are unattempted, so
29 of 982 known direct objects remain unresolved. Archives, link metadata and
final linking remain separate requirements.

## Actual source and setup rules

Use the [pinned XNU8796.121.2 source](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a),
with recorded E1S donor patches/fixes. The prepared source's actual
`config/MasterVersion` is **22.5.0**. This is source metadata, not an Apple release
or selected private SDK identity. See [attribution](../../patches/kernel-setup/README.md).

The generated osfmk RELEASE/ARM64/E1S/iPhoneOS Makefile selects
`osfmk/arm64/genassym.c`. GNU Make expands the original GENASSYM_KCC/CFLAGS/
INCFLAGS recipe. It compiles that real source to target assembly using `-S`
and `-fno-integrated-as`, then executes the actual original sed extraction.
The historical `genassym.o` filename contains assembly text, not an object.
The result contains 135 target constants and their numeric aliases: 270 defines.
No host-size approximation or manually filled offset is used.

Version generation byte-copies actual `libkern/libkern/version.h.template` and
`config/version.c`, then invokes genuine `config/newvers.pl`. The Linux adapter
replaces the BSD `install -S` copy step with a byte-identical template copy;
no upstream stamping logic is changed. MasterVersion 22.5.0 and selected
`release` configuration are retained. Supported KERNEL_BUILD_DATE/OBJROOT hooks
supply a recorded UTC timestamp and an explicit `s24-ios-exynos-local/...` build
label. Builder identity remains in ignored generated local artifacts. The
selected RELEASE optimization/configuration is distinct from Apple provenance.

The direct version object uses the original MakeInc.kernel C_RULE_1A invocation,
expanded by actual MakeInc.def/rule under the selected top-level target profile.
Its original postprocessor is empty. This directly qualifies this object recipe,
not all top-level kernel validation, segment processing or final linking.

## Source defect exposed after generation

The first affected run compiles twelve of thirteen component consumers plus
version.o. startup.c then exposes a real donor declaration guard mismatch:
`minimac_policy_init` is declared under CONFIG_VNGUARD but called under CONFIG_MACF.
The selected profile enables MACF without VNGUARD. The existing implementation
in `bsd/kern/kern_minimac.c` has signature `void minimac_policy_init(void)`.

The owned patch moves only the existing declaration under its correct MACF
scope. The runner applies it to a copied startup.c and retains original, patched
source, patch and implementation hashes. The original 5111-file prepared tree
is unchanged. A first owned patch had an invalid hunk count and failed before
compilation; its KSETUP-003 evidence is retained. The corrected patch is used by
KSETUP-004. Neither call nor implementation/policy behavior is changed.

## Inputs and reproduction

The compiler is `artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang`,
SHA256 `c218fede38b771ead34b9cad47a4a79e53dc742f8864bb6bade2e0041bcc4dbe`.
Coherent KMIG-003 and KSYSC-002 inputs remain immutable. Input verification
includes the 10889-file compiler source, 198 build inputs, 5111 kernel files,
registered HOSTGEN/KOBJECT/ATCOMP/KMIG inputs and KSYSC-002/004/006/007.
All other owners and device scopes are preserved.

Register a new KSETUP experiment before execution and use fresh run names:

```sh
python3 tools/build/xnu_kernel_setup.py --run NEW_GENERATION --mode generate
python3 tools/build/xnu_kernel_setup.py --run NEW_AFFECTED \
  --mode compile --setup-evidence KSETUP-001 --selection affected --startup-declaration --jobs 2
python3 tools/build/xnu_kernel_setup.py --run NEW_FULL_PROFILE \
  --mode compile --setup-evidence KSETUP-001 --selection all --startup-declaration --jobs 2
python3 tools/build/xnu_kernel_setup.py --run NEW_CONTRACT \
  --mode contract --setup-evidence KSETUP-001
python3 tools/build/xnu_kernel_setup.py --run NEW_AUDIT \
  --mode audit --setup-evidence KSETUP-001 --compilation-evidence KSETUP-004
```

Record a new generated run under its own experiment ID before substituting it
for KSETUP-001. Existing directories cannot be overwritten. The full compile
retains each KSYSC-004 per-file recipe, changing object/dependency outputs,
adding real setup include roots and using only the recorded startup copy when
requested. Actual allocator/type checks stay enabled, with no constant fallback
header or blanket `-w`. All prior 939 successes are rebuilt under the new roots.
Complete argv/cwd/exits/diagnostics remain in hashed reports; evidence labels any
command sample. Host process-group timeouts/jobs provide no phone watchdog.

## Controls and measured evidence

| Experiment | Actual result |
|---|---|
| KSETUP-001 | Pass: genuine genassym/Make/sed yields 135 constants and 270 defines; original Perl stamps local source 22.5.0 metadata |
| KSETUP-002 | Pass for bounded assessment: 12/13 affected consumers and version.o compile; startup guard error retained |
| KSETUP-003 | Fail: owned patch hunk count is malformed; actual source compilation never starts |
| KSETUP-004 | Pass for partial closure: 952 component objects plus version.o, all 13 affected consumers, zero prior 939 regressions |
| KSETUP-005 | Pass: separate target layout/version/mutation checks; original shared expectation fixture sequence retained |
| KSETUP-006 | Pass: same controls with distinct immutable positive/negative input trees |
| KSETUP-007 | Pass: 953 independent arm64 headers, 961 exact recipe associations, 3085 actual dependencies and startup/provider symbols |

The offset control preserves real genassym includes/conditionals/expressions,
replacing only its emission macro with C static assertions against separately
named extracted values. It checks all 135 active constants without redefining the
original type/constants. A real 8-byte TH_RECOVER mutation is rejected. This is
a separate C layout path using the same target compiler, not an independent
Apple compiler or hardware oracle. Raw assembly labels and primary/NUM aliases
must agree exactly. Positive and negative header inputs have separate paths.

Real version.o bytes contain 22/5/0, release stage 0x80 and prerelease 0, matching
MasterVersion and generated header. Its osrelease/config strings and local build
label are checked without publishing builder identity. A real major-version
byte mutation is rejected. The genuine script rejects MasterVersion 0.0.0.
An unknown placeholder is retained by upstream with exit 0; the runner's production
placeholder guard rejects that output rather than pretending upstream rejected it.
Each malformed-input fixture keeps its own immutable directory.

LLVM independently verifies all 953 Mach-O arm64 headers and finds 17050 external
plus 11914 local code definitions. The audit reconstructs every permitted source/
include/output transformation from the actual previous recipe profile, validates
the direct version invocation, captures 3085 actual input files and checks exact
object/dependency associations. startup's undefined `_minimac_policy_init` agrees
with the real defined symbol in the newly compiled kern_minimac object. This
proves symbol agreement, without executing initialization or linking a kernel.
No compiler crashes/timeouts or previous-success regressions occurred.

## Published handoff and remaining work

The [component manifest](../../fixtures/public/xnu-kernel-setup/qualified-component.json)
binds generated assembly/headers/source, constants, local version metadata,
source-port hashes, compiler parents and full object/dependency audit.
Local prefixes are:

- `artifacts/xnu-kernel-setup/generate-session1`: genuine offsets and version metadata.
- `artifacts/xnu-kernel-setup/full-profile-session2`: all 961 component recipes and direct version.o.
- `artifacts/xnu-kernel-setup/object-audit-session1`: 953-object/dependency/source association audit.

Public [compiled component objects](../../fixtures/public/xnu-kernel-setup/compiled-objects.json)
and [unresolved components](../../fixtures/public/xnu-kernel-setup/unresolved-objects.json)
are separate from immutable parent manifests. Their startup entry intentionally
references the hash-bound source copy. Reuse requires matching compiler/command/
header/source-port/dependency bytes, not only the original source hash.

Remaining failed attempts are four missing-header consumers, three deliberately
unsupported metadata types and two source/profile errors. Missing headers are
`arm_neon.h` (one APFS source) and `os/firehose_buffer_private.h` (three sources).
Fixed NEON vectors, C++ member pointers and reference fields remain unsupported
metadata. The printf macro/declaration conflict in mc_provider and undeclared
proc_pid in user_exception_trace remain. Seventeen selected IIG C++ sources
still need coherent full-recipe integration and private ABI qualification under
their existing owner. Three other direct top-level objects and archive/link
closure remain additional work.

KRN-011 covers bounded vector metadata; KRN-014/015 cover genuine firehose
exports and matched compiler resource headers. Full kernel/Apple ABI, live IPC/
syscalls, native boot/recovery, userland, GPU, Wi-Fi and SIM/eSIM operation remain
unqualified. Final repository/task acceptance is recorded as KSETUP-008.
