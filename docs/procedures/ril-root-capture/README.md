# CELL-011 — read-only root copy of the BYH3 vendor RIL libraries (2026-11-10)

Evidence category: **android-userland** (read-only device data). Owner: `claude-takeover-20261110-6c8f`. Authority: decision 0002 item 3, which allows root (su) for diagnostics and reading needed system data. Having root access is not evidence that an action is safe. This task only reads two files.

CELL-010 (2026-11-05) measured that these two files exist and that the shell user cannot read them; root was not authorized then. This task performs only that read, now with su:

| File | Size (bytes) | SHA-256 (device = host) | ELF |
|---|---:|---|---|
| `/vendor/lib64/libsec-ril.so` | 5 459 848 | `fa4c0b63dfb37f91af77710bc8ba4cea064a00adc3707ca2d2ab0e51df4c04ae` | ELF64, AArch64, DYN |
| `/vendor/lib64/libsecril-client.so` | 134 368 | `458cb6bec12d340d6576a13bf5e5f499fd86061b08087c0cef91642309d8adfb` | ELF64, AArch64, DYN |

The sizes equal CELL-010's measurement. The identity was checked first: SM-S921B, e1s, S921BXXS9BYH3, a user build.

Commands, with the transport selected by its id and no serial recorded:
1. `adb shell getprop` for the four identity properties.
2. `adb shell "su -c 'sha256sum …; stat -c …'"`.
3. `adb exec-out "su -c 'cat /vendor/lib64/<file>'"` for each file.

All exit codes were 0. No write, chmod, mount, setenforce, setprop, service, modem or RIL command was issued. Nothing from the files was executed.

The bytes are proprietary Samsung code. They stay only in the ignored `artifacts/ril-root-capture/session-001/` directory (mode 0700/0600) and are not committed or published. This unblocks CELL-009's input requirement ("an explicitly supplied matching SM-S921B/BYH3 vendor RIL with recorded hashes"). The analysis itself is CELL-009's work.
