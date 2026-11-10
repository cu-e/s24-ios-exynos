# STR-039 handoff

Owner `claude-e1s-native-resource-20261110-sr39`, branch
`team/str-039-e1s-native-resource-20261110`. Source-only; no target tool ran.

The caller at `fixtures/public/e1s-native-resource-fix/native_compile.py` is ready
for a compile manifest. It is the accepted `2676a8ed` caller plus the exact delta
in `source-delta.patch`. Run `execute` only under a host-test task, a preregistered
experiment and a heavy lease in the canonical resource queue.

A new `dnf` transaction can change `/etc/ld.so.cache` and make the plan fail with
`Changed/aliased native input`. Repin `runtime.json` and `RUNTIME_SHA` then, and
confirm the five libraries are unchanged.

Next: STR-040 compiles original bsd-a[109:170]. STR-024 remains with its Codex
owner; nothing here releases or completes it.
