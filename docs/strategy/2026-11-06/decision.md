# S24 strategy decision — 2026-11-06

**Primary route: C, the existing E1S port with minimal coherent repairs.**
The target is SM-S921B/e1s, Exynos2400. Generic QEMU reproduction is a supporting
bench, not a prerequisite for all hardware source work. Retain the current
1080-object guest. A bounded direct-link diagnostic exposed one undefined
symbol; a five-guard source repair and two-object incremental rebuild now produce
a genuine linked Mach-O image. Do not finish the broad product controller merely
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
| A: current guest | Initial real link exposed only `_iBoot_Stage_2_version`. Five guards now use the genuine internal `XNU_TARGET_OS_OSX` selector. Only two actual TUs were rebuilt; their headers/flags match the originals. A fresh measured link exits0 and produces a genuine ARM64 Mach-O. | Reuse the image for the smallest existing loader/entry/console qualification. No dummy provider, whole-corpus rebuild or general controller was needed. A linked generic image remains separate from E1S and runtime qualification. |
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
| Guest image not yet booted → generic console bench | Existing donor loader/RAM-root/PID1 and newly linked image. | Qualify the actual Mach-O entry/segments and the existing loader's physical layout, payload/RAM-root and console settings; capture the first real bounded serial run only after those inputs are established. Preserve linker warnings for inspection. | E1S source work proceeds. |
| Coherent E1S kernel inputs → full board kernel build | Existing E1S patches and embedded donor dependency recipes. | KRN-001 retains its original blocked owner: explicit matching SDK/dependency paths are unconfigured. The public-source native alternative also retains KRN-026's37 required provider/ABI gaps; guest-profile exclusions do not resolve them for E1S. Supply/qualify coherent genuine inputs or demonstrate a supported board configuration; do not suppress exports or relabel the guest. | Loader, DTB, console policy and board source work proceed; no takeover of these blocked claims. |
| Invalid/incomplete memory exclusions → trustworthy E1S handoff | Existing unchanged E1S loader/FDT parser. | STR-002 actual-C regression and minimal patch: reject incomplete reservations/overflow and unqualified fallback; later complete live DTB/carve-outs. | Started now, no QEMU or phone required. |
| UART/WDT/conduit assumptions → useful first console/halt | Upstream0017–0019 and pinned Samsung DTS/drivers. | Qualify powered accessibility and boot policy; source review of opt-in MMIO, PSCI SMC/HVC,25.6MHz timer and GIC/ADT contracts; later actual EL/IRQ/tick observation. | Narrow source patches/contracts can proceed now. |
| UFS state/ownership → disk root | Existing E1S polled UFS/Samsung donor; RAM/static-init root already available. | Actual S-Boot queue/PHY/power/DMA state and timeout/extent qualification. Read-only blocks still require MMIO/DMA. | Use RAM root first; review bounded queue/timeout code independently. |
| Scanout/panel and input lifecycle → usable UI | E1S framebuffer/STM source, retained nibble repair, exact retail Samsung panel donor. | Live reserved buffer/stride/format/DSC and rails/reset/IRQ/event-loss inputs. | Source extent/format, bus-error and cancellation work independently; no GPU dependency. |
| No native Xclipse/radio backend → GPU/Wi-Fi/SIM/eSIM | Existing SGPU/CPIF/Wi-Fi donors and project interface work. | Firmware/board ownership and real frontend/ABI/device evidence. Generic Adreno performance is not an Exynos backend. | Keep source work scoped to a concrete blocked subsystem after early boot. |
| Entry/recovery not verified → any physical boot experiment | Existing device inventory and E1S entry/probe source. | Exact current live DTB/EL/reservations plus an explicitly authorized, reviewable recovery/boot experiment. | Host code, source and image validation remain authorized; no new ADB/root/flash/reboot/MMIO action is authorized here. |

The measured end state is still incomplete: a genuine guest image is linked,
but no XNU console has been established locally and no native XNU system has
run on this S24. The route decision and source repairs must not be reported as
that result.

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

The demonstrated target-selector defect then justified a small common-source
repair: five Stage2 guards use the internal XNU selector already established by
the genuine Makefile. Both original compile recipes were retained except for
source, output and dependency-file operands. Two actual ARM64 objects compiled;
all other headers/dependencies stayed unchanged and the other1078 products were
reused. These two products are explicitly source derivatives, not relabeled as
members of the original canonical manifest. With those exact two substitutions,
the next bounded link completed with exit0 in9.940seconds. Image SHA256:
`87496c21f41cdd56c748cb1cfad37dba8712b48a01a204dcbb298c0feac5e8fc`.
Raw diagnostic SHA256:
`bed13fd168e43d29ebd4f7792931d9ced4435448195bbe4a78572a3c0e9855ab`.
No QEMU ran. The missing framework search directory and BSS alignment reduction
warnings are retained; loader/segment qualification remains next.

Primary implementation STR-002 changes actual donor E1S `loader.c`/`fdt.c`:
bounded DTB/range parsing, complete-or-reject reservation handling, checked
endpoints and refusal of the unqualified payload-RAM fallback. This does not
establish that a supplied DTB describes every firmware carve-out. A nonempty
reservation list is a conservative acceptance policy, not physical RAM proof.
The first admitted host compile failed because the extracted regression fixture
omitted two original loader constants. Its failure is preserved as STRMEM-001.
After copying the exact donor definitions into the extraction, the fresh
STRMEM-002 run passed all six genuine commands: six baseline reproductions,
35 patched controls under ASan/UBSan and two AArch64 freestanding compilations.
Both output objects have ELF machine183. The measured batch took3.351seconds;
all owned sessions were empty afterward. This is a host-verified E1S donor
loader correction. Raw result SHA256 is
`bc377c3975df286869892be6094c695852e10a0b3d2ca9552cc9d7cf268c4c90`.

STR-003 adds14 lines to the existing E1S builder: capture the exact accepted
patch, check/apply it to the verified donor copy, and record provenance. The
actual existing Zig0.16.0 builder passed all19 commands, producing both linked
freestanding probe/loader ELF files, Images and boot packages. All eight product
hashes and six patched donor bodies were checked. The loader boot-v4 package
and its tar pass the existing structural verifier. This is still a loader with
no XNU payload, not a full E1S kernel or a boot on this phone. Actual supervised
build SHA256: `85747434c0a1aa4f5a29dc4f1e158ca8bc9176a53fe57bff47d23f280ec00267`.

STR-002 is accepted and closed by its original owner. STR-003's tested hook and
its independent review are being accepted against the new HEAD. The original
STR-001 audit and narrow donor lookup are complete. The common track's next
result is image/loader/console qualification; the E1S track's next host result
is a coherent entry/DTB/console policy, with full kernel inputs still separately
blocked as recorded above.
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
