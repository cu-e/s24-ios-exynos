# Selected XNU DriverKit generator qualification

Owner: codex-iig-abi-20261105-o; task KRN-004; main checkout;
baseline commit 5a65301. All work is host-only.

## Source inputs and limits

- Selected XNU8796.121.2/E1S source retains the complete immutable KRN-003
  file witness, checked before every use.
- Nyktis/iig-port ea6d147d668ca15d490da638012243fcd705f30d provides the real
  C++17/libclang AST generator. Preserve its MIT LICENSE and NOTICE, including
  the Zilong Tan fasthash notice. Observed DriverKit440 behavior is not a
  qualified selected8796 ABI.
- PureDarwin/iig-tools 28010c688caab7eb5400b9c98faa5b1e538e0108 explicitly
  generates non-Apple FNV IDs. Pinned current PureDarwin generated
  IOService/OSObject files use that tool and are not independent Apple oracles.
- Allenwdk/xnu-linux-toolchain 909990e4ec2c6cda30c20cdb23219946918c7fd6 was
  reviewed as documentation only. Its described unsupported RPC stubs do not
  implement marshalling; a reusable code license is not established.
- Eight published numeric IOService observations in
  fixtures/public/xnu-iig-abi/published-id-observations.json identify
  XNU10063.121.3/DriverKit286. The snapshot is hash-bound, but neither
  authenticated nor a selected8796 oracle. Its header is not an SDK input.
- Public Libc1507.100.9 dbde50970329ace8793fca2b63d708d280c33d88 was a
  source-only lead while locating the setup-header generator. It supplies no
  build input. The real generator is already in selected XNU.

No upstream installer, Nyktis test archive, Apple SDK/binary/firmware/archive,
or global package/header/compiler modification is used. Installed ROCm LLVM19
C API headers/libraries and installed NDK28.2 Clang19.0.1 are explicitly hashed.
Freestanding ARM64 compiles use genuine source/MIG headers without an Android
or Apple SDK sysroot. Preserve their original per-file notices.

## Actual experiments

State/evidence/IIGABI-001.json through IIGABI-013.json bind source/tool hashes,
actual argv/exits, builder bytes and output paths. Reports stay in private
artifacts/xnu-iig-abi/RUN with sanitized copies under fixtures/public/xnu-iig-abi.
Full selected Apple ABI qualification remains false in every experiment.

| Experiment | Actual outcome |
|---|---|
| 001 | Tool builds; two conditional AST controls and eight independent cross-version fasthash facts agree; actual selected ARM64 IORPC is 24 bytes; original CLI rejects all 17 explicit target inputs |
| 002 | Explicit target patch applies; all 17 real IDLs reach missing compiler stdint resource header |
| 003 | Genuine LLVM19 resource headers resolve stdint; selected cdefs requires sys/_symbol_aliasing.h |
| 004 | Actual selected setup-header recipes succeed; 17 generated pairs; zero implementation compiles because exported string.h is missing; overall inconclusive |
| 005 | Genuine osfmk/libsa root export resolves string.h; compiles expose MIG server, compiler builtins and kernelContent gaps |
| 006 | Legacy24 emitter compiles genuine OSObject RPC into arm64 Mach-O; other 16 fail |
| 007 | All 14 actual source-listed MIG server headers generated with qualified real migcom; OSObject remains sole implementation compile pass |
| 008 | Host probe fails on Blocks/accurate host profile; no runtime execution |
| 009 | Blocks resolves; original header overrides explicit OS macros and ROCm ASan archives are missing |
| 010 | Full-source Linux target header/profile assertions compile without diagnostics; GNU sanitizer link fails on missing installed libasan |
| 011 | Actual generated host decoder executes: seven controls pass; truncated guard-page input and null message/callback crash; null reply exits 91 under an invalid optimizer assumption |
| 012 | Harness name collision stops before any compiler command; failed builder/error retained |
| 013 | Corrected Invoke guards pass all 11 host cases; generated ARM64 invocation/layout assertions pass; eight actual generated IDs match cross-version observations; other 16 implementation compiles still fail |

Selected bsd/sys/Makefile SETUP_GEN_LIST calls make_symbol_aliasing.sh
and make_posix_availability.sh. The former consumes the pinned public
AvailabilityVersions115.4 availability.pl (5d9baee345b3bc72b26c71adc65f94f2d5e9ced2),
whose list ends at iOS16.4/macOS13.3. The private tool prefix supplies only its
expected script location; it is not an SDK. No version entries were invented.

The host-only patch uses a private copy of the full licensed RES-009 target
header. Static assertions verify Linux/Unix/x86_64, 64-bit, non-Mach-O and
non-Apple OS profiles. Real ARM64 compiles retain the original qualified
header. The guard-page helper uses genuine Linux libc headers in a separate
translation unit and implements no XNU interface. ASan/UBSan are explicitly
not used by the passing host experiment; earlier failed attempts are retained.

## Reproduce the current bounded result

Register a new experiment before execution and choose a fresh run name.
The CLI's command budget is 300 seconds with at most 60 seconds per command;
the registry timeout is bookkeeping, not a watchdog. Expected overall exit
is 1 because 16 implementation compiles remain failed.

    python3 tools/build/xnu_iig_abi.py --run fresh-iig-run \
      --selected-target-port --compiler-headers --setup-headers \
      --kernel-export-includes --server-headers --compile-generated \
      --legacy-rpc-port --guard-invoke --host-linux-port --host-guard-pages \
      --host-clang /usr/lib64/rocm/llvm/bin/clang++ \
      --cxx /usr/bin/c++ \
      --clang /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang \
      --libclang-prefix /usr/lib64/rocm/llvm \
      --prepared-run artifacts/xnu-prepare/e1s-dependency-source-session1

Current component paths/hashes are in fixtures/public/xnu-iig-abi/components.json
and IIGABI-013. The maintained runner additionally folds generated-ID/layout
checks into its overall classification; saved IIGABI-013 values satisfy them
while full compilation fails. Rechecking those saved values needs no rebuild.

## Handoff and remaining work

This turn produced real host progress: source setup/MIG headers, a working AST
tool, an experimental ARM64 OSObject interface, actual decoder execution and
a measured malformed-input fix. The preceding RES-009 and RIL turns also made
new progress. This is not full-goal completion or a global impasse.

Selected OSData/IOLib/allocation macros require compiler type signature/summary
semantics. Current actual compiles fail there. The donor's constant signature
"12" and broad summary bits are excluded from this IIG qualification. Apple's
[primary kalloc_type explanation](https://security.apple.com/blog/towards-the-next-generation-of-xnu-memory-safety/)
describes compiler granule information and data/pointer separation; constants
cannot establish real allocator metadata. Next independent work is a genuine
compiler/source path for those selected APIs, then the 16 failed compiles.

A selected8796 generated-header/dispatch/marshalling oracle with provenance is
also missing; no local input path has been supplied. Published newer numeric
facts are useful controls, not an exact-version substitute.

Only CopyDispatchQueue_Invoke executed on x86_64. Other methods, dispatch entry
points, descriptor variants, object conversions/lifetimes, user metadata and
Apple interoperability remain unqualified. The guard patch checks method
extents and required pointers before access; it does not harden every generated
path or turn unsupported RPC into a successful stub. No ARM code executed.

No phone command, APK install, root request, reboot or flash occurred.
KRN-001/KRN-003/NAT-001 and radio owners/files remain unchanged. Full native
kernel, GUI/GPU/Wi-Fi/SIM/eSIM and recovery remain unqualified. Optional local
input requests have no supplied path; elapsed time does not supply an input.
