# Расширенный технический профиль без изменения телефона

Область: android-readonly. Нужен уже авторизованный ADB и точное совпадение SM-S921B/e1s. Root не запрашивается. Команды su, reboot, install, flash, setprop и запись разделов не используются.

```sh
python3 tools/device_inventory.py --output devices/local-NEW.json
python3 tools/device_profile.py --output-dir artifacts/device-profile/NEW
```

Каждый запуск требует нового имени. Каталоги профиля получают режим 0700, файлы — 0600. В Git они исключены. Для отдельных повторных измерений:

```sh
python3 tools/device_profile.py --output-dir artifacts/device-profile/NEW-extra \
  --sections battery-service thermal-service display sensors input-capabilities
```

Сохраняются выбранные свойства ОС/загрузки, CPU/memory, kernel config, карты разделов и системных mounts, Vulkan/EGL, режимы дисплея, возможности встроенных input, список сенсоров, питание и доступные sysfs-факты. Журналы личного использования батареи, активные окна, приложения и история событий не сохраняются.

Vulkan UUID/LUID удаляются до записи. Device tree проходит allowlist; chosen/bootargs, serial/MAC/seeds не сохраняются. Исходный tar и полные dumpsys не записываются. Пустое дерево считается недоступным, а не успешным результатом.

Наличие Magisk binary не доказывает доступ root для ADB. locked/green — наблюдение свойств текущего Android, не наблюдение Download Mode; значения могут переопределяться. Включённый CONFIG_KVM или узел /dev/kvm не доказывают возможность запуска VM. Снимки метаданных не являются резервными копиями BOOT/recovery и не подтверждают восстановление.

Сбор ограничен отдельными командами с timeout 25–45 секунд. При потере связи сохранить имеющиеся файлы и описать неполноту; не перезагружать телефон для продолжения. Для native-device доказательств этот профиль сам по себе не подходит.
