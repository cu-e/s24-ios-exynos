# S24 iOS / Exynos

A research workspace for the Galaxy S24 with Exynos 2400, from measurements inside running Android to a possible XNU port. Preserving the owner's current Android system and data is the primary practical requirement.

The first host research lab is implemented: pinned sources, reproducible freestanding loader builds, independent boot checks, a signed Android Vulkan APK and one real AIR-shaped compute translation test. **There is no working native iOS port on this phone.** See the [implementation handoff](research/notes/implementation-handoff.md) for actual results, artifact paths and remaining gates.

On 2026-11-05, ADB measurements identified **SM-S921B / e1s**, Exynos s5e9945, Android 15 and S921BXXS9BYH3. See the [device baseline](research/notes/DEV-001-profile.md). The owner reports an unlocked bootloader, while Android properties show locked/green; Magisk is present. Actual unlock state, root access and recovery remain unverified. The primary upstream targets **SM-S921B / e1s**; compatibility with other S24 variants is not assumed.

## Quick start

Requires Python 3.11+ and Git. No third-party Python packages are needed.

```sh
cd /home/egor/dev/pet/s24-ios-exynos
make doctor
make check
python3 tools/lab.py task next
python3 tools/lab.py task show KRN-001
```

[STATUS.md](STATUS.md) is a saved summary. `python3 tools/lab.py status` renders the current registry; `make status` updates the file. [AGENTS.md](AGENTS.md) defines the agent working agreement. English is the working language; see the [language policy](docs/language.md).

[BOARD.md](BOARD.md) is the file-based Kanban with owner reports, progress, dependencies and task-card links. `python3 tools/lab.py board` renders current state; `make board` refreshes all planning files. See the [planning workflow](docs/planning.md). Every successful registry mutation automatically refreshes the board, cards, machine view and status under the shared lock.

[Implementation contract](docs/implementation.md) records the approved iOS 16.5 sequence through graphics, radios, telephony and eSIM. [CAPABILITIES.md](CAPABILITIES.md) separates local Android observations, authored implementations and native acceptance. Use `make capabilities-check` to validate its evidence and generated view. [Feasibility review](research/notes/2026-11-05-feasibility.md) records sources, unavailable inputs and research limits.

[Radio/donor follow-up](research/notes/RES-003-radio-donors.md) adds pinned primary research, explicit Reddit coverage, the SIPC5/SIT framing model, and the missing vendor-command and eSIM-frontend gates. [Cellular contract](src/platform/cellular/contracts/README.md) is host preparation; it does not establish a working modem or eSIM.

[Xclipse interface audit](research/notes/RES-004-xclipse-interfaces.md) traces SGPU/RADV, conditional XNU page sizes and missing native GPU/Metal/presentation interfaces. The [GPU contract](src/graphics/contracts/README.md) includes executable host ownership scenarios for memory, fences and Stop/fault handling. These are specification checks, with no native GPU result.

The [experimental SGPU transport](src/platform/gpu/abi/README.md) now has compiled C validation, a separate synthetic peer and AArch64 ELF/arm64 Mach-O layout checks. It performs no GPU operations and does not replace the pending XNU backend build.

[Wi-Fi research](research/notes/RES-005-wifi-donors.md) adds a pinned native ath12k donor, a catalog/current ABI mismatch and Exynos DMA/MSI requirements. The [compiled Wi-Fi input boundary](src/platform/wifi/README.md) checks those interfaces and DMA ranges; real board callbacks, firmware and iOS16.5 integration remain missing.

[Bluetooth research](research/notes/RES-006-bluetooth-donors.md) traces E1S UART1/shared power, unknown controller firmware inputs and native iOS donor semantics. The [owned H4/command models](src/platform/bluetooth/README.md) pass host sanitizer and ARM compile checks. Real UART/power/firmware, iOS16.5 integration, pairing and audio remain separate BT-003/004/002/005 tasks.

[Display/input research](research/notes/RES-007-display-input.md) confirms and [corrects a real E1S STM coordinate defect](patches/display-input/README.md), with regression tests against the actual decoder and integration into source preparation. [Owned display/input contracts](src/platform/display/README.md) check byte extents, mapping and event lifecycle; actual panel/DSC/scanout, SPI touch and iOS16.5 services remain UI-003/004/005 before native UI-002 qualification.

[Android probe runtime qualification](research/notes/TST-002-runtime-qualification.md) now includes genuine65536-pixel SwiftShader readback and16 actual guest cases covering both themes, larger text, export, storage errors and worker/restart lifecycle. The helper owns an isolated ADB server; committed-byte verification preserves honest storage status. This is host Android evidence, with no physical S24 installation or native GPU qualification.

