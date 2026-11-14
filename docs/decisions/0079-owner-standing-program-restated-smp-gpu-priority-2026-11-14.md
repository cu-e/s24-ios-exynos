# 0079 — Owner instruction restated: the standing native program, SMP/GPU priority, no quality compromise (2026-11-14)

Status: in force. Recorded by `claude-opus-usb130-20261113` from the owner's messages of 2026-11-14 (the repeated /goal message
and the direction given after NAT-193). The originals are in Russian; this English text translates their substance and adds nothing.
It restates decision 0061 and does not widen the mandatory boundary.

## What is the same as 0061

The authorizing paragraph ("ПОСТОЯННОЕ РАЗРЕШЕНИЕ ВЛАДЕЛЬЦА …") and the forbidden list repeat decision 0061 word for word, so 0061's
scope and run conditions apply unchanged. The same holds for the per-run conditions:
- a per-image decision file;
- host checks first;
- the stock RECOVERY restored with a full hash check, then Android verified;
- no repeat of a failed run without a new verifiable reason.

## Recorded on top of 0061 (owner's words, quotation)

"Если телефон завис, ушёл в bootloop или недоступен, выполнять доступную проверенную процедуру восстановления. Если нужен физический
ввод кнопками — сообщить точное действие один раз; пока ожидается помощь, продолжать независимые задачи на компьютере. Не отправлять
повторяющиеся команды восстановления вслепую и не обещать автоматическое восстановление без доказательств."

"При остановке классификатора сохранить фактическое состояние и сообщить, что было остановлено. Не обходить блокировку повторными
формулировками, дроблением той же операции, субагентами или ручным запуском. Продолжать независимые разрешённые исследования, код и
проверки, которые сами не воспроизводят остановленное действие; при необходимости перейти к другой линии CPU, GPU, ввода или
производительности."

"Самостоятельно устранять обычные ошибки, выбирать архитектуру, создавать узкие задачи и принимать необходимые задачи остановленных
исполнителей после проверки отсутствия активной работы. … Приоритет следующего шага выбирать по доказанному препятствию к отзывчивой
iOS и 60 FPS. если задач нет … сам придумай задачу или разбей … главное ускорить ядра и сделать ускорение аппаратное и 60 кадров
добиться"

Direction given the same day, after NAT-193 was prepared:

"Не продолжай NAT-193/194 и другие компромиссы качества ради FPS. … Сохрани рабочую сборку с исходным разрешением как эталон.
Приоритет — настоящие дополнительные CPU и аппаратное ускорение Xclipse, с сохранением качества интерфейса. … Не обходи остановки
классификатора и не подменяй заблокированную цель серией оптимизаций программного рендеринга."

"разбирай что запретил делать классификатор на мелкие куски … тогда это не выполняй а куски остальные выполняй"

## How it is applied

- **Priority.** Real additional CPU cores (SMP) and Xclipse hardware acceleration come first. Lowering the UI resolution or effects for
  FPS is out; NAT-193/194 are withdrawn. The reference build is `docs/reference-build.md` (scV, native resolution).
- **The plan.** `docs/plans/smp-gpu-roadmap-2026-11-14.md` lists each piece as done, allowed now, STOPPED (classifier) or owner.
- **Stopped work is split.** The exact piece the classifier stopped is not repeated, reworded or delegated. A piece that does not
  reproduce the stopped action may go ahead. If a new piece is stopped, it stays stopped and is reported.
- **No new permissions.** The registry `native` permission is still opened per run, citing that run's per-image decision file (which
  must contain the text "decision 0019" and both hashes), and closed after `task done`/`task update`.
