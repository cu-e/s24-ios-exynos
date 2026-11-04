# Измеренный профиль S24 — 2026-11-05

Origin: local-device, kind: android-userland. Чтение через уже авторизованный USB ADB; shell uid 2000, SELinux Enforcing. Дата в имени — Asia/Yekaterinburg; фактические UTC timestamps сохранены в manifests (2026-11-04T21:44–21:53Z). Установок, изменений настроек, su, перезагрузки и чтения сырых разделов не выполнялось.

| Компонент | Наблюдение |
|---|---|
| Устройство | Samsung SM-S921B, e1s; SoC s5e9945, board erd9945 |
| ОС | Android 15, API 35, One UI property 70000 |
| Прошивка | S921BXXS9BYH3, security patch 2025-08-01 |
| Ядро | 6.1.93-android14-11, страница 4096 байт |
| CPU | 10 online cores, кластеры 4+3+2+1; максимумы policy 1.959/2.592/2.900/3.207 ГГц |
| RAM | MemTotal 7 401 772 KiB ≈ 7.06 GiB, доступная ядру память; физический объём отдельно не измерен |
| Swap / CMA | 3 145 724 / 372 736 KiB |
| GPU | Samsung Xclipse 940, Vulkan 1.3.279, Samsung Proprietary driver 24.3.9, 153 device extensions |
| GLES | ANGLE поверх Vulkan, OpenGL ES 3.2; строка версии GLES-драйвера отличается от Vulkan |
| Экран | 1080×2340, density 480 с override 450; объявлены 120/80/60/48/30/24/10 Гц, активны 60 Гц в снимке |
| Хранилище | sda 255 890 292 736 байт; карта by-name и размеры сохранены |
| Разделы | boot 64 MiB, init_boot 16 MiB, vendor_boot 64 MiB, recovery 96 MiB, dtbo 8 MiB, super 12 380 MiB |
| Touch | sec_touchscreen, ABS X/Y 0–4095, 10 multitouch slots |
| Датчики | LSM6DSVTR accel/gyro, AK09918C magnetometer, STK33F11 light/proximity, LPS22DFTR barometer; список HAL сохранён |
| Батарея | Снимок: 80%, 4216 mV, 28.1°C; это не оценка износа/ёмкости |

## Загрузка, root и виртуализация

Владелец сообщил о разблокировке. Android показывает ro.boot.flash.locked=1, ro.boot.vbmeta.device_state=locked, ro.boot.verifiedbootstate=green, warranty_bit=0, sys.oem_unlock_allowed=0. Найден /system_ext/bin/su → ./magisk, версия Magisk 96221b69-alpha:MAGISK:R. Свойства могут переопределяться: это расхождение, а не доказательство блокировки. Root для ADB не проверялся; Download Mode не открывался.

В прочитанном kernel.config **CONFIG_KEXEC и CONFIG_KEXEC_FILE выключены**. Обычный kexec в этом ядре нельзя считать готовым путём запуска XNU. CONFIG_KVM=y; /dev/kvm существует, но shell-проверки readable/writable не сработали. Открытие устройства, ioctl и VM не тестировались. Из этого нельзя обещать работоспособную виртуализацию.

## Сохранённые файлы и ограничения

Локально, вне Git:

- `devices/local-2026-11-05-session1.json` — узкий исходный inventory.
- `devices/local-2026-11-05-session1.md` — подробная сводка и указатель файлов.
- `artifacts/device-profile/2026-11-05-session1/` — 28 секций, manifest, hardware-summary.json, partition-map.json и validation.json.
- `artifacts/device-profile/2026-11-05-session1-extra/` — 7 дополнительных секций и manifest.

Проверены SHA256 всех 35 исходных файлов; статусы: 25 collected, 9 partial-or-unavailable, 1 unavailable. Для частичных файлов читать diagnostics, а не считать все строки аппаратными фактами. Доступны списки некоторых DT-путей, но свойства дерева закрыты SELinux. /proc/iomem недоступен: адреса MMIO, reserved-memory и IRQ-routing для нативного порта не получены. Недоступны части sysfs и audio metadata. Полный DTB и BOOT/recovery не извлекались. Прочитанный kernel config не подтверждает работу отдельных функций.

Исправлена ошибка сборщика: JSON-обёртка пустого дерева первоначально считалась успешной. Manifest исходного сеанса сохраняет original_status и объясняет переклассификацию в unavailable. Новая версия отклоняет пустое дерево; регрессионный тест добавлен. Исторический файл не переписан.

IMEI, серийник ADB, MAC, Vulkan UUID/LUID, аккаунты и личные файлы не сохранялись. Полные getprop/logcat/dumpsys не сохранялись. Raw tar device tree обрабатывался только в памяти. Это техническая инвентаризация, не резервная копия и не проверка XNU.

## Передача следующему агенту

DEV-001 — инвентаризация; DEV-002 — код сборщика и host-тесты. `make check`: 29 тестов проходят, включая приватность фильтров, недоступное дерево и timeout. Тесты фильтров синтетические; аппаратные значения выше взяты из отдельных настоящих ADB-снимков. Сбор метаданных не был заранее зарегистрирован как эксперимент, не добавлять задним числом фиктивный plan.

Следующий шаг: закрепление upstream RES-001 и сопоставление конфигурации SM-S921B с донорами. Для GUI использовать зафиксированный Vulkan-профиль; установка APK остаётся отдельным этапом. Нативный загрузчик и автоматическое восстановление пока не реализованы. Не повторять весь сбор без новой причины; использовать существующие manifests и новые имена для последующих наблюдений.
