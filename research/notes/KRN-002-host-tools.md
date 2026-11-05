# KRN-002 host-tool handoff

2026-11-05. Owner: `codex-xnu-host-tools-20261105-j`, main checkout. Three host generators and a real ld64/TAPI host profile now build/pass their bounded fixtures. Full XNU/SDK/archive integration remains separate. No SDK/userland/firmware download, donor setup, global installation or phone command occurred.

## Actual results

| Experiment | Outcome | Meaning |
|---|---|---|
| LLVMTOOLS-001 | pass | Installed NDK28 LLVM19 compiles an actual arm64 Mach-O object, inspects its symbol/header, creates an archive and Darwin-links a small dylib without SDK |
| HOSTGEN-001 | fail | Pinned MIG/unifdef fixtures pass; tcsh configure cannot find tgetent through missing unversioned development libraries |
| HOSTGEN-002 | pass | Explicit installed `/usr/lib64/libtinfo.so.6` permits real tcsh source build; all three host-generator fixtures pass |
| LLVMTOOLS-002 | fail | Real source-derived static XNU flag subset returns linker exit0 but emits warnings that static/image_base/segment_order are unimplemented; this is a semantic compatibility failure |

Reports are under `fixtures/public/xnu-host-tools/`; immutable registry evidence is `state/evidence/LLVMTOOLS-001/002.json` and `HOSTGEN-001/002.json`. An experiment pass covers its stated fixture, not KRN-002 completion. Earlier failures remain unchanged.

## Built prefix and reproduction

Current real prefix: `artifacts/xnu-host-tools/generators-session2/prefix/bin/` containing migcom, mig, unifdef, tcsh and csh→tcsh. Component licenses/notices remain under prefix/share/licenses and the pinned source copies. The binary identities and exact compiler/source/patch/installed-library provenance are in its report; its exact builder snapshot is generators-session2/builder.py. No binaries are committed.

```sh
python3 tools/build/xnu_host_tools.py --run unique-generator-build \
  --cc /usr/bin/cc \
  --preprocessor /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang \
  --termcap-library /usr/lib64/libtinfo.so.6 --jobs 2
```

Use a fresh name and preregister the experiment. Exact source pins: MIG f337e600741638896fb6056ce87c6479f74b89a3; unifdef08d12cd3059fe072929ea001ad9833f5487fd355; tcsh b7db07931546178c4cb2542b5fc850c483628ed5. The builder verifies clean checkouts and the recipe's fixed pins before writing a run. These checkouts have been expanded to their pinned program sources; the initial metadata-only sparse set alone is insufficient for compilation.

MIG's owned direct recipe follows the pinned Makefile.am/configure.ac source list/non-Apple includes with installed flex/bison and explicit host cc. No Autotools package was installed or silently assumed. A one-line attributed patch enables pipeline failure propagation in the build copy. The genuine fixture generates client/server/header sources and rejects a valid interface followed by a preprocessor error. It does not compile generated RPC code against fake SDK headers or execute Mach IPC.

unifdef compiles in gnu11 mode and selects both actual branches, checking its documented modification exit1 and exact output. tcsh uses its existing configure script with NLS disabled, the explicit versioned runtime library, and a real foreach/arithmetic/conditional fixture with startup files disabled. No guessed terminal headers or stub library are supplied.

## LLVM limitation and real ld64

The installed LLVM tools genuinely support the narrow dylib/object/archive operations, but **must not be substituted as the E1S kernel ld64**: the actual static/layout subset emits unimplemented warnings even with exit0. Keep that false-positive guard. `MakeInc.def` source and object digests are retained in LLVMTOOLS-002. The produced kernel-style fixture is not a valid XNU image.

MACHOTOOLS-004 resolves this host linker/tool gap with actual real-ld64 output semantics and archive/export/text-stub tests. Full XNU generated SETUP/symbolset checks remain KRN-001 integration work. Required flags were not dropped and LLVM binaries were not renamed to imply compatibility.

The real candidate is now pinned: cctools-port904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb (cctools1030.6.3/ld64-956.6), apple-libtapi fa9443738c1a18accef4244732ec6d6ee97a8133 (1600.0.11.8), and host swift-corelibs-libdispatch137b6cf3060eae87d9b367c263619c2eca5d3aac. The host runtime is separate from the kernel firehose/libdispatch input. The owned xnu_macho_tools.py builder uses explicit reviewed CMake/configure/make commands, no rolling installer or Apple SDK.

After a real compatible tool prefix exists, KRN-003 handles explicit compiler/E1S board selection and genuine dependency archives with supplied SDK/DriverKit inputs. KRN-001 and NAT-001 retain their original owners/reservations; no native boot/recovery evidence exists from this task.

## Checks and context

