# 0061 — Owner instruction: standing authorization of sequential native experiments, now naming CPU and GPU (2026-11-14)

Status: in force. Recorded by `claude-opus-usb130-20261113` from the owner's /goal message of 2026-11-14. The original is in
Russian; the English text below is a translation of its substance and adds nothing. It extends decisions 0002, 0019, 0044, 0049 and
0052 and does not widen the mandatory boundary.

## Source (owner's words, quotation of the authorizing part)

"ПОСТОЯННОЕ РАЗРЕШЕНИЕ ВЛАДЕЛЬЦА: самостоятельно выбирать и выполнять необходимые действия внутри указанных ниже границ, без повторных
вопросов «можно ли». Разрешаю исходники, сборки, тесты, документацию, локальный Git, ADB/root, собственные тестовые приложения, чтение
разделов, подготовку и запись образов только в RECOVERY с проверкой чтения, необходимые перезагрузки и переходы в экспериментальную
систему, Android, recovery и Download Mode, доставку системы в ОЗУ, журналы, кадры, восстановление штатного RECOVERY и проверку
Android. Разрешаю подготовленные ограниченные эксперименты с CPU, GPU, дисплеем, вводом, USB, памятью, IRQ, clocks/reset, watchdog и
временным питанием периферии через PMIC/ACPM на подтверждённых штатных параметрах именно этого устройства. Это постоянное разрешение
на последовательные испытания, а не разовое согласие. Новые хеши, образы и длительность в этих границах отдельно согласовывать не
нужно.

Записать это сообщение как решение владельца и согласовать инструкции и реестр. Существующие Android, приложения, настройки, аккаунты и
данные обязательно сохранить. Запрещены сброс, форматирование, разблокировка со сбросом, запись разделов кроме RECOVERY, изменения
GPT/EFS/ключей/шифрования, неподтверждённые напряжения и необратимые изменения периферии. Защиту файлов или сервиса не обходить.

Перед запуском самостоятельно зафиксировать образ, хеши, обоснование, наблюдаемые критерии, предел времени, механизм остановки и
восстановление. Сначала выполнить подходящие проверки на компьютере. После опыта восстановить штатный RECOVERY, проверить полный хеш и
Android. Не повторять неудачный опыт без новой проверяемой причины."

The same message sets the goal: stable native iOS with responsive UI and input, several CPU cores working, Xclipse 940 hardware
acceleration, measured sustained 60 FPS in menus and apps, then research into 120 FPS; continued USB speed-up keeping USB 2/3
compatibility; panel refresh rate, rendered frame count and input latency measured separately.

## Translation of the substance

* Standing, sequential permission (not a one-off consent). New images, hashes and durations inside these bounds need no new
  question to the owner.
* Granted: sources, builds, tests, docs, local Git, ADB/root, own test apps, reading partitions, preparing and writing images
  **to RECOVERY only** with readback, required reboots and transitions into the experimental system, Android, recovery and Download
  Mode, delivery into RAM, logs, frames, restoring stock RECOVERY and verifying Android.
* Granted: prepared bounded experiments with **CPU**, **GPU**, display, input, USB, memory, IRQ, clocks/reset, watchdog, and temporary
  peripheral power through PMIC/ACPM **only with confirmed stock parameters of this exact device**.
* Forbidden: reset, formatting, unlocking with a reset, writing any partition other than RECOVERY, GPT/EFS/key/encryption changes,
  unconfirmed voltages, irreversible peripheral changes. File or service protections are not to be bypassed.

## What this changes against 0052

* **CPU** is now named. A bounded run that starts secondary cores through the standard PSCI `CPU_ON` call (the method decisions
  0059 and 0060 asked for per run) no longer needs a per-run owner question; it needs only the per-image decision file below.
* **GPU** experiments are named as before. A GPU power-domain or secure-call step is covered only when every register, value and
  call ID comes from this phone's own stock sources (the BYH3 kernel/device tree or a readback on this S24), it is bounded and
  reversible by reset, and the per-image decision file lists it. Anything not traceable to a stock source stays excluded, like the
  PMIC rule of 0052.

## Conditions attached to every run (unchanged from 0052, plus two items)

1. The per-image decision file records image, hashes, **rationale**, **observable criteria**, time limit, stop mechanism and restore.
   It cites this record as consent; the agent does not ask the owner.
2. Host checks first.
3. Afterwards: stock RECOVERY with full hash check, then Android verified.
4. A failed experiment is not repeated without a new verifiable reason.
5. If the phone hangs, boot-loops or is unreachable, use the available verified recovery procedure. If buttons are needed, tell the
   owner the exact action once and continue host work while waiting; do not send blind repeated recovery commands; do not promise
   automatic recovery without evidence.
6. On a safety-classifier stop: record the actual state, report what was stopped, do not work around it (rewording, splitting,
   subagents, manual launch); continue independent allowed work.
7. Service limits are not overridden by this record.

## How this record is applied

* The registry `native` permission is still opened per run, citing the per-image decision file, and closed after the run.
* The session gate's literal requirement (the text "decision 0019" and both hashes) still applies to each per-image file.
* Owner directions in later messages win over this record.
