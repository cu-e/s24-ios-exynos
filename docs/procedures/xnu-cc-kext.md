# ARM64 cc_kext compiler runtime

KRN-025, owner `codex-team-cc-runtime-20261105-az`.
Branch/worktree: `team/krn-025-20261105` / `worktrees/krn-025-20261105`.
Host work only. No phone, firmware, SDK binary or global tool installation.
Full kernel linking, corecrypto, private Apple ABI and device execution remain
separate gates. A helper link probe is not a kernel or a boot test.

## Exact driver and runtime sources

[Selected Clang Driver.cpp](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/Driver.cpp)
lines482–497 rewrites `-lcc_kext` to `OPT_Z_reserved_lib_cckext`.
[Darwin.cpp](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/ToolChains/Darwin.cpp)
lines2839–2870 selects `RESOURCE/lib/darwin/libclang_rt.cc_kext_ios.a`
for iPhoneOS and silently omits it when absent. This is compiler support,
not a corecrypto provider. KRN-024 retains the absent-resource diagnosis.
The runner checks exact Git blobs against the actual compiler source lineage.
`patches/cc-kext-runtime/inputs.json` pins all driver source hashes.

The actual compiler is
`artifacts/xnu-compiler-cxx-storage/source-build-session2/clang`, SHA256
`7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82`.
Its LLVM version declarations identify17.0.6. Compatible public compiler-rt
comes from [LLVM17.0.6](https://github.com/llvm/llvm-project/tree/6009708b4367171ccdbf4b5905cb6a803753fe18/compiler-rt),
full commit `6009708b4367171ccdbf4b5905cb6a803753fe18`, under
Apache-2.0 WITH LLVM-exception. This is not a private Apple runtime oracle.

The genuine builtins CMake source expressions and Darwin exclusion/architecture
functions select the sources. The cc_kext branch intentionally excludes without
MIN_VERSION: kexts cannot depend on libSystem's builtin providers. All six genuine
Darwin profiling sources are included. Actual native atomic, assembler LSE and
unwind-header probes pass, selecting287 objects including125 outline atomics.
The runtime uses `-mkernel`, `KERNEL_USE` and original Darwin visibility/optimization
flags. The target is explicitly plain ARM64/iOS16.5; upstream's generic iOS6.0
minimum is recorded as context, not the selected deployment target. ARM64e/PAC
and other platforms are not qualified.

## Genuine public declaration inputs

CCKEXT-004 binds472 complete compiler-rt builtin/profile/include/cmake and
root files to exact primary Git blobs. The release XZ download had a truncated
unused-test tail; it is not represented as a complete release archive. Only
verified source subtrees were recovered into a fresh immutable snapshot.

CCKEXT-013 binds149 declaration source files, using Apple Libc1534.100.14
`a61a5933206342413af76579500f313a045c1c33` and named public header blobs at
existing PureDarwin revision `6982ddbfca1047c86680ec7c66da152789746efd`.
The inventory includes actual source symlinks, such as gethostuuid.h, and verifies
both the link payload and terminal source blob. Ambiguous or missing sources
are rejected. HTTP200 does not establish complete content: truncated responses
were rejected by Git blob hashes, with bounded Git-object fallback retained.

Real selected XNU scripts generate symbol-aliasing and POSIX availability headers
through an owned availability-tool prefix. That prefix is not an SDK. Explicit
`-nostdinc` plus resource-first system include order prevents host Linux header
fallback. Libc's raw sys/cdefs.h is a build-internal wrapper explicitly marked
not-installed and absent from native SYS_INSTHDRS; it is excluded from the
staged declaration tree. The real XNU cdefs and genuine generated headers are
used instead. No `_LIBC_NO_FEATURE_VERIFICATION`, fake FILE/pthread types or
function-removal substitute is supplied. Public declaration inputs remain a
measured source subset, not a complete SDK or private ABI qualification.
Original per-file Apple/BSD/APSL/Apache notices remain in source snapshots.

## Signed-shift correction and arithmetic evidence

CCKEXT-014 built287 native objects, the genuine archive,318 defined external
symbols and509 dependency witnesses. Its full ASan+UBSan host arithmetic test
found an actual negative signed left shift in original `ashrti3.c:34`.
`int_lib.h` documents two's complement and arithmetic signed RIGHT shift;
no reviewed native flag defines negative signed LEFT shift. Preserve that
failed experiment and original diagnostic.

The owned patch converts only the high word to `du_int` before the cross-word
left shift. Unsigned conversion preserves its word bits; the branch bounds the
shift to1..63. Signature and every selected runtime function remain unchanged.
The patch/base/postimage/license are bound in
`patches/cc-kext-runtime/source-pin.json`.

CCKEXT-015 passes305 checks: only the affected native TU is actually recompiled
with its recorded native flags;286 actual native object bytes are retained;
the complete archive is rebuilt and all members/symbols re-inspected. The
original source reproduces the UBSan failure as a negative control. Corrected
source passes full ASan+UBSan at O3 over10,128 integer cases and1,281,025 arithmetic
right-shift cases, including every valid shift count, signed boundary patterns
and random128-bit values. The shift oracle uses only unsigned64-bit limbs;
products use shift-add and quotients/remainders are constructed, avoiding calls
to the helper under test as an oracle. No sanitizer category is disabled.
These are host x86_64 source tests, not execution of ARM64 objects.

Measured native Clang17 code bytes are unchanged by the source correction:
the old/new ashrti3 object SHA256 is
`c965a5b0a688a78528abf9b74d4e65826a8c01ee87a1cf6c10ecd8fec73ae077`.
The rebuilt287-member archive SHA256 remains
`67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5`.
Do not infer a full UB-free-source claim for all287 runtime components.

## Driver controls and integration

Run only after registering an experiment in the MAIN ledger. Canonical existing
experiment IDs resolve through that registry across worktrees:

```sh
python3 tools/build/xnu_cc_kext.py --run FRESH_CORRECTION --mode build-recheck --source-run CCKEXT-004 --build-run CCKEXT-014
python3 tools/build/xnu_cc_kext.py --run FRESH_CONTROLS --mode controls --source-run CCKEXT-004 --build-run CCKEXT-015
```

The controls rebuild the real archive deterministically with native libtool and
`ZERO_AR_DATE=1`, compare every member with actual object bytes, independently
compare LLVM architecture/symbol output, and exercise original Clang's explicit
resource lookup. A transparent owned wrapper records the exact executed native
linker argv and compares it to `-###` expansion. The tiny helper image must link
actual div/mod/multiply/corrected-shift providers without unresolved imports.
Real missing, corrupted, incomplete, foreign-architecture and wrong-platform
archives are rejected or fail the controlled link; forwarding literal
`-Wl,-lcc_kext` demonstrates that bypassing the reserved driver mapping fails.
An owned parent/child timeout fixture ignores SIGTERM and must reach bounded
SIGKILL escalation with no live owned descendants.

The final explicit resource tree is for LINKING existing objects. Retain the
separately qualified resource headers used to compile XNU. Pass
`-resource-dir ROOT` only to the selected link command, preserving outer
`-lcc_kext`. KRN-024's restoration of literal backend `-lcc_kext` was a diagnostic
for the absent runtime; do not restore that raw library flag when the genuine
absolute compiler-rt archive already expands. No libcc_kext.a renaming, global
resource installation or copied SDK is needed.

All287 members are inspected, including upstream userland-calling/profiling
members. Their47 remaining external imports, including kernel/libc/unwind and
linker section-magic symbols, are explicit in report.json. This is not complete
all-member runtime closure. The selected full-kernel link retains lazy archive
loading; the tiny helper proof cannot establish full exports/aliases, profiling,
crypto, kernel boot or Apple interoperability.

## Resource limits and immutable evidence

Exclusive coordinator lease: at most2 compiler jobs (runner uses sequential
compiles), aggregate owned-child RSS at most2GiB, MemAvailable floor4GiB, actual
PSI/RSS sampling, whole-run deadline and finite process-group termination. Native
full-source surveys observed about61MiB peak owned-child RSS; corrected host tests
observed about73MiB. The stop fixture is an actual owned-process test, not a
promise about recovery from external SIGKILL or about returning a phone to Android.

Each fresh prefix retains its runner/fixture bytes, actual commands/exits,
stdout/stderr, tool/source/dependency/archive hashes, pressure observations,
Git commit and evidence.json. Registered parent capsules are checked against
ledger and artifact hashes before reuse. Shared references, original compiler,
original resource directory and old capsules remain untouched. All Git commands
use `GIT_NO_LAZY_FETCH=1` and `GIT_OPTIONAL_LOCKS=0`.

Preserved failures:001–003 download/tree/XZ truncation;005 first missing header;
007 include-order/generated-header/feature-extraction issues;008 truncated named
blob rejection;010/012 exact declaration gaps;014 original UBSan finding.
Passing source/header steps are004/006/009/011/013; corrected runtime is015.
The coordinator owns independent review, integration and common `make check`.
Keep KRN-025 in progress until that acceptance.

CCKEXT-016 proves actual positive driver/helper linking and missing/corrupt/
incomplete controls, then retains a fixture prerequisite failure: the selected
compiler has only an AArch64 backend. The foreign-x86 negative uses the existing
multi-target NDK Clang with its actual tool hash; positive/platform probes retain
the selected original compiler. No compiler rebuild or native-runtime change.

## Final integration handoff — 2026-11-05

Host acceptance is ready for coordinator/independent review. Implementation is
frozen in commits `c512e44` and `c0c69ee`; the final handoff update changes prose
only. KRN-025 stays in progress until coordinator review/integration and main
checks. The exclusive heavy-build lease is released; no compiler/linker/test
process remains running.

- Corrected arithmetic/native component: CCKEXT-015,
  `worktrees/krn-025-20261105/artifacts/xnu-cc-kext/corrected-session1/evidence.json`,
  SHA256 `3f9695b97c1525f77282814c2652e9e3bf1d4b989b6cb97224d3cc08b94bb34b`.
  Actual305 checks across16 commands pass, including the expected original UBSan
  negative exit1. Full ASan+UBSan success applies to the tested integer harness
  and functions, including the corrected shift source; all287 runtime behaviors
  were not executed or qualified.
- Final driver/resource/archive/stop component: CCKEXT-017,
  `worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/evidence.json`,
  SHA256 `27244be434d4f27a45734f4c18565646bb3138a1888294d0303b431353ec1c96`.
  Actual343 checks across32 commands pass at implementation commit
  `c0c69ee1fe8d0ac84dbc7700dfaf5e03b2e1cce6`.
- Integration descriptor:
  `worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/qualified-component.json`.
  Link-only resource root:
  `worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive`.
  Actual287-member archive SHA256:
  `67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5`.

The positive native helper image exists, has no unresolved imports, and contains
actual div/mod/multiply/corrected-shift providers. Executed native linker argv
matches Clang expansion exactly. All six negative link cases exit1 with no image:
missing, corrupt, incomplete, foreign CPU, wrong platform and literal-library
bypass. Independent profile diagnostics reject x86 as non-ARM64 and macOS as
non-iOS16.5. Two native deterministic archive rebuilds match byte-for-byte.
The intentional owned parent/child timeout exits -9 after SIGKILL escalation
in3.556seconds and leaves no live owned descendants. The control run observed
43,724,800bytes peak owned-child RSS; this is a sampled measurement.

Acceptance assessment: source mapping/pins/native selection are established;
actual compatible public runtime build/member/ABI-surface/resource/negative
controls are established within the stated source/header/target scope;
reproducible hashes, original failures and integration handoff are retained.
No empty success archive, synthetic provider or skipped selected function was
supplied. One explicit licensed source correction is recorded, with the other
286 native member bytes retained and the current native machine code unchanged.

Coordinator next: independently review the frozen implementation and capsules,
integrate owned commits, run main `make check`, then decide completion. Feed the
qualified link-only resource root to the original driver for the current coherent
kernel graph, preserving outer `-lcc_kext` and native flags/FHDR/current-pthread
inputs. The new full native link will measure remaining export/private-IIG/
crypto/runtime gaps. This executor did not run or claim the common main checks,
full-kernel construction, native ARM64 execution or any phone operation.
