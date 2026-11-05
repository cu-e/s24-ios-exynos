# Guest compiler runtime resource lookup

VM-023, 2026-11-06, owner `codex-guest-exec-20261106-de`.
Worktree `worktrees/vm-023-20261106`, branch `team/vm-023-20261106`.

The qualified source-built compiler actually selects the accepted genuine
compiler-rt `libclang_rt.cc_kext_ios.a` for `arm64-apple-ios16.5` in a bounded
driver `-###` invocation. An absent resource root exits **zero while omitting
the archive**. A successful driver exit alone therefore cannot admit this
runtime to a guest link. The verifier requires the exact pinned archive path
once in the emitted linker arguments and no uninterpreted `-lcc_kext`.

No runtime rebuild was necessary. All 287 archive members retain their exact
qualified bytes, plain ARM64 Mach-O architecture, iOS16.5 deployment version,
definitions and imports. The verifier binds all 287 original member compile
witnesses to actual source hashes, including the genuine CMake-generated
outline-atomic wrappers and the accepted unsigned-shift correction. Original
and corrected command records remain distinct. The historical initial build
failed its host integer semantics check; its failure and the later accepted
correction are preserved explicitly.

There are **47 external names across the whole archive**, including kernel,
libc and linker section-magic dependencies. These are reported, not replaced
with stubs or treated as resolved. Archive selection does not prove which
members a complete guest kernel needs, final reference closure, complete
runtime behavior, corecrypto, private Apple ABI, or guest execution.

## Resource namespaces and exact inputs

The runtime resource root is **link only**:

```text
worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive
```

It must never become the kernel compile-header resource root. This verifier
checks all 1080 immutable guest compile templates retain the selected guest
target, BCM2837 kernel profile and real allocator builtins, and exclude this
link-only root. This is a namespace separation check; it does not independently
accept VM-008, regenerate headers, or measure compiler-header lookup.

The [`inputs.json`](../../../fixtures/public/avf-guest-compiler-runtime/inputs.json)
pins source/recipe reports, the member manifest, parser, source-built compiler,
source-built linker, three genuine compiler-driver source files and the
immutable guest graph. Every input is streamed through SHA256 before and after
the check. No binary from an SDK, prebuilt kernel, native E1S object, or
board-sensitive archive is consumed. The qualified board-neutral cc_kext
archive is inspected directly; its compiler is hashed and used only in
driver-only mode.

| Input | SHA256 |
| --- | --- |
| Qualified archive | `67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5` |
| Qualified compiler | `7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82` |
| Qualified linker, emitted only | `f3cab070fef2c3fb39687e31bab86193f34ab95215fc4dbc8783f2a4f741563e` |
| Guest graph | `afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd` |

The pinned driver source revision is
`fa9443738c1a18accef4244732ec6d6ee97a8133`; compiler-rt is
`6009708b4367171ccdbf4b5905cb6a803753fe18` (17.0.6), with the already accepted
`ashrti3.c` unsigned cross-word shift correction. Source facts are recorded by
file hash and line in the report. `Driver.cpp:494` rewrites the reserved library
name even under `-nostdlib`; `Darwin.cpp:2845` constructs the resource path and
`:2867` permits absence by omitting the library. The actual positive and
missing-resource outputs match these source facts.

## Reproduction and resource admission

Source/archive inspection launches no compiler:

```sh
env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 -s tools/build/avf_guest_compiler_runtime.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-compiler-runtime/NEW-source-check
```

Root explicitly admitted this task's bounded driver-only qualification
independently of VM-008 namespace acceptance. Reproducing the driver experiment
requires equivalent root resource admission; the CLI string records that
admission and does not grant it:

```sh
env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 -s tools/build/avf_guest_compiler_runtime.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-compiler-runtime/NEW-driver-check \
  --driver-lookup --admission root-driver-only-20261106
```

Each driver command requires three MemAvailable samples at least one second
apart, each at least 4GiB. A 15-second deadline, sampled 256MiB combined
controller/driver HWM limit, and sampled child detection bound each owned
session. HWM comes from `/proc/PID/status` only after `/proc/PID/exe` identifies
the current compiler image. This avoids confusing inherited Python process
memory with the current driver. The controller remains below the same limit.

The explicit `-x object /dev/null` input is only a non-provider argument to
driver `-###`. No frontend, assembler or linker consumes it, and no object or
output image is produced. The printed linker arguments are a lookup probe,
not a complete DEVELOPMENT kernel link recipe. The qualified linker is hashed
and selected in that printed recipe, but never executed.

Five source/parser controls reject truncated genuine archive bytes, a modified
actual member with foreign CPU, a wrong deployment version, link-only resource
reuse in the compile namespace, and the wrong guest target. The sixth control
invokes the actual driver with an absent resource tree and measures omission.

The final implementation commit is `0e44b04`; the final retained run is
`artifacts/avf-guest-compiler-runtime/final-0e44b04`. Both driver exits are zero;
both process groups are empty afterward. Maximum sampled current-driver HWM
is 40,476,672 bytes, controller HWM 83,382,272 bytes, combined 123,858,944 bytes.
Minimum sampled MemAvailable during these commands is 17,045,835,776 bytes.
These are measurements of this bounded lookup run, not kernel build estimates.

`prepare-1` preserves an initial verifier failure caused by assuming every
source path was under the unpacked source root; genuine generated wrappers
were then bound through the accepted dependency manifest. `driver-1` preserves
an inconclusive first attempt to sample compiler HWM after a host-wide `/proc`
scan outlasted the short-lived driver. Direct current-image sampling corrected
that measurement issue. Passing `prepare-2`, `driver-2` and the final run are
retained separately. No failed attempt was overwritten.

Independent review, integrator acceptance and fresh common repository checks
are still required. There was no QEMU, full kernel compile/link, guest runtime
execution, phone operation or native-device qualification in VM-023.
