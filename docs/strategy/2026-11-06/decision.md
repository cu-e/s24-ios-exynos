# S24 strategy decision — 2026-11-06

**Primary route: C, the existing E1S port with minimal coherent repairs.**
The target is SM-S921B/e1s, Exynos2400. Generic QEMU reproduction is a supporting
bench, not a prerequisite for all hardware source work. Retain the current
1080-object guest. Its bounded direct-link diagnostic has now reached the real
linker and exposed one undefined symbol. Do not finish the broad product controller merely
to obtain linker stderr. Stock upstream reproduction is the fallback bench,
not a second speculative full build.

## Preserved state and evidence classes

MAIN remains `951f23336c1521c8ee94828e26fc98bfcf1e8411`. All1080 current-profile
guest objects, separately qualified tails/components, raw failures and owner
assignments are retained. Unpublished candidate33 `7b4aff686e8d4ce3fd96a1eb0b3f497b6604cfdf`
and its audit stay frozen. CU stopped broad wiring at `4f1b8e711dcaf46eefbe1c23a4b98ab57154e0dd`.
The preservation snapshot, tracked patch, worktree list, task assignments and
artifact-authority hashes are under
`artifacts/team-coordination/20261106-team/strategy-reassessment-20261106/`.
No phone action, source-pin rewrite or destructive cleanup occurred.

Use these categories in future results:

1. **Reproduction:** compiling upstream XNU, running donor QEMU/loader/PID1.
2. **Environment repair:** a demonstrated compiler/header/library/build defect here.
3. **Common-code change:** a genuine reusable fix, such as the PID1 syscall ABI repair.
4. **E1S adaptation:** a board-specific change or contract repair, such as STM decoding or RAM ownership.
5. **Device verification:** an observation on this actual S24. Source, compilation and QEMU do not establish it.

## Reuse versus our work

| Component | Ready solution | Current local use and reason for changes | Next useful S24 result |
| --- | --- | --- | --- |
| Build execution/scheduling | Donor Makefiles and dependency setup. | Sharded execution handled resource bounds; later lock/accounting/cancellation bugs required real fixes. Extra generic scheduling is now deferred. | One genuine link diagnostic; then a coherent E1S configuration, not another scheduler. |
| Hashes/header namespaces | Donor generated exports and matching SDK/dependency tree. | Real missing Firehose exports and APFS resource-root inputs were fixed. Repeated whole-corpus reviews are unnecessary when inputs are unchanged. | Preserve the known closure and derive a distinct E1S10CPU/four-cluster closure when rebuilding; no BCM8CPU relabel. |
| Compiler/linker wrappers | Upstream `xnu-clang`, ld64 and genuine source recipes. | Current public-source-qualified tools/headers differ from stock SDK setup. Source/lifetime/driver-argument defects were local environment/tooling repairs. | Run the unchanged real Clang link once, inspect actual diagnostics; do not create another general wrapper. |
| Loader, RAM root, PID1 | Scion/HakiOS open loader, packaging, hello/libmini and launch scripts. | Existing shim/collector and corrected PID1 are reusable. Their compilation is not S24 adaptation. | Reuse them for minimal validation; first board work is E1S RAM/entry/console. |
| Crypto/libraries | Existing selected provider and compatible runtime/FH/pthread libraries. | Bounded source/ABI/KAT work exists; native crypto feature expansion is separate from early boot. | Preserve known compatible dependencies. Add crypto work only when an actual next E1S result is blocked. |
| Review/common checks | Existing narrow source review and common gate. | They found real FD/signal/parser defects but also created substantial fixture/doc overhead. | Review changed behavior once; run relevant tests and one common gate for an integrated code change. No repeat matrix/corpus without a new failure or changed input. |
| Documentation/tasks | Existing `lab.py`, raw evidence and short handoffs. | The registry remains authoritative; preserved blocked ownership is retained. | Two real tracks and a compact blocker list; no new dashboard/planner/provenance subsystem. |

## Current upstream choices