## Run the host lab

Source fetches and heavy builds are explicit. These commands do not select a phone:

```sh
python3 tools/sources.py fetch s24-port apple-xnu metal2vulkan
python3 tools/sources.py verify s24-port apple-xnu metal2vulkan
python3 tools/build/e1s.py --run my-loader-build
python3 tools/build/prepare_xnu.py --run my-xnu-source
python3 tools/verify/boot.py artifacts/e1s-build/my-loader-build/probe/boot.img \
  --tar artifacts/e1s-build/my-loader-build/probe/boot.img.tar
python3 src/android-probe/build.py --run my-apk-build
python3 src/platform/gpu/abi/check.py --run my-transport-check
```

Run names must be new. See [build requirements](docs/procedures/e1s-build.md), the [probe instructions](src/android-probe/README.md) and the [graphics fixture](src/graphics/README.md). The loader build does not compile a complete XNU kernel. Check required external inputs with `python3 tools/build/kernel_preflight.py`. No SDK or Apple userspace is bundled.

## Directory map

| Path | Purpose |
|---|---|
| `state/lab.json` | Canonical tasks, experiments, facts and change history |
| `BOARD.md`, `planning/tasks/`, `state/board.json` | Generated Kanban, task cards and machine-readable coordination view |
| `tools/` | Registry CLI, read-only ADB inventory and extended device profiling |
| `docs/` | Architecture, stages, testing, device access and recovery |
| `docs/procedures/` | Reproducible procedures |
| `research/sources.json` | Sources, purpose, licenses and pinned revisions |
| `research/notes/` | Findings and handoffs with citations and limitations |
| `research/snapshots/` | Historical local research snapshots; excluded from Git |
| `references/` | Local upstream checkouts; excluded from Git |
| `src/android-probe/` | Android Vulkan measurement app, manual build and isolated emulator harness |
| `src/graphics/` | User-space graphics adapters and test scenes |
| `src/platform/cellular/contracts/` | Versioned radio inputs and a bounded host-only CPIF frame parser |
| `src/xnu/`, `patches/` | Project code and small patches against pinned upstream |
| `fixtures/public/` | Sanitized or synthetic test data with provenance |
| `devices/` | Public schema and private local inventory/reports |
| `artifacts/` | Logs, APKs, images and run outputs; excluded from Git |
| `worktrees/` | Separate checkouts for explicitly authorized parallel work |

## Work cycle

```sh
python3 tools/lab.py task claim-next --owner agent-research-session-a --scope host
# Inspect the returned task with task show ID before implementation.
python3 tools/lab.py task update RES-001 --owner agent-research-session-a \
  --note 'Pinned the selected source revision' --next-step 'Check donor licenses'
# Work within scope; record actual observations and checks.
# Create evidence.json using docs/procedures/evidence.example.json.
python3 tools/lab.py task done RES-001 --owner agent-research-session-a --evidence artifacts/res-001/evidence.json
make status
```

The example update/done commands assume the returned task was RES-001. Use the actual returned ID. Claims respect priority, dependencies, authorization and active file reservations. Owner-only progress, heartbeat, block, resume and release commands are documented in docs/planning.md. A stale heartbeat never transfers ownership automatically.

For a new experiment, register `experiment plan` before execution and `experiment record` afterward. The registry does not run experiments or control the phone. Its timeout field records a plan; it is not an implemented watchdog.

A passing host check does not establish operation on the S24. The `origin` field distinguishes local observations, upstream claims and synthetic tests. See the [agent workflow](docs/agent-workflow.md).

## Current scope

Code preparation, research, host tests, merges into main, ADB and root diagnostics, read-only partition copies to the host, the project's own test APKs (`android-app`) and bounded GPU/KVM experiments including a test VM are authorized by the owner's decision record of 2026-11-10 ([0002](docs/decisions/0002-owner-autonomy-grant-2026-11-10.md)). Native experiments, partition writes, boot-chain changes, intentional reboots and anything that erases data remain unauthorized. Registry flags do not replace the owner's authorization.

Fully autonomous return from a hung XNU kernel has not been demonstrated. Upstream e1s has no independent USB/network control plane. Avoiding USERDATA formatting does not guarantee Android will boot after a BOOT failure.

Further reading: [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), [testing](docs/testing.md), [recovery](docs/recovery.md), [sources](docs/sources.md).
