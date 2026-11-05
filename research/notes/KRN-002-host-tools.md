# KRN-002 host-tool handoff

2026-11-05. Owner: `codex-xnu-host-tools-20261105-j`, main checkout. **In progress:** three host generators now build/pass; a compatible full kernel linker/toolchain remains outstanding. No SDK/userland/firmware download, donor setup, global installation or phone command occurred.

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

## Linker boundary and next work

The installed LLVM tools genuinely support the narrow dylib/object/archive operations, but **must not be substituted as the E1S kernel ld64**: the actual static/layout subset emits unimplemented warnings even with exit0. Keep that false-positive guard. `MakeInc.def` source and object digests are retained in LLVMTOOLS-002. The produced kernel-style fixture is not a valid XNU image.

Next: pin/review a compatible cctools-port/ld64 and, where required for text stubs, TAPI source; build into an isolated prefix using the existing qualified generators/compiler. Trace actual XNU linker, libtool, nm/otool/nmedit and symbolset options. Repeat genuine static/high-address/segment-layout and export/symbol operations using the candidate, checking actual output semantics as well as exit codes. Do not drop required flags, emit success stubs, run rolling installers or rename LLVM tools to imply compatibility.

Primary candidate: https://github.com/tpoechtrager/cctools-port (reviewed README lead only, not pinned or built yet). Its README names libdispatch/BlocksRuntime and TAPI dependencies; source/build requirements must be inspected for the selected exact revision. Optional missing tools may be narrowed only with an explicit coverage record; remaining required behavior must stay on the board.

After a real compatible tool prefix exists, KRN-003 handles explicit compiler/E1S board selection and genuine dependency archives with supplied SDK/DriverKit inputs. KRN-001 and NAT-001 retain their original owners/reservations; no native boot/recovery evidence exists from this task.

## Checks and context

Two admission regressions reject escaping run names, excessive job counts and shell-fragment/relative compiler/library paths before run creation. Genuine generator fixtures are separate runtime evidence, not inferred from those CLI checks. `make check` passed115 tests; [check report](../../fixtures/public/xnu-host-tools/checks.json) retains the exact log digest and unchanged original KRN-001/NAT-001/permissions checks.

A GitHub recursive tcsh tree response truncated at131072 bytes; no build was inferred from it. Top-level metadata/local pinned Git access replaced that discovery request. The primary web renderer also failed on the exact three source-tree URLs; local Git/raw primary source was the fallback.
