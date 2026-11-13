# 0049 — Owner decision: enabling only the touch rails LDO9 and LDO18 (2026-11-13)

Status: in force. Recorded by `claude-opus-nat116-20261113` from the owner's answer of 2026-11-13 (after NAT-122).

## Question put to the owner (Russian original, verbatim)

"Ввод: тач-контроллер не отвечает, вероятнее всего потому, что его линии питания (PMIC LDO9 3.0 В и LDO18 1.8 В) выключены после
загрузчика. Включение — это запись в два регистра LDO PMIC через ACPM, те же линии и напряжения, что использует Android. AGENTS.md
относит операции с питанием к неразрешённым, а решение 0044 разрешает ввод только в общих словах. Разрешаете ли вы в одном
подготовленном запуске включить ТОЛЬКО LDO9 и LDO18 на напряжениях Android, с чтением назад, только RECOVERY и полным
восстановлением штатного?"

## Answer (owner's choice, verbatim)

"Yes, only LDO9/LDO18 at Android voltages"

## What this authorizes

Within decisions 0002/0019/0044: images whose kernel switches on **only** the PMIC regulators named `vdd_ldo9` (3.0 V, touch analog) and
`vdd_ldo18` (1.8 V, touch I/O) of the e1s device tree, at those voltages, with each written register read back and the write refused if
the read-back/identity checks fail; RECOVERY-only, with the usual stock restore. One prepared single run per image under a per-image
decision file citing this record.

## What it does not authorize

Any other regulator, buck, voltage, PMIC register, charger, fuel gauge or power-off/reset operation; changing a regulator's voltage
selection unless the read value already differs from the DT voltage and the change is to exactly that voltage (otherwise refuse and log);
anything listed as forbidden in 0044 (other partitions, GPT, EFS, keys, encryption, reset).
