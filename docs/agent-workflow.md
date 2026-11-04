# Работа агента и передача контекста

## Вход

```sh
python3 tools/lab.py status
python3 tools/lab.py task next
python3 tools/lab.py task show RES-001
python3 tools/lab.py history
```

`task next` по умолчанию выбирает host-задачи с закрытыми зависимостями. `--scope android-readonly` покажет read-only задачи. Scope-флаги — учёт согласованных границ, не полномочия на самостоятельное их расширение.

## Одна задача — один исполнитель

```sh
python3 tools/lab.py task claim RES-001 --owner agent-a
python3 tools/lab.py task block RES-001 --owner agent-a --reason 'Нужен доступ к конкретному upstream'
python3 tools/lab.py task release RES-001 --owner agent-a
```

Claim атомарен и защищён файловой блокировкой на локальной файловой системе. Состояние записывается заменой временного файла. Не редактировать реестр параллельно руками. Нет автоматического истечения claim: незавершённую работу сначала проверить, затем явно release. Не использовать общий owner для независимых агентов.

## Новые карточки

Создать spec по task.example.json, затем:

```sh
python3 tools/lab.py task add --file docs/procedures/task.example.json --owner planner
```

Пример имеет ID EXAMPLE-999, его не нужно добавлять без реальной задачи. Задать цель, scope, evidence_kind, dependencies, acceptance, paths и узкие шаги. Зависимости не должны образовывать цикл.

Ветку называть `task/RES-001-description`. При согласованной параллельной работе — отдельный worktree на задачу, общий ledger только в основном checkout. Изменения путей tasks.paths координируются организационно; CLI не запрещает агенту редактировать файлы вне этих путей.

## Завершение

Сначала сохранить настоящие artifacts и evidence, затем task done и make status. `done` требует pass и существующих файлов; ручной review acceptance всё равно необходим. Коммит включает код, тесты, документацию и относящиеся к ним изменения реестра. Не добавляй чужую работу и приватные artifacts.

## Handoff

Длинная задача ведёт `research/notes/ID-handoff.md`: цель; что прочитано и SHA; изменения; команды и реальные exit codes; известные дефекты; границы устройства; следующий конкретный шаг. Перед остановкой обновить его. Не удалять неудачные эксперименты.

Новый агент продолжает по handoff и истории, без полного повторения исследования. STATUS.md — производный снимок; конфликт в нём решается повторной генерацией после согласования state/lab.json.
