# 0003 — Task transfer from any stopped agent, 2026-11-10

Status: in force. Recorded by `claude-takeover-20261110-6c8f` at the owner's request. Extends decision 0002 item 2; changes nothing else in 0002.

## Source

Owner's message in the session of 2026-11-10 (original in Russian; the English text is a translation and adds nothing):

> "Разрешаю документированную передачу незавершённых задач от любых завершённых или остановленных исполнителей — Codex, Claude и их субагентов. Повторного согласования передачи не требуется. Сначала проверь отсутствие работающего владельца и сохрани все изменения."

> "Это уточнение касается владения задачами, а не отмены ограничений сервиса или разрешения прошивки."

## Granted

- `task transfer` of an unfinished (active or blocked) task from any finished or stopped executor: Codex, Claude, or a subagent of either. No further approval per transfer.

## Conditions

1. Before a transfer, check that no live process works on the task, and record that check in the transfer reason.
2. Preserve the previous owner's files, branch, worktree and results; commit uncommitted work as-is with its status stated, rather than discarding or rewriting it.
3. The new owner works under its own name; the transfer is recorded in `ownership_history` with this file as the decision.

## Not changed

- This concerns task ownership only. It does not lift service restrictions, and work stopped by a safety classifier is not to be restarted to get around that stop, including through a transfer or a subagent.
- It does not authorize flashing, partition writes, boot-chain changes, reboots or the `native` scope. Everything listed under "Not granted" in 0002 still applies.