Two admission regressions reject escaping run names, excessive job counts and shell-fragment/relative compiler/library paths before run creation. Genuine generator fixtures are separate runtime evidence, not inferred from those CLI checks. `make check` passed115 tests; [check report](../../fixtures/public/xnu-host-tools/checks.json) retains the exact log digest and unchanged original KRN-001/NAT-001/permissions checks.

A GitHub recursive tcsh tree response truncated at131072 bytes; no build was inferred from it. Top-level metadata/local pinned Git access replaced that discovery request. The primary web renderer also failed on the exact three source-tree URLs; local Git/raw primary source was the fallback.

## Real Mach-O source-build continuation

| Experiment | Actual result |
|---|---|
| MACHOTOOLS-001 | fail: NDK19/GCC15 stdatomic C++ templates appear under libdispatch internal.h extern-C |
| MACHOTOOLS-002 | fail: include-order correction alone exposes C11 _Atomic versus hosted std::atomic type incompatibility |
| MACHOTOOLS-003 | fail after genuine runtime/TAPI/cctools builds: overstrict harness incorrectly requires generated LINKEDIT at literal third input-order position; fixture omits actual general XNU pagezero_size0 |
| MACHOTOOLS-004 | **pass:** actual static+PIE/no-PAGEZERO/high-base/non-overlap/protections, real nm/libtool/otool/nmedit and owned arm64 text-stub link/missing-symbol rejection |

MACHOTOOLS-003 actually passes a mixed C/C++ layout/32-update check using the pinned LLVM source header's C11 intrinsic implementation, plus real dispatch_once/32 parallel callbacks. Its real TAPI/ld64 build succeeds. Dependency prefix: artifacts/xnu-macho-tools/macho-session3/dependencies, with exact file hashes and successful dependency-build status in its immutable report. This is not an SDK, kernel or native scheduler result.

The small attributed patches remain in patches/build-tools. 0002 alone did not fix the build;003 selects the genuine pinned LLVM C11 compiler-header implementation only for this host runtime/fixtures. No compiler/system header is modified. The C/C++ test checks actual size/alignment and operations rather than substituting std::atomic types or no-op functions. The original failed attempts stay retained.

The first static-layout oracle was incorrect: ld64 OutputFile adds generated LINKEDIT after the previously sorted input sections. Apple XNU arm_vm_init documents LINKEDIT after DATA and performs named lookup; MakeInc.def general flags disable PAGEZERO. The [source-bound contract](../../fixtures/public/xnu-host-tools/kernel-layout-contract-sources.json) records exact source hashes and the corrected fixture scope. Do not relabel003 a pass. The next run retains the segment_order argument, includes pagezero_size0 and checks actual static+PIE/high-base/non-overlap/protections.

MACHOTOOLS-004 uses artifacts/xnu-macho-tools/macho-session4 and explicitly reuses only the verified immutable003 dependency prefix. It rebuilds cctools in its own new prefix, then tests real static Mach-O bytes, archive/global/export operations and owned text-stub positive/negative cases. The actual terminal report is pass with exit0; no current child build remains running. The earlier003 dependency prefix was verified by all recorded file hashes before reuse and remains immutable. Full XNU/SDK and hardware qualification remain separate.

## Qualified build inputs and remaining integration

[qualified-inputs.json](../../fixtures/public/xnu-host-tools/qualified-inputs.json) identifies the actual generator, cctools and host dependency prefixes and their exact file/binary hashes. The real cctools prefix is artifacts/xnu-macho-tools/macho-session4/prefix/bin with aarch64-apple-darwin-* names. Its runtime/TAPI dependency prefix remains artifacts/xnu-macho-tools/macho-session3/dependencies. The real generator prefix is artifacts/xnu-host-tools/generators-session2/prefix/bin. Do not rename installed LLVM tools or make global compiler/library symlinks.

KRN-003 must consume those inputs through its owned explicit compiler/board profile, qualify supplied SDK/DriverKit provenance and build real E1S firehose/pthread archives. KRN-001 retains full-kernel acceptance, including actual generated SETUP tools, symbolsets and check_all_exports. This toolchain fixture neither runs those full-kernel checks nor qualifies all cctools/TAPI options or every stub format. LTO/XAR are disabled to match the selected no-LTO kernel profile; bitcode packaging is unqualified.

The initial LLVMTOOLS-002 and MACHOTOOLS-001/002/003 failures remain unchanged. Completing this host-input task does not complete the iOS port or authorize native execution.

Final host acceptance: all four bounded tool/runtime fixture groups and `make check`119 tests pass. [Current check evidence](../../fixtures/public/xnu-host-tools/checks-macho.json) also verifies original KRN-001/NAT-001 task bytes and scope permissions remain unchanged. All earlier failure evidence is retained.
