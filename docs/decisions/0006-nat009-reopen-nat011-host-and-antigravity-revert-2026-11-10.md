# 0006 — Reopen NAT-009, NAT-011 host work, revert Antigravity's uncommitted edits, 2026-11-10

Status: in force. Recorded by `claude-takeover-20261110-6c8f` at the owner's request. Changes nothing
in 0002, 0003 or 0005.

## Source

Owner's message in the session of 2026-11-10 (original in Russian). The owner pasted Claude's NAT-014
summary, which ended with three questions, and replied "сделай" ("do it"). The questions were:

> "1. Переоткрывать ли NAT-009. Antigravity отметил её выполненной, но по его же записи результат
> неокончательный. Файл, на который ссылается реестр, не закоммичен, а прошитый образ собран из
> незакоммиченного кода.
> 2. NAT-011. Для неё нужна новая экспериментальная запись в recovery, а это сейчас не разрешено.
> 3. Незакоммиченные правки Antigravity в docs/procedures/nat-009 и references/odin4-nat008 я оставил
> как есть. Решите, откатывать их или нет."

> "сделай"

## Granted

1. Reopen NAT-009 (recorded done by `agy-nat006-20261110-aca2` with an uncommitted evidence file)
   and continue it under a new owner.
2. Do NAT-011's host work: source analysis, loader changes, host tests and a host build of a
   candidate image.
3. Revert Antigravity's uncommitted edits in `docs/procedures/nat-009` and
   `references/odin4-nat008`. Following 0003 condition 2, the edits are preserved first: committed
   as found for the project tree, and saved as a patch with hashes for the upstream clone.

## Not granted

"сделай" answers these three questions only. It does not authorize the experimental RECOVERY write
that question 2 named as not permitted. Writing any partition, rebooting the phone, entering
Download Mode or executing a loader or XNU on the phone still needs a separate owner decision
naming the image hash (AGENTS.md; NAT-002 §6; NAT-014 gate). The 0002 boundary is unchanged.
