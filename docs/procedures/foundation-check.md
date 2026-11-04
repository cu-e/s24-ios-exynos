# Проверка основы проекта

Контур: host. Телефон не нужен. Никакие инструменты прошивки не вызываются.

```sh
python3 tools/lab.py validate
python3 -m unittest discover -s tests -v
python3 tools/lab.py doctor
```

Ожидается exit 0 у validate и unittest. Doctor перечисляет доступные инструменты; отсутствие Android SDK/QEMU не мешает основе. Внешний runner ограничивает проверку 120 секундами. Остановка — завершить host-процесс; аппаратных изменений нет.

Сохранить реальные stdout/stderr и exit codes в artifacts/foundation/. Evidence kind=host-test, origin=local-host. Pass подтверждает инфраструктуру реестра, не аппаратную загрузку или пригодность драйверов.
