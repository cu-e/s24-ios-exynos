# VM-002 host guest preparation and handoff

Date: 2026-11-05. Owner: `codex-team-vm-20261105-am`.
Branch: `team/vm-002-20261105`.
Worktree: `/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-002-20261105`.

**Actual XNU execution remains blocked. No guest was launched and no PID 1
execution was observed.** The completed preparation consists of a genuinely
compiled pinned AVF shim, an owned static arm64 PID 1 executable, a host-only
launch harness and real host process-termination controls.

## Pinned source and boundaries

The selected donor is [Scion-Project/hackios-xnu-kernel at
a6f4bc38aa244359cd365c976244a88c9d6b3304](https://github.com/Scion-Project/hackios-xnu-kernel/tree/a6f4bc38aa244359cd365c976244a88c9d6b3304).
The primary `research/sources.json` and the read-only local checkout agree on
this full SHA; its working tree was clean when checked. Its root LICENSE covers
the loader/tools with MIT and the kernel derivatives with APSL 2.0. Extracted
source retains LICENSE and LICENSE.APSL beside it in local artifacts. No donor
implementation is vendored in the project source tree. `pid1.c`, the bounded
host runner, payload encoder and source-build wrapper are independently authored;
their ABI/format references are identified in source comments.

Reviewed source includes `avf/README.md`, `avf/qemu-avf.sh`,
`avf/run-probe.sh`, `avf/shim/*`, `xnuloader/mkpayload.py`,
`xnuloader/mkidentity.py`, `userland/src/hello.c` and the open-core Makefile
targets. The phone runner grants permissions, changes global hidden API settings
and invokes Android app/ADB operations; it was not run. The donor QEMU wrapper
selects KVM merely from `/dev/kvm` availability, which is insufficient for an
arm64 guest on this x86_64 host. The owned harness explicitly selects TCG.

The donor's normal identity header is generated from an IPSW. Only the reviewed
`mkidentity.py --placeholder` branch was executed on task-local extracted source:
four empty identity tables, no Apple device-tree data. No SDK, Apple binary,
IPSW, firmware, root, phone, MMIO, reboot, flash, global installation or unrelated
process operation was performed. Existing Android emulators were untouched.

## Actual results

`artifacts/vm-002/inventory-20261105/commands.json` records actual commands,
times, exits and log paths. `artifacts/vm-002/shim-20261105/report.json` records
every extraction/build command and source/tool/artifact hashes. Paths here are
relative to this worktree; the shared registry uses the `worktrees/vm-002-20261105/`
prefix to find them from the primary checkout.

| Check | Measured result |
| --- | --- |
| Host | Fedora 43, Linux x86_64; `/dev/kvm` exists |
| Compiler | Existing Android NDK Clang 18.0.2; no new toolchain installation |
| PID 1 build | Compile exit 0; source-built ld64-956.6 static link exit 0 |
| PID 1 format | Actual arm64 executable; LC_UNIXTHREAD entry `0x100003ddc`; no dyld dependency |
| PID 1 SHA256 | `bc7575a3690d6da52752763c5de496631032bef92777e6fe5b341e8a0e3414f7` |
| Host controls | 12 checks passed: real Mach-O, ten malformed/non-kernel rejections, actual SIGTERM-ignoring child stopped with SIGKILL in less than 5 seconds |
| AVF shim | Five real source compilations, ELF link, relocation inspection and objcopy all exit 0 |
| AVF Image | 35,368 bytes; arm64 Image header; only supported relative relocations |
| Image SHA256 | `283f6740424011959ebe03e71ce910a81bbfa3b7ba31c6395ab6f8aab77eaf87` |
| Existing Android ARM64 emulator | Direct invocation needs local emulator library search paths; with those paths `-machine help` exits 1 and `-accel help` exits 2; it exposes the Android frontend contract |
| Final prerequisite run | Exit 2; existing built shim/PID 1 recognized; complete XNU and generic virt/TCG QEMU contract missing |
| Guest execution | No guest, no measured XNU console, no measured guest PID 1 |

The static linker emitted a missing default `/System/Library/Frameworks/`
warning. No frameworks or SDK were linked; `LC_UNIXTHREAD` and absence of dynamic
load commands were checked against the resulting real Mach-O bytes. This is
not runtime syscall qualification. PID 1's console marker is conditional on
successful `getpid() == 1` and `sysctlbyname("kern.ostype") == "Darwin"`.
It then intentionally exits, which should panic XNU; the donor's AVF exit patch
uses PSCI to stop the guest. Neither that kernel path nor the owned program's
runtime ABI has been measured here.

## Reproduction

Use a new output directory for every invocation. The source builder extracts
only named files from the full donor SHA and uses LLVM binaries beside the
resolved existing compiler. Every subprocess has a 30-second timeout and a
512 MiB address-space limit; compiler jobs are sequential.

```sh
python3 src/virtualization/build_shim.py \
  --donor /home/egor/dev/pet/s24-ios-exynos/references/scion-avf \
  --clang /home/egor/.local/bin/clang \
  --out artifacts/vm-002/NEW-shim-run

clang --target=arm64-apple-macos12 -Os -ffreestanding -nostdlib \
  -fno-stack-protector -fno-builtin -Wall -Wextra -Werror \
  -c src/virtualization/pid1.c -o artifacts/vm-002/NEW-pid1.o

/home/egor/dev/pet/s24-ios-exynos/artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld \
  -arch arm64 -static -e _start -macosx_version_min 12.0 \
  -pagezero_size 0x100000000 artifacts/vm-002/NEW-pid1.o \
  -o artifacts/vm-002/NEW-pid1

python3 src/virtualization/check.py --pid1 artifacts/vm-002/NEW-pid1 \
  --out artifacts/vm-002/NEW-controls
```

The unbounded shell examples for PID 1 above show the exact compiler/linker
arguments; measured invocations used the resource/deadline wrapper recorded in
the evidence. `host.py --help` lists the actual guest arguments. Each of the
kernel, shim and PID 1 inputs requires an explicit reviewed SHA256. Preparation
is the default; `--run` is an explicit launch. The runner checks static arm64
Mach-O structure, rejects the user program as a kernel, builds the XNUP payload,
requires generic QEMU virt/TCG help results and records the exact command.
It disables network, default devices, display and monitor; uses one vCPU,
512 MiB default guest RAM and no host disk attachments. A finite deadline signals
only the newly created process group, escalates after two seconds and reaps the
owned child. The host termination control is a real process test, not a guest.

The runner records `observed` only when a real invocation's console contains both
the Darwin kernel banner and the marker from the owned program; it does not mark
the task done. Independent review must establish actual full-kernel provenance,
the console's origin and the measured termination result. A timeout is retained
explicitly, including whether the host had to stop the guest.

## Specific missing inputs and next action

1. A **complete, linked, provenance-qualified XNU guest kernel** built for the
   selected QEMU/AVF platform, mockfs raw-executable ramdisk and PSCI exit path.
   No such artifact was supplied. The existing E1S component/object work is not a
   kernel image; a future E1S hardware image also does not establish VM board
   compatibility. The read-only selected-kernel preflight exits 2 for missing
   explicit iPhoneOS16.5 SDK and pinned dependency-tool directory. This observes
   that build route's current input gate; it does not assert that every possible
   open-core route inherently needs a proprietary SDK.
2. A reviewed **generic `qemu-system-aarch64` executable supporting `virt` and
   `tcg`**, with tool provenance. No generic executable is on PATH. The installed
   Android frontend fails the required generic help probes; it was not started
   with an AVD or modified. No emulator was downloaded or built.
3. After those inputs are supplied, the coordinator must grant a concrete lease
   for one bounded guest within the shared RSS limit before `--run`. Then build
   the real payload, capture actual Darwin boot and conditional PID 1 output,
   measure guest/host stopping and review acceptance. Do not launch a Linux
   substitute or interpret host checks as guest evidence.

Task VM-002 must remain blocked until this actual execution acceptance is
measured. KRN-001/003/004/008 and the coordinator's kernel work were read-only.
The main repository `make check` is deferred to coordinator review/integration,
as required for this parallel worktree; scoped checks and `git diff --check`
were run here. The planned experiments and evidence are preserved beside this
handoff.
