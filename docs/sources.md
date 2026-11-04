# Источники и примеры

`python3 tools/lab.py sources` показывает первичные источники. Полный SHA есть только у точного S24 snapshot. У остальных revision=null: перед использованием кода закрепить ревизию и сохранить её в research/sources.json.

| Для чего нужен пример | С чего начинать |
|---|---|
| Точный загрузчик/патчи e1s | s24-port: README, E1S_PROGRESS, xnu/e1s/README, docs/e1s-hackios-port-map |
| Протоколы и адреса S24 | s24-linux, DTS точной прошивки; сравнить с hardware map s24-port |
| Exynos UFS, питание и организация порта | y2sios, scion-starlte; адреса не переносить автоматически |
| Графика Xclipse внутри Android | radv-xclipse |
| Metal/AIR → Vulkan | metal2vulkan |
| Общий XNU и слои userland | hakios, unixnu |
| Ограничения UEFI e1s | silicium, Status.md |
| Отдельный эмулятор старого iOS | un1box; другое направление, не нативная проверка |

Клонировать выбранный источник в references/<source-id>, переключать на полный SHA, проверять git status и license. Не скачивать все репозитории, submodules, toolchain или firmware без потребности задачи. Не исполнять flash/install-скрипты upstream при исследовании.

Собственный патч сопровождается source URL, base SHA, исходными файлами, лицензией/авторством, причиной, проверкой и ограничениями. Чужие большие деревья не коммитить поверх src/.

research/snapshots содержит импорт прежней проверки 2026-11-05: он исключён из Git и остаётся историческим. Состояние владельца в нём не измерялось. Публичные заметки research/notes могут устаревать; оперативные факты находятся в state/lab.json и датированных evidence.
