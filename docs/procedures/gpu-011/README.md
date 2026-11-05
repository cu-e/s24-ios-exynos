# GPU-011: bounded SGPU transport build

Implement the [GPU-006 operation requirements](../../../src/graphics/contracts/README.md) as a versioned little-endian byte protocol. Compile the layouts as C11/C++17 on the host and as freestanding AArch64 ELF plus arm64 iOS16.5 Mach-O. Execute only host validators and synthetic peers. No Apple SDK, iOS runtime, Linux DRM/SGPU ioctl, firmware, device or IOKit driver is exercised.

```sh
python3 src/platform/gpu/abi/check.py --run unique-transport-run
python3 -m unittest discover -s tests -p test_gpu_abi.py -v
make check
```

The script's default cross-compiler is installed NDK 28.2.13676358 Clang 19.0.1; the separate host sanitizer compiler is `/home/egor/.local/bin/clang` (currently NDK 27.1 Clang 18). `cc` supplies the host C/C++ layout and shared-library checks. Inspect actual version/command reports. A run requires a new directory and retains source copies, commands, exit codes, hashes, object headers and failure/pass reports under ignored artifacts/gpu-abi/. No cross-compiled object is executed. Each process has a finite deadline; the ledger timeout itself is only a plan field.

Register a build experiment **before** execution, using this existing file as `--procedure`. The first transport-session1 attempt was accidentally run after the plan registration failed because its procedure argument was prose rather than an existing path. It is retained as an unregistered failed attempt, not retrospectively described as preregistered. That attempt failed while linking host ASan with NDK 28 (missing Linux ASan archives); no sanitizer harness or AArch64 build ran. The next registered experiment uses the separately installed host sanitizer toolchain and keeps the original failure.

Registered SGPUABI-001 / transport-session2 passes 50,000 host sanitizer mutations and AArch64 C compilation, but fails the ELF C++ layout check because an unnecessary const marker is unused under `-Werror`. Preserve the overall failure and those partial results. Remove that marker, retain every layout assertion and strict compiler flag, then use a new registered experiment/run for the corrected build.

SGPUABI-002 / transport-session3 passes after that correction: host C/C++ checks, 50,000 sanitizer mutation/control attempts (36,882 rejected before the callback, 13,118 dispatched to UNSUPPORTED), seven malformed backend reply cases and all eight AArch64 ELF/Mach-O C/C++ objects. This includes valid control packets; it is not 50,000 unique failures or coverage of all possible inputs. No ARM object, IOKit client, native GPU or iOS runtime was executed.

Final review added nonzero/adequate object-size checks and retirement-reply controls. SGPUABI-003 / transport-session4 rechecks the changed C core: **14 malformed backend replies, five valid/timeout controls and the same 50,000 mutation/control attempts pass**. All eight AArch64 object headers, including C++ layout objects, are inspected. Earlier reports retain their original source hashes and outcomes; the session4 report identifies the final tested C inputs.

Review [the ABI definition and integration limits](../../../src/platform/gpu/abi/README.md) before using any result. Passing shape validation is not handle authentication, BO-bound checking, executable command validation, cache maintenance, native waiting or GPU retirement. GPU-007 still needs the actual XNU/IOKit implementation and external build inputs; GPU-008 through GPU-010 retain hardware and OS presentation acceptance.
