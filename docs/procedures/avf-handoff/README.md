# VM-005: genuine AVF shim to an owned synthetic CPU fixture

Date: 2026-11-05. Owner: `codex-team-avf-handoff-20261105-bd`.
Branch/worktree: `team/vm-005-20261105`, `worktrees/vm-005-20261105`.

The unchanged pinned AVF Image actually handed control to the owned synthetic
arm64 Mach-O under the qualified generic QEMU. The fixture checked EL1, disabled
MMU, entry address, bootargs, command cookie, translated Apple device tree and
HVC PSCI, printed its conditional **SYNTHETIC PASS**, and powered off through
PSCI SYSTEM_OFF. Wrong-cookie and bad-Mach-O cases were rejected; a separately
compiled spinning guest was stopped by the owned host deadline.

**This is a synthetic privileged CPU fixture, not XNU, PID 1, iOS or an S24
hardware result.** VM-002 still lacks a complete qualified XNU guest kernel and
actual XNU/owned-PID-1/guest-stop evidence. No VM-002 implementation or original
artifact was changed. Upstream shim messages naming XNU describe its intended
use; they do not identify this fixture as an XNU kernel.

## Bound inputs and actual address contract

[`inputs.json`](../../../fixtures/public/avf-handoff/inputs.json) pins:

- Scion AVF source commit `a6f4bc38aa244359cd365c976244a88c9d6b3304`.
- Genuine 35,368-byte Image SHA256
  `283f6740424011959ebe03e71ce910a81bbfa3b7ba31c6395ab6f8aab77eaf87`.
- QEMU source commit `698104725efad4b29079d857dfdebbd804e34c99`.
- Qualified generic QEMU binary SHA256
  `bca8564182c786eb00e9f43c3153328f68e2edf50bfabe28236dbaac438acc11`.

The verifier checks both build reports, all thirteen recorded shim source,
header, linker/generator and license hashes against the full donor SHA, and
three QEMU board/boot/PSCI files against the qualified source manifest. All child
commands receive `GIT_NO_LAZY_FETCH=1` and `GIT_OPTIONAL_LOCKS=0`; missing source
objects fail instead of hydrating a shared promisor checkout. The guard flags,
source-read commands/exits/hashes, tools and reused supervisor hash are recorded.

Scion's root LICENSE covers the AVF loader/tools with MIT and its kernel
derivatives with APSL 2.0; the existing source artifact retains the license
texts. QEMU's GPL/component notices remain in its qualified source artifact.
No upstream code or binary is vendored here. `synthetic.c` and the new verifier
are owned code derived from the documented interfaces. Existing Clang and the
source-built ld64 compile/link a real static arm64 Mach-O without libc, dyld,
SDK, IPSW or Apple userland. ld64 warns about a missing default framework search
directory; no framework is linked.

QEMU `hw/arm/virt.c` supplies virtual RAM at `0x40000000`, PL011 at
`0x09000000`, GICv3 at `0x08000000`/`0x080a0000` and HVC PSCI. Its
`hw/arm/boot.c` moves a nonempty arm64 Image with zero text offset 2 MiB above
RAM, avoiding its boot stub. The actual shim console confirms loading at
`0x40200000` and receiving its FDT at `0x48200000`. No address/header patch was
applied to either input.

The genuine shim's virtual base is `0xfffffff004000000`; it requires Mach-O
segments at or above that base plus 48 MiB. The synthetic text begins at
`0xfffffff007000000`; its real LC_UNIXTHREAD entry translates to `0x43002de4`.
With 256 MiB guest RAM the shim constructs a 224 MiB window, Apple DT at
`0x4300c000`, bootargs at `0x4301c000` and top at `0x43020000`. These values
agree across the actual Mach-O segment oracle, shim console and executed guest.
The 64 MiB spare-memory condition is satisfied without a larger RAM lease.