| Source | Project pin → observed current | Useful change / compatible adoption |
| --- | --- | --- |
| HakiOS | `87bf4851` → `2631f5d7` | Common Make/QEMU/hello/setup blobs are unchanged; most new work concerns Adreno Metal and related input/UI. Stock setup still needs matching SDK inputs. See [HakiOS audit](hakios.md). Do not replace the embedded E1S `d82c64a3` tree piecemeal. |
| Scion | `a6f4bc38` → `8bee16f3`, repository renamed `scion-kernel` | Generic AVF/QEMU/shim/launch/package/hello blobs are unchanged. EFI/platform organization evolved, but no E1S/Exynos2400 donor appeared; the ios27 profile explicitly is not implemented. Keep the accepted PID1 ABI fix. A full update would change coupled kernel/dependency inputs without removing this link/staging gap. |
| iOS-On-S24 | `c8860dec` → `57d0a97e` | Three commits: QEMU capture, console scaling, UART/PSCI/watchdog patches. Same XNU8796.121.2 and embedded `d82c64a3` base; loader/FDT and older E1S patches unchanged. Selectively qualify early-console changes, retain our STM nibble fix, and inspect default-on MMIO assumptions. No upstream phone boot is established. |

## Remaining work, not sunk cost

| Route | Work remaining / main risk | Choice |
| --- | --- | --- |
| A: current guest | Executed: eight Make targets pass; genuine Clang/ld exits1 on only `_iBoot_Stage_2_version` referenced by `SavePanicInfo` in `model_dep.o`. No kernel image. Source guards depend on whether `TARGET_OS_OSX` is defined, with different actual header include contexts between the reference and provider. | The cheap diagnostic was useful. Investigate this precise common-source/environment defect and donor semantics; no dummy symbol, broad controller or automatic relink. |
| B: stock upstream | Ready build/loader/hello/package/runner; coherent SDK/toolchain setup, configuration and resource-compatible UEFI/QEMU reproduction still needed. | Fallback if A shows a broad mismatch or its preparation expands. No parallel full rebuild now. |
| C: E1S | Minimal source repairs and a real E1S profile, followed by measured board entry/memory/interrupt/console work. Device inputs and authorized recovery are still absent. | Primary hardware lane. Actual implementation has started with STR-002, independent of guest boot. |

## Two tracks and concrete blockers

The common track retains compatible source/tools/products, one direct-link
diagnostic and later the smallest donor boot bench. It does not gate all E1S
source work. The S24 track starts with loader RAM ownership and early console,
then one-CPU timer/GIC, RAM-root boot, storage and display/input, and subsequently
GPU/radios. Existing owners and blocked reservations are not reassigned.

| Blocker → result blocked | Ready solution/donor | Concrete missing input or experiment | Independent work now |
| --- | --- | --- | --- |
| Current guest not linked → generic boot bench | Existing genuine Make/Clang recipes and measured1080 products. | Actual diagnostic now identifies one boot-version symbol. Verify the selected target-macro semantics, repair only affected genuine code/inputs and measure an incremental rebuild/link if justified. | E1S source work proceeds. |
| Invalid/incomplete memory exclusions → trustworthy E1S handoff | Existing unchanged E1S loader/FDT parser. | STR-002 actual-C regression and minimal patch: reject incomplete reservations/overflow and unqualified fallback; later complete live DTB/carve-outs. | Started now, no QEMU or phone required. |
| UART/WDT/conduit assumptions → useful first console/halt | Upstream0017–0019 and pinned Samsung DTS/drivers. | Qualify powered accessibility and boot policy; source review of opt-in MMIO, PSCI SMC/HVC,25.6MHz timer and GIC/ADT contracts; later actual EL/IRQ/tick observation. | Narrow source patches/contracts can proceed now. |
| UFS state/ownership → disk root | Existing E1S polled UFS/Samsung donor; RAM/static-init root already available. | Actual S-Boot queue/PHY/power/DMA state and timeout/extent qualification. Read-only blocks still require MMIO/DMA. | Use RAM root first; review bounded queue/timeout code independently. |
| Scanout/panel and input lifecycle → usable UI | E1S framebuffer/STM source, retained nibble repair, exact retail Samsung panel donor. | Live reserved buffer/stride/format/DSC and rails/reset/IRQ/event-loss inputs. | Source extent/format, bus-error and cancellation work independently; no GPU dependency. |
| No native Xclipse/radio backend → GPU/Wi-Fi/SIM/eSIM | Existing SGPU/CPIF/Wi-Fi donors and project interface work. | Firmware/board ownership and real frontend/ABI/device evidence. Generic Adreno performance is not an Exynos backend. | Keep source work scoped to a concrete blocked subsystem after early boot. |
| Entry/recovery not verified → any physical boot experiment | Existing device inventory and E1S entry/probe source. | Exact current live DTB/EL/reservations plus an explicitly authorized, reviewable recovery/boot experiment. | Host code, source and image validation remain authorized; no new ADB/root/flash/reboot/MMIO action is authorized here. |

