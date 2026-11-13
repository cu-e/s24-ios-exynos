# 0044 — Owner instruction: standing authorization of prepared single native experiments (2026-11-13)

Status: in force. Recorded by `claude-opus-nat116-20261113` from the owner's message of 2026-11-13 (sent before NAT-116). The
original is in Russian; the English text below is a translation of its substance and adds nothing. It refines decisions 0002 and
0019 and does not widen their boundaries.

## Source (owner's words, abridged quotation of the authorizing part)

"Разрешаю NAT-116 и последующие подготовленные одиночные нативные эксперименты без повторного согласования каждого образа, хеша
или длительности. Разрешены: изменения исходников, сборки, проверки, локальный Git и согласованная передача задач остановленных
исполнителей; ADB/root-диагностика; запись экспериментального образа только в RECOVERY с проверкой чтения; намеренные перезагрузки
и необходимые переходы между режимами; загрузка системы в ОЗУ, диагностика, сбор журналов и кадров; ограниченные эксперименты с GPU,
дисплеем, вводом, памятью, прерываниями и watchdog; восстановление штатного RECOVERY и проверка Android. Обязательная граница:
существующие Android, приложения, настройки, аккаунты и пользовательские данные должны сохраниться. Запрещены сброс, форматирование,
разблокировка со сбросом, изменение других разделов, GPT, EFS, ключей и шифрования. Разрешение на RECOVERY не распространяется на
BOOT/init_boot/vendor_boot/dtbo/vbmeta/super/USERDATA."

## Translation of the substance

The owner authorizes NAT-116 and every later prepared single native experiment without asking again per image, hash or duration.
Allowed: source changes, builds, checks, local Git and documented transfer of stopped executors' tasks; ADB/root diagnostics;
writing an experimental image to RECOVERY only, with readback; intentional reboots and required mode transitions; booting a system
in RAM, diagnostics, collecting logs and frames; bounded experiments with the GPU, display, input, memory, interrupts and watchdog;
restoring stock RECOVERY and verifying Android.

Mandatory boundary: the existing Android, apps, settings, accounts and user data stay intact. Forbidden: reset, formatting,
unlocking with a reset, changing any other partition, GPT, EFS, keys and encryption. The RECOVERY permission does not extend to
BOOT, init_boot, vendor_boot, dtbo, vbmeta, super or USERDATA.

## Conditions the owner attached (each run)

1. Before each run the agent records the image, hashes, changes, time limit, stop conditions and restore path (the per-image
   decision file required by decision 0019 and the session drivers carries these).
2. The build is verified on the host first; the proven bounding mechanism of the experiment (watchdog / loader deadline /
   Download Mode restore) is kept.
3. After each run: analyse, restore stock RECOVERY with hash readback, verify Android.
4. A failed experiment is not repeated without a new verifiable reason.
5. Live executors' tasks are not touched; transfer only after checking there is no active work, keeping their results.
6. If buttons must be pressed physically, the agent tells the owner the exact action.
7. On any sign of risk to Android or data, device actions stop and host work continues.
8. Service (safety-classifier) limits are not overridden by this decision (as in 0019 item 4).

## How this record is applied

* Per-image decision files (`docs/decisions/NNNN-natXXX-<image>-single-run-<date>.md`) are still written before each run, because
  the session drivers' gate requires one, but they cite this record as the owner's consent and the agent does not ask the owner.
* The registry `native` permission is opened per run citing the per-image file and closed after the run, as before.
* Owner directions of later messages win over this record (e.g. withholding consent for a specific image).
