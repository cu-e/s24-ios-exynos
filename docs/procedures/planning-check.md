# Planning workflow verification

Scope: host only, without phone commands or workers launched against the real project.

Run `make check` with an external 120-second timeout. Tests use temporary ledgers and subprocesses to exercise concurrent claims, atomic next-task selection, overlapping paths, owner restrictions, block/resume/release, priority, generated snapshot freshness and publication failure. Keep failing cases; an unchanged canonical ledger is required when a transition is rejected.

On the real project, run `python3 tools/lab.py board --write`, `python3 tools/lab.py board --check`, `python3 tools/lab.py validate` and `git diff --check`. Review the Kanban and cards and check local Markdown links. Real task updates should describe this implementation only; do not claim unrelated research work to demonstrate the UI.

Save actual stdout/stderr, exit codes and public host evidence. Stop by terminating the host test process; no device cleanup is needed. Pass establishes local coordination behavior, not distributed locking, agent liveness or hardware functionality.
