# 0052 — Owner instruction: standing authorization of the native program (USB speed, touch, display, GPU, FPS) (2026-11-13)

Status: in force. Recorded by `claude-opus-usb130-20261113` from the owner's message of 2026-11-13 (sent at the start of that
session). The original is in Russian; the English text below is a translation of its substance and adds nothing. It extends
decisions 0002, 0019, 0044 and 0049 and does not widen the mandatory boundary.

## Source (owner's words, abridged quotation of the authorizing part)

"Даю постоянное разрешение самостоятельно проводить подготовленные испытания без повторного согласования каждого образа, хеша или
длительности: изменения кода, сборки, тесты, локальный Git, ADB/root-диагностика, собственные тестовые APK, чтение разделов, запись
только RECOVERY с проверкой чтения, необходимые перезагрузки и переходы между режимами, загрузка в ОЗУ, сбор журналов и кадров,
ограниченные нативные эксперименты с USB, дисплеем, тачем, GPU, памятью, прерываниями, clocks/reset и watchdog. Разрешаю временные
операции питания периферии через PMIC/ACPM только на подтверждённых штатных параметрах именно этого S24, включая повторное включение
LDO9/LDO18. Запиши это разрешение как постоянное решение владельца и согласуй инструкции и реестр.

Обязательная граница: сохранить существующие Android, приложения, настройки, аккаунты и пользовательские данные. Запрещены сброс,
форматирование, разблокировка со сбросом, запись любых разделов кроме RECOVERY, изменения GPT, EFS, ключей и шифрования. Не использовать
неподтверждённые напряжения, перебор PMIC-регистров или необратимые изменения периферии.

Перед каждым запуском самостоятельно фиксируй образ, хеши, изменения, предел времени, механизм остановки и процедуру восстановления.
Сначала проверяй сборку на компьютере. После эксперимента восстанавливай штатный RECOVERY с полной проверкой хеша и проверяй Android.
Не повторяй неудачный эксперимент без новой проверяемой причины.

Если нужны физические кнопки или смена кабеля, сообщи конкретное действие. При выявленном риске нарушения обязательных границ останови
действия на устройстве и продолжай независимую работу на компьютере. Ограничения сервиса этим разрешением не отменяются."

## Translation of the substance

The owner gives standing permission to run prepared experiments autonomously, without asking again per image, hash or duration:
code changes, builds, tests, local Git, ADB/root diagnostics, the project's own test APKs, reading partitions, writing RECOVERY only
with readback verification, required reboots and mode transitions, booting into RAM, collecting logs and frames, and bounded native
experiments with USB, display, touch, GPU, memory, interrupts, clocks/reset and watchdog.

The owner permits temporary peripheral power operations through the PMIC/ACPM **only with confirmed stock parameters of this exact
S24**, including switching LDO9/LDO18 on again (repeated runs of the decision-0049 rail enable, no longer limited to one run).

Mandatory boundary: the existing Android, apps, settings, accounts and user data stay intact. Forbidden: reset, formatting,
unlocking with a reset, writing any partition other than RECOVERY, changes to GPT, EFS, keys and encryption. Forbidden: unconfirmed
voltages, PMIC register scanning/brute force, and irreversible peripheral changes.

## Conditions attached to every run

1. Before each run the agent records image, hashes, changes, time limit, stop mechanism and restore procedure (the per-image decision
   file required by the session drivers carries these and cites this record as consent; the agent does not ask the owner).
2. The build is verified on the host first.
3. After the experiment: restore stock RECOVERY with full hash verification and verify Android.
4. A failed experiment is not repeated without a new verifiable reason.
5. If physical buttons or a cable change are needed, the agent tells the owner the exact action.
6. On an identified risk to the mandatory boundary, device actions stop and independent host work continues.
7. Service (safety-classifier) limits are not overridden by this record.

## What "confirmed stock parameters" means here

A PMIC/ACPM write is allowed only when the regulator, its register, the value and the voltage are taken from this phone's own stock
sources (the BYH3 device tree / pinned Samsung kernel source for e1s) and, where available, matched by a readback measured on this S24
(as NAT-124 did for LDO9 = 3.0 V and LDO18 = 1.8 V). Each write is read back; a mismatch refuses further writes. Bucks, the charger,
the fuel gauge, power-off/reset paths and any value that does not come from such a source remain excluded.

## How this record is applied

* The registry `native` permission is still opened per run citing the per-image decision file and closed after the run.
* The not-granted list of AGENTS.md is narrowed accordingly: intentional reboots, RECOVERY writes with readback and the PMIC/ACPM
  operations above are granted; everything else on that list stays not granted.
* Owner directions in later messages win over this record.
