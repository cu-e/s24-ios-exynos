# KRN-002: isolated host tools

Build only reviewed pinned open-source generators and qualify the actual installed Mach-O tool behavior. Apple SDKs, userspace, firmware and phone operations are outside this procedure. Do not run the donor setup or a rolling Theos installer, and do not create global compiler symlinks.

## Installed LLVM capability experiment

Register LLVMTOOLS-001 under KRN-002 before execution. Use the already installed NDK28.2.13676358 Linux LLVM executables by explicit absolute path. In a new artifacts/xnu-host-tools run, compile an owned freestanding C function for arm64-apple-ios16.5, inspect the Mach-O header and exported symbol, create/list an archive, then attempt a Darwin-flavor dylib link without any external SDK/library. Record actual commands, hashes and exit codes; preserve a rejected linker flavor as a failure. Do not infer complete cctools/TAPI or full-kernel support from object/archive success.

## Source generators

The donor declares specific MIG, unifdef and tcsh revisions, listed in RES-008. Pin/check out the actual sources, read their build definitions and component licenses, then build in an artifacts copy with an explicit compiler and prefix. Build-system generators may require additional pinned source dependencies. No system package or PATH mutation is implied. Qualification must run genuine generation/filter/shell fixtures, not only --version output.

The task remains incomplete until the claimed host-tool coverage is actually built and tested. Record missing coverage and precise next steps in research/notes/KRN-002-host-tools.md. A usable tool prefix is an input to KRN-003/KRN-001, never a full XNU build or native acceptance result.

## Owned generator builder

Register HOSTGEN-001 before the first build. `tools/build/xnu_host_tools.py` requires the three exact declared source pins, verified clean local checkouts expanded to their program sources. It copies them into a new artifacts run; it never fetches code. MIG's direct flex/bison/C recipe follows its exact Makefile.am/configure.ac, so no Autotools installation is required for that owned recipe. Preserve its limitations rather than claiming the donor setup ran.

The [MIG patch](../../patches/build-tools/README.md) enables pipeline failure propagation in the artifacts copy. Qualification generates real client/server/header files and rejects valid interface text followed by a preprocessor error. It does not compile or execute generated RPC code against a substituted SDK. unifdef must select both actual branches with its documented modification exit1. tcsh builds from its existing configure script with NLS disabled and runs a real arithmetic/control-flow fixture with startup files disabled.

```sh
python3 tools/build/xnu_host_tools.py --run unique-generator-build \
  --cc /usr/bin/cc \
  --preprocessor /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang \
  --termcap-library /usr/lib64/libtinfo.so.6 \
  --jobs 2
```

The shared subprocess budget is600seconds; individual commands are capped at300seconds. Builds and licenses stay in the private run prefix, and exact commands/source snapshots/hashes remain in its report. This host budget is not a device recovery watchdog. A passing generator run covers these tools only; full cctools/TAPI, XNU linker flags, selected SDK ABI and full kernel remain explicit gaps.

HOSTGEN-001 retained an actual tcsh configure failure after passing MIG/unifdef fixtures: tgetent was not linkable through the unavailable unversioned development libraries. HOSTGEN-002 supplies the observed existing versioned libtinfo file explicitly through LIBS, records its resolved path/hash and leaves system library/package state untouched. It is a separate experiment, not a relabeling of001. The source already declares its terminal entry points; no invented header or stub implementation is used.

## Kernel linker compatibility subset

Register LLVMTOOLS-002 before using the installed LLVM Darwin linker with a source-derived subset of actual ARM64 XNU flags: static/PIE, high image base, section renaming, segment ordering and protections from the prepared tree's MakeInc.def. Reuse the genuine owned object from LLVMTOOLS-001; record that exact input digest and source-file digest. This is a small linker compatibility fixture, not a full XNU invocation. A nonzero exit or a warning that requested behavior is unimplemented/ignored must fail the claimed compatibility. An earlier simple dylib success never clears this gate.

## Real cctools/ld64 source build

Register MACHOTOOLS-001 before running `tools/build/xnu_macho_tools.py`. It requires clean, source-expanded pinned checkouts of cctools-port904de2a7..., apple-libtapi fa944373... and host swift-corelibs-libdispatch137b6cf3.... These are open-source build tools/runtime, not an Apple SDK or the selected kernel's separate libdispatch/firehose dependency.

```sh
python3 tools/build/xnu_macho_tools.py --run unique-macho-build \
  --clang-bin /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin \
  --jobs 2
```

The owned builder copies sources to artifacts/xnu-macho-tools, configures host dispatch/BlocksRuntime without the Swift overlay, verifies actual once/parallel-block behavior, builds TAPI with its bundled LLVM/Clang source and installs into that run's dependency prefix. It then builds real cctools/ld64 with TAPI enabled into a separate tool prefix. It uses reviewed build definitions explicitly, not upstream rolling installers/build.sh. LTO/XAR are disabled consistently with the selected kernel's BUILD_LTO=0 profile; this does not qualify bitcode packaging. The dependency/source pins and actual commands remain recorded.

Qualification must inspect actual Mach-O output for static header semantics, high VM base, requested segment order and protections. It also executes real libtool/nm/otool/nmedit operations, links an owned arm64 text stub and rejects a stub missing the required symbol. No SDK stub is consumed. Ignored/unimplemented linker warnings fail the claim even with exit0. This still does not establish a full XNU link, real SDK/header ABI or kernel execution.

The shared subprocess budget is1800seconds; cleanup signals only process groups launched by this builder. A failed build remains a distinct experiment. For an explicit later experiment, --reuse-dependencies may select a prior run only if its dependency build result, source pins and complete prefix file hashes still match. It never modifies that earlier prefix or silently restarts a failed build. Preserve the exact original failure and builder snapshot.

MACHOTOOLS-001 failed in the actual host libdispatch C++ build before any runtime/ld64 qualification. MACHOTOOLS-002 applies the [one-line atomic-header linkage correction](../../patches/build-tools/README.md) to its artifacts copy, retaining the exact original source pin and first failure. The dependency-reuse check also binds this patch digest. Build and runtime success must be observed separately; a proposed header-order fix alone is not a passing result.

MACHOTOOLS-002 also failed: fixing include order exposed the actual C11 _Atomic versus hosted C++ std::atomic API mismatch. MACHOTOOLS-003 uses the pinned LLVM source header's existing C11 intrinsic implementation under an explicitly local profile, with actual mixed-language layout/operation checks before any runtime build. Both earlier failures remain immutable. The private include path never changes compiler/system files or the selected kernel's dependency profile.

MACHOTOOLS-003 built the actual runtime/TAPI/cctools but failed an overstrict harness assertion. ld64's OutputFile adds generated LINKEDIT after input-section sorting; the XNU arm_vm_init source documents LINKEDIT after DATA and discovers segments by name. The old assertion incorrectly demanded LINKEDIT at the literal third position in segment_order. [Source-bound contract](../../fixtures/public/xnu-host-tools/kernel-layout-contract-sources.json) preserves the exact source hashes. The fixture also omitted the actual general XNU pagezero_size0 flag. MACHOTOOLS-004 corrects those observations, keeps the original segment_order argument, requires real static+PIE/high-base/non-overlap/protections and no PAGEZERO, and explicitly reuses the immutable verified dependency prefix. The original003 failure and bytes remain unchanged; no full-kernel layout is inferred from this small fixture.
