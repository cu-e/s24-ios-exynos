# LAB-001: file-based planning and coordination

Date: 2026-11-05. Owner: codex-coordination. Scope: host only.

Added BOARD.md, generated planning/tasks/ID.md cards and state/board.json, all derived from state/lab.json. STATUS.md is refreshed with them. Successful transactions publish views under the same fcntl ledger lock; each file is atomic, and the JSON checksum index is published last. The canonical registry remains authoritative if publication fails. The CLI explicitly reports committed state before requesting a repair; board --check detects stale/edited/incomplete machine and Markdown views, and board --write repairs them.

New commands: task claim-next, update, heartbeat, resume and prioritize. Claims honor authorized scope, completed dependencies, priority and active/blocked file reservations. Progress and next step, optional handoff/branch/worktree context and heartbeat are recorded in task/event data. Only the owner may change owned work. Priority updates apply to pending work and require a reason. Directory/file parent overlap is detected; traversal, globs and symlink aliases are rejected. Existing task outcomes, evidence and authorization flags are preserved.

Owner labels are not authenticated identities and heartbeat is not process monitoring. Stale reports never expire/reassign claims. Reservations enforce cooperative CLI claims, not arbitrary filesystem edits. Independent machines/worktree ledgers are not coordinated; use one shared local primary ledger. This implementation does not launch agents or calendar jobs. Parallel workers require separate authorization and worktrees.

Host verification follows docs/procedures/planning-check.md. Tests cover independent/same-task/overlapping concurrent claims, priority, no eligible work, owner restrictions, progress history, blocked path retention/release, resume authorization, stale reports, invalid context, view tampering and interrupted publication/recovery. Public results are recorded in state/evidence/LAB-001.json and fixtures/public/planning/. No phone commands are involved.

Verification result: make check exited 0 with 42 tests (29 existing, 13 planning checks). Reviewed 20 generated task cards and checked 99 local Markdown links. Existing task/experiment records, project permissions/facts and original evidence bytes were unchanged. board --check and git diff --check passed. The live LAB-001 claim demonstrates owner, branch, progress, next-step and handoff metadata without claiming unrelated work.

Next research task remains RES-001 after LAB-001 completion releases its file reservations. Agents should start from AGENTS.md and docs/planning.md, inspect live board output, then atomically claim ready work with a unique session owner. Keep the pending backlog's paths narrow as tasks are refined; broad parent paths intentionally serialize overlapping work.
