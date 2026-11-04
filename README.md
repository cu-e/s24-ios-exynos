# S24 iOS / Exynos

A research workspace for the Galaxy S24 with Exynos 2400, from measurements inside running Android to a possible XNU port. Preserving the owner's current Android system and data is the primary practical requirement.

Tooling and a task plan are available. On 2026-11-05, ADB measurements identified **SM-S921B / e1s**, Exynos s5e9945, Android 15 and S921BXXS9BYH3. See the [device baseline](research/notes/DEV-001-profile.md). This project has no working iOS port or APK yet. The owner reports an unlocked bootloader, while Android properties show locked/green; Magisk is present. Actual unlock state, root access and recovery remain unverified. The primary upstream targets **SM-S921B / e1s**; compatibility with other S24 variants is not assumed.

## Quick start

Requires Python 3.11+ and Git. No third-party Python packages are needed.

```sh
cd /home/egor/dev/pet/s24-ios-exynos
make doctor
make check
python3 tools/lab.py task next
python3 tools/lab.py task show RES-001
```

[STATUS.md](STATUS.md) is a saved summary. `python3 tools/lab.py status` renders the current registry; `make status` updates the file. [AGENTS.md](AGENTS.md) defines the agent working agreement. English is the working language; see the [language policy](docs/language.md).

## Directory map

| Path | Purpose |
|---|---|
| `state/lab.json` | Canonical tasks, experiments, facts and change history |
| `tools/` | Registry CLI, read-only ADB inventory and extended device profiling |
| `docs/` | Architecture, stages, testing, device access and recovery |
| `docs/procedures/` | Reproducible procedures |
| `research/sources.json` | Sources, purpose, licenses and pinned revisions |
| `research/notes/` | Findings and handoffs with citations and limitations |
| `research/snapshots/` | Historical local research snapshots; excluded from Git |
| `references/` | Local upstream checkouts; excluded from Git |
| `src/android-probe/` | Future Android measurement app |
| `src/graphics/` | User-space graphics adapters and test scenes |
| `src/xnu/`, `patches/` | Project code and small patches against pinned upstream |
| `fixtures/public/` | Sanitized or synthetic test data with provenance |
| `devices/` | Public schema and private local inventory/reports |
| `artifacts/` | Logs, APKs, images and run outputs; excluded from Git |
| `worktrees/` | Separate checkouts for explicitly authorized parallel work |

## Work cycle

```sh
python3 tools/lab.py task claim RES-001 --owner agent-a
# Work within scope; record actual observations and checks.
# Create evidence.json using docs/procedures/evidence.example.json.
python3 tools/lab.py task done RES-001 --owner agent-a --evidence artifacts/res-001/evidence.json
make status
```

For a new experiment, register `experiment plan` before execution and `experiment record` afterward. The registry does not run experiments or control the phone. Its timeout field records a plan; it is not an implemented watchdog.

A passing host check does not establish operation on the S24. The `origin` field distinguishes local observations, upstream claims and synthetic tests. See the [agent workflow](docs/agent-workflow.md).

## Current scope

Code preparation, research and host tests are authorized. Inventory is limited to read-only access through already-authorized ADB. Test app installation and native experiments are not authorized yet. Registry flags do not replace the owner's authorization.

Fully autonomous return from a hung XNU kernel has not been demonstrated. Upstream e1s has no independent USB/network control plane. Avoiding USERDATA formatting does not guarantee Android will boot after a BOOT failure.

Further reading: [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), [testing](docs/testing.md), [recovery](docs/recovery.md), [sources](docs/sources.md).
