# FND-001: foundation handoff

Date: 2026-11-05. Task status: done. Owner: codex. This is a historical account of the foundation stage, not the current device baseline.

Created a registry of 17 tasks with dependencies, 16 primary sources, coordination/evidence CLI, narrow read-only ADB inventory, architecture/testing/recovery documentation and agent instructions. Previous research was imported into local research/snapshots, excluded from Git.

Verification: make check — exit 0, 20 tests. Tested base commit: 3315832. Evidence: state/evidence/FND-001.json; English translation: state/evidence/FND-001.en.json. Logs: fixtures/public/foundation. Local Markdown links and git diff --check were also checked. After task completion, make validate passed and STATUS.md was updated.

The phone was not queried or modified during this stage. Tests used mocked ADB. At that time, unlock was owner-reported and model, firmware, root and recovery were unknown. Native control, watchdog, XNU boot and an APK had not been implemented. For later measured device facts, read DEV-001-profile.md.

Next independent step at handoff: RES-001. Read AGENTS.md, then `python3 tools/lab.py task show RES-001`; claim under your own owner. Clone the exact s24-port into references/ and pin only required donors. Do not repeat the entire previous review. DEV-001 was a separate task requiring already-authorized ADB.

Do not turn source work into flashing or APK installation; these scopes were not authorized. src/* directories contain design requirements, not a working iOS implementation.