The guest parses the actual translated Apple DT with bounded depth/count/data
checks and strict-alignment loads. It checks root, chosen DRAM base/size and PSCI
method, UART compatible/address and GIC compatible/distributor/redistributor.
An independent host parser inspects a real QEMU-generated DTB from the same
board/payload options. That dump is a separate QEMU invocation before CPU start;
ephemeral randomness need not be byte-identical to the runtime FDT. The runtime
console and guest checks establish the actual handoff properties.

## Controls, resources and reproduction

Four real QEMU cases run sequentially, one vCPU and 256 MiB guest RAM each:

| Case | Required actual result |
| --- | --- |
| positive | Conditional synthetic pass, matching entry/bootargs/DT addresses; natural PSCI exit 0 |
| wrong-cookie | Executed guest rejects the cookie, emits no pass marker and powers off |
| bad-magic | Unmodified shim rejects the corrupted owned Mach-O entry; guest never entered |
| spin-timeout | Separately compiled guest enters and spins; host stops only its new session after three seconds |

Initial bound validation `run-2-bound` measured positive exit 0 in 0.092 seconds
and the actual spinning-guest timeout in 3.107 seconds, with no surviving owned
process. The final commit-bound measurements, target/object/payload/console
hashes and exact commands are in `evidence.json` and its existing artifacts.
`run-1` and `run-2-bound` remain preserved; neither is rewritten.

Final guarded validation ran at implementation commit
`221923b2a7ee28bd2bb4c5f56a73a777a9d29476`:

| Measurement | Actual result |
| --- | --- |
| Positive CPU handoff / natural PSCI stop | Exit 0 in 0.134 seconds |
| Wrong-cookie guest assertion | Rejected, no pass marker; exit 0 in 0.141 seconds |
| Bad-Mach-O genuine shim assertion | Rejected before entry; exit 0 in 0.140 seconds |
| Executed spin control / host stopping | Three-second deadline; stopped/reaped in 3.105 seconds |
| Largest sampled source-build total RSS | 81.67578125 MiB |
| Largest sampled guest total RSS | 64.72265625 MiB |
| Read-only source proof | Fourteen successful guarded Git reads; thirteen shim bindings and three QEMU source bindings |
| False-source metadata controls | Two expected exit-2 rejections before target compilation or guest execution |

The guest RSS value includes the peak from the preserved bound validation as
well as the final validation; the final guarded guest maximum was
54.73046875 MiB. No live owned process remained after any final case.

The wrapper samples total owned session plus supervisor RSS at 50 ms intervals:
256 MiB budget for one small compiler/linker job and 512 MiB for a QEMU fixture.
Build children additionally have a 512 MiB virtual-address-space cap; core dumps
are disabled. Runs have five-second deadlines, or three seconds for the spin
control, plus finite session cleanup. No guest consumes the heavy-build lease.
The qualified existing supervisor signals only process groups in the newly
created session; after each case the verifier requires no live survivor.

Use a new output directory. Existing input locations are read-only:

```sh
python3 tools/verify/avf_handoff.py \
  --out artifacts/avf-handoff/NEW-run \
  --qemu /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build/qemu-system-aarch64 \
  --shim /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/Image \
  --scion /home/egor/dev/pet/s24-ios-exynos/references/scion-avf \
  --qemu-source /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-004-20261105/artifacts/qemu-host/release-10.2.0/source/qemu-10.2.0 \
  --clang /home/egor/.local/bin/clang \
  --ld /home/egor/dev/pet/s24-ios-exynos/artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld \
  --shim-build-report /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/report.json \
  --qemu-build-report /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build-report.json \
  --qemu-source-manifest /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-004-20261105/artifacts/qemu-host/release-10.2.0/source-manifest.json
```

AVFHOST-002 independently rejects an intentionally false donor report and a
false QEMU boot-source manifest before any object/payload/guest is created.
Only task-local metadata copies are altered; original reports and sources are
unchanged. Its separate capsule is `evidence-bindings.json`.

The task ends ready for coordinator review and main common checks. It uses no
phone/ADB, root, physical hardware MMIO, flash, reboot, global installation,
unrelated-process signal, Linux substitute or new SDK/binary acquisition.