The measured end state is still incomplete: no genuine linked guest image or
XNU console has been established locally, and no native XNU system has run on
this S24. The route decision and source repairs must not be reported as that
result.

## Actual follow-through and preserved observations

The first staging attempt stopped at the genuine `san` Make recipe because the
already-staged `.KASANFLAGS` sentinel was treated as a recipe target without
`REPLACECONTENTS`. The second plan added only the existing-sentinel `-o`
convention used for the other flag files. Eight real Make stages then passed;
the unchanged real Clang invocation reached the linker and failed on the single
symbol above. This is environment diagnosis, not a completed guest or E1S port.
The second attempt took25.678seconds, with306159616bytes sampled linker-tree
RSS. Both raw results, commands, logs and zero-survivor cleanup are retained;
the exclusive root lease was released. No archive/XNUP/QEMU run followed.

Primary implementation STR-002 changes actual donor E1S `loader.c`/`fdt.c`:
bounded DTB/range parsing, complete-or-reject reservation handling, checked
endpoints and refusal of the unqualified payload-RAM fallback. This does not
establish that a supplied DTB describes every firmware carve-out. A nonempty
reservation list is a conservative acceptance policy, not physical RAM proof.
The first admitted host compile failed because the extracted regression fixture
omitted two original loader constants. Its failure is preserved as STRMEM-001;
the original owner is correcting the fixture before a fresh measured run.
No tests or target objects are credited from that failure.

The real immediate queue is STR-002 correctness/actual-C verification, followed
by STR-003's small hook in the existing E1S builder so the reviewed patch is
actually applied. INT-002 independently reviews the changed C. The original
STR-001 owner performs a narrow donor lookup for the measured linker defect.
Other native-driver work remains under its existing owners and dependencies;
there is no eligible unclaimed host task merely to fill agent slots.

Detailed local evidence is retained under
`artifacts/team-coordination/20261106-team/strategy-reassessment-20261106/`.
The source audit commits are HakiOS (this directory), Scion `e06432f` +
`f6ceb25`, platform `1c44599` and common/kernel `4dd3598`.

Exact upstream reference points:
[HakiOS Makefile](https://github.com/oosexgang/hakios-xnu-kernel/blob/2631f5d7d4f9d7322aca60991b34ba465dec343b/Makefile),
[SDK setup](https://github.com/oosexgang/hakios-xnu-kernel/blob/2631f5d7d4f9d7322aca60991b34ba465dec343b/xnu-deps/setup.sh),
[QEMU runner](https://github.com/oosexgang/hakios-xnu-kernel/blob/2631f5d7d4f9d7322aca60991b34ba465dec343b/qemu/run.sh),
[Scion current tree](https://github.com/Scion-Project/scion-kernel/tree/8bee16f38f6e34751d2867a8945577edc7cd30c7),
[E1S current revision](https://github.com/RNDMBG/iOS-On-S24/commit/57d0a97e35bddac5ad732f08492cdf03f0946cc1).
