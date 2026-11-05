# VM-004: generic ARM64 QEMU host tool

Owner: `codex-team-qemu-host-20261105-au`. Date: 2026-11-05.
Branch: `team/vm-004-20261105`.
Worktree: `/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-004-20261105`.

This task builds a genuine generic `qemu-system-aarch64` for future VM-002
execution. It does not build or execute an XNU kernel. VM-002 remains blocked
under `codex-team-vm-20261105-am` until actual qualified guest execution reaches
the owned PID 1 and its stopping behavior is measured.

## Sources and licenses

The exact source pins are in
[`fixtures/public/qemu-host/source.json`](../../../fixtures/public/qemu-host/source.json):

| Input | Exact pin |
| --- | --- |
| Primary QEMU release | [QEMU 10.2.0 official source archive](https://download.qemu.org/qemu-10.2.0.tar.xz), 141,093,360 bytes |
| Archive SHA256 | `9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a` |
| Primary Git commit | `698104725efad4b29079d857dfdebbd804e34c99`, independently resolved from primary `v10.2.0` tag |
| Annotated tag object | `75eb8d57c6b9577c8121e28169c3512cfe2d2544` |
| libfdt source | [QEMU's dtc fork](https://gitlab.com/qemu-project/dtc), `b6910bec11614980a21e46fbccc35934b671bd81`, exactly as QEMU's `subprojects/dtc.wrap` selects |
| Local dtc `git archive` SHA256 | `1fb660c56f7c255b930f9763f58e0b3f3c59d1815fa11bc5cb01d01823540ba4` |

The archive was fetched through primary HTTPS and hashed before extraction or
reuse. Its signature was not verified; tag resolution is an independent primary
Git observation, not a claim of cryptographic archive-to-commit verification.
QEMU's LICENSE states GPL version 2 for the emulator as a whole, with component
licenses; TCG includes BSD/MIT and other notices. Firmware in its distribution
has separate licenses. `libfdt` is GPL/BSD dual licensed; the full README.license,
GPL and BSD-2-Clause files remain in the extracted local dtc source. QEMU's
LICENSE, COPYING, COPYING.LIB and per-file notices remain beside its source.
No upstream implementation or binary is committed to this repository.

The official QEMU archive omits the optional dtc checkout, and system libfdt
headers/library are absent here. The exact wrapped dtc source was acquired into
task-local artifacts and archived at its full SHA. No system package was
installed. QEMU's configure uses `--disable-download`/Meson `nodownload`; its
bundled pinned Python wheels provide pycotap locally, while existing Meson 1.8.5
satisfies the source's build requirement. Rust, documentation, extra tools,
guest agent, user emulation and optional features are disabled.

Existing build tools were GCC 15.3.1, Python 3.14.8 and Ninja
1.13.0.git.kitware.jobserver-pipe-1. Installed dependency inventory includes
GLib 2.86.5, pixman 0.46.2 and zlib compatibility version 1.3.1.zlib-ng.
The actual build reports and runtime dependency list distinguish available
packages from libraries the final executable uses. Tool hashes, RPM source
package versions and library hashes are retained in local provenance records.

## Minimal configuration and preserved failures

[`vm002.mak`](../../../fixtures/public/qemu-host/vm002.mak) selects ARM_VIRT and
its genuine CXL dependency closure with default devices disabled. QEMU 10.2.0's
ARM_VIRT selects ACPI_CXL. The first minimal link failed on
`cxl_fmws_get_all_sorted`; enabling CXL and PXB exposed missing Type 3 provider
functions; enabling CXL_MEM_DEVICE linked, but actual generic machine help
aborted because `cxl-rp` lacked `pcie-root-port-base`. PCIE_PORT supplies that
real QOM parent. These are actual source providers and device classes, with no
handwritten stubs. The owned profile is copied to a new content-hash-named
configuration file in the local extracted source. Existing upstream source
files are unchanged. Prior failed profiles and logs remain in artifacts.

The first strict archive extraction rejected an absolute symlink in unrelated
EDK2 ROM source. That failed partial extraction is preserved separately. The
successful extraction excluded only `qemu-10.2.0/roms/` and retained Python's
strict `data` filter for all selected members. No unsafe absolute link was
created. Firmware was neither built nor installed.

The first two build attempts did not spawn configure: the actual memory/PSI
guard refused them. The first compilation's root-PGID-only monitor undercounted
Ninja's separate compiler groups; its aggregate RSS measurement is explicitly
unqualified. This was corrected before subsequent builds to account for every
process in the newly created session. The original logs are retained.

## Build and resource contract

Use a new output directory for each attempt. Source archive SHA256 is checked
before a build. The local source must be extracted from that exact archive,
excluding the unused ROM subtree, with the exact dtc archive extracted at
`subprojects/dtc`. The previous source preparation is retained under
`artifacts/qemu-host/release-10.2.0/`; it is never a shared reference checkout.

```sh
python3 tools/build/qemu_host.py controls \
  --out artifacts/qemu-host/NEW-controls

python3 tools/build/qemu_host.py build \
  --archive artifacts/qemu-host/release-10.2.0/qemu-10.2.0.tar.xz \
  --source artifacts/qemu-host/release-10.2.0/source/qemu-10.2.0 \
  --out artifacts/qemu-host/NEW-build --seconds 2400

python3 tools/build/qemu_host.py check \
  --binary artifacts/qemu-host/NEW-build/build/qemu-system-aarch64 \
  --out artifacts/qemu-host/NEW-check
```

The exclusive coordinator lease permits two compiler jobs and approximately
2 GiB aggregate RSS. The wrapper uses Ninja `-j2`, caps build subprocess virtual
address space at 1 GiB each, samples session-wide RSS/MemAvailable/PSI/swap every
0.5 seconds and stops the owned session if aggregate RSS exceeds 2 GiB. It waits
before starting under low memory/pressure, pauses all owned session groups below
4 GiB MemAvailable or after three high-pressure samples, and resumes above
4.5 GiB with lower pressure. High pressure is memory PSI full avg10 >= 2% or
some avg10 >= 10%; recovery requires full < 1% and some < 5%. Wait/build deadlines
are finite and recorded. The initial resource wait is bounded by the stage
timeout or ten minutes, whichever is shorter.

At a deadline the wrapper continues stopped groups, sends SIGTERM to every
owned session group, waits up to two seconds, then sends SIGKILL to remaining
groups and reaps its direct child. The real host fixtures deliberately put a
child in an independent process group, matching Ninja's behavior, and verify
timeout termination plus actual SIGSTOP/SIGCONT states. Dead orphan zombies are
distinguished from live children; no live owned child may remain.

No swap clearing, cache dropping, global installation or unrelated-process
signal occurs. The existing Android emulator, editor, browsers and other work
are outside the owned session. No phone/ADB, root, MMIO, flash or reboot occurs.

## Interface for VM-002

Pass the qualified local executable's absolute path with `--qemu` to
`src/virtualization/host.py`. It supports the generic `-machine help` / `-accel
help` contract; the future guest command explicitly uses `virt,gic-version=3`,
TCG, `cortex-a76`, one vCPU, the reviewed shim via `-kernel`, the genuine XNU
payload via `-initrd`, serial stdio, no default devices, no network/display/
monitor and no reboot. No LD_LIBRARY_PATH or Android AVD frontend is required.

The host-tool check uses the same board/CPU/serial options with **`-S`, no kernel
and no payload**, then measures stopping of that actual paused QEMU instance.
This exercises the real host interface without running a guest OS. Neither a
paused empty machine nor help output proves XNU compatibility or guest PID 1.
The remaining XNU input must be a complete provenance-qualified QEMU/AVF kernel
with mockfs and the intended PSCI exit configuration. An E1S object closure or a
Linux image cannot satisfy that gate.

## Measured final result

| Check | Actual result |
| --- | --- |
| Final source build | `build-6`, configure exit 0; 1,393 Ninja steps, exit 0 in 94.295 seconds |
| Executable | 25,771,232-byte native x86_64 ELF, generic `qemu-system-aarch64` |
| Binary SHA256 | `bca8564182c786eb00e9f43c3153328f68e2edf50bfabe28236dbaac438acc11` |
| Session-wide compile peak RSS | 938.5703125 MiB; 182 actual resource samples |
| Lowest sampled MemAvailable during final compile | 13.466842651367188 GiB |
| Maximum sampled memory PSI full avg10 | 0.0%; no pause was needed during final compile |
| Real executable help | QEMU 10.2.0; `virt` alias to `virt-10.2`; TCG; Cortex-A76; serial interface all pass |
| Actual stopped empty QEMU | Two-second deadline, exit 0 after own SIGTERM; 2.137 seconds total; no surviving owned process |
| Independent-group timeout control | SIGTERM-ignoring parent/child session stopped with SIGKILL, exit -9 in 3.102 seconds; no live child survived |
| Independent-group pause/resume control | Both actual process groups reached `T` state under SIGSTOP and resumed under SIGCONT |
| Existing VM-002 harness | Read-only invocation with this binary plus existing built shim/PID 1 exits 2 with exactly one missing input: complete kernel; no guest started |
| Source integrity | 12,351 original source files/symlinks checked against the recorded baseline; none changed; only three retained owned profile files added |

Qualified executable, without any installation:

```text
/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build/qemu-system-aarch64
```

The artifact root is `artifacts/qemu-host/` in this worktree. `build-6/` contains
actual configure/compile commands, exits, live resource JSONL and build/tool
provenance; `check-final/` contains the real binary help and stopped-machine
lifecycle; `controls-final/` contains independent-process-group controls.
`check-2/vm002-interface/` is the read-only existing-runner prerequisite result.
`release-10.2.0/` retains archives, license/source manifests, dependency versions,
runtime-library provenance and the original source delta check. The shared
registry resolves these paths with the `worktrees/vm-004-20261105/` prefix.

As its original owner, the agent updated VM-002's primary blocked reason to
remove the now-resolved generic-QEMU prerequisite. VM-002 was neither resumed
nor completed, and none of its implementation files was edited in this task.

Final measurements and existing artifact paths are recorded in `evidence.json`
beside this handoff. Main repository checks and task acceptance remain the
coordinator's integration step. VM-002's original owner/reservation/status are
preserved by this independent host-tool task.
