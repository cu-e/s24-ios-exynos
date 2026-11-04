# S24 iOS / Exynos — состояние

> Сгенерировано tools/lab.py из state/lab.json. Не редактировать вручную.

Фаза: **foundation; Android-preserving research**. Обновление реестра: 2026-11-04T21:41:05+00:00.

Разрешённые области: android-readonly, host.

| Задача | Статус | Область | Исполнитель | Зависимости |
|---|---|---|---|---|
| FND-001 — Подготовить и проверить основу проекта | done | host | codex | — |
| RES-001 — Зафиксировать upstream S24 и происхождение доноров | pending | host | — | FND-001 |
| DEV-001 — Получить обезличенную read-only инвентаризацию S24 | pending | android-readonly | — | FND-001 |
| RES-002 — Сверить карту аппаратуры e1s по первичным источникам | pending | host | — | RES-001 |
| BLD-001 — Сделать воспроизводимую host-сборку загрузчика и E1S delta | pending | host | — | RES-001 |
| TST-001 — Проверить boot-пакет, ADT и границы памяти на host | pending | host | — | RES-002, BLD-001 |
| GPU-001 — Спроектировать Android-приложение для измерений GUI/GPU | pending | host | — | RES-002 |
| GPU-002 — Реализовать минимальный Android Vulkan probe | pending | host | — | GPU-001 |
| GPU-003 — Измерить штатный Vulkan на S24 внутри Android | pending | android-app | — | DEV-001, GPU-002 |
| GPU-004 — Проверить минимальный Metal-to-Vulkan путь на host | pending | host | — | RES-001, GPU-001 |
| GPU-005 — Сравнить штатный драйвер и RADV Xclipse в test APK | pending | android-app | — | GPU-003, GPU-004 |
| DRV-001 — Подготовить STM SPI touch driver и host-адаптер | pending | host | — | RES-002 |
| DRV-002 — Проверить read-only UFS/MCQ контракт на host | pending | host | — | RES-002, BLD-001 |
| NAT-001 — Подготовить проверяемый план восстановления именно этого S24 | pending | host | — | DEV-001, RES-002 |
| NAT-002 — Спроектировать управление и возврат из нативного теста | pending | host | — | NAT-001, TST-001 |
| NAT-003 — Первый нативный BOOT-сеанс с журналом и восстановлением | pending | native | — | NAT-002, BLD-001, TST-001 |
| DRV-003 — Аппаратно проверить минимальные драйверы XNU | pending | native | — | NAT-003, DRV-001, DRV-002 |

## Эксперименты

- FOUNDATION-001: recorded, host-test, результат: pass.

Подробности: `python3 tools/lab.py task show ID`; доступная следующая задача: `python3 tools/lab.py task next`.
