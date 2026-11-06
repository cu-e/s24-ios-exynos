# STR-022 native osfmk-a160 actual handoff

Original owner: `codex-e1s-native-objects-20261106-sr22`.
Worktree: `worktrees/str-022-e1s-native-osfmk-a-20261106`.
Branch: `team/str-022-e1s-native-osfmk-a-20261106`.
Base: `415c9a1fcad73cb47affcedbb037520ce973f888`.

All 160 genuine DEVELOPMENT / ARM64 / E1S osfmk-a objects now have physical
Mach-O, exact actual argv, actual MD/input and per-command resource evidence.
The combined descriptor is
`fixtures/public/e1s-native-objects/osfmk-a/objects.json`, SHA256
`bf9fb30ae6f01759e2ca433f9b7d388f4ea005d94a0e0cf7ce5ae8485664060a`.
It preserves the accepted STR016 original order `[0:160]` and three distinct
actual origins, with exact object/MD/source/recipe/argv and raw capsule pins.
It is an object collection, not a relabeling of failed parent experiments.

| Actual origin | Original indices | Qualified objects | Parent trial |
| --- | --- | ---: | --- |
| STR022BUILD-001 / root85 | `[0:5]` | 5 | FAIL: next compiler not started, stale reservation |
| STR022BUILD-002 / root88 | `[5:26]` | 21 | FAIL: next compiler not started, budget lock timeout |
| STR022BUILD-003 / root102 | `[26:160]` | 134 | PASS, outer exit 0 |

Both failed trials and every original object, MD, raw log and source-plan byte
remain unchanged. Root separately accepted the prior 26 object origins. The
new003 source plan was independently accepted by CM (705 source checks,
review SHA256 `1a2895bdf6754e512caaf6b58b2fcc1d35afa22174002e409037d61876b46745`).
All three actual runs used the same physical frozen STR030 caller2676;
source014, genuine generated inputs, BOUND_CHECKS=0, portable profile
`-DXNU_NO_TYPE_BUILTINS=0`, original recipe flags and typed namespaces remain
unchanged. No prefix object was reexecuted.

Root102 dispatched003 once with its exact native allocation/approval and
external 1,890-second watchdog. Worker launched no target tool. Raw capsule
`artifacts/e1s-native-compile/osfmk-a/build-003/evidence.json` SHA256 is
`e472f1140fd4861a47748a7b337b191736c73231a04de59981d8faa362bcef3c`.
The [conventional actual result](build-003-result.json) SHA256 is
`70cc843872899ed3a142475205d94ad052144712f91a896ffde26af9e6ba818d`.
It binds root102 evidence SHA256
`ad8563ef13d89cc86bd701328863b04ff0c351bdc22470c209a21e5d9edb9819`,
outer exit0, exact grant/approval and source plan, 134 object/input passes and
135 loader/compiler command resource passes. No command accounting or release
error occurred. Engine elapsed time was 707.8843881159555 seconds; controller
HWM 81,866,752 bytes, maximum owned tree RSS 197,890,048 bytes, below the
536,870,912-byte cap. Project peak sample 566,509,568 bytes is not a whole-wave
maximum or attribution of unrelated host activity.

The [003 physical audit](build-003-physical-audit.json) SHA256 is
`21b1ab3eace19fef14649d8e37f78cf4b3c6074c765f2273f0c72169981baeeb`.
It read 134 ARM64 Mach-O objects, checked actual argv against the frozen plan,
parsed exact MD targets/source closure and hashed 793 unique actual dependency
files. The descriptor also rebinds the accepted original26 object/MD bytes;
it does not rerun their compilation or namespace validation. Current owned
PID/start identities, retained sessions and descendants yielded zero survivors;
own reservation is complete and root's final receipt reports release. Worker
did not release the global queue.

The immutable002 receipt initially left outer exit pending. The additive
[outer-exit supplement](build-002-outer-exit-supplement.json) now binds root88's
final observed exit1. No second002 experiment record is performed. Both failed
experiments were recorded once. New003 is recorded once with the conventional
actual result; CLI transaction completion is reported separately in the sole
MAIN ledger and owner handoff message.

Next: immediate independent CM review of actual134 and the combined160
descriptor, then root publication and fresh common acceptance. Original owner
keeps STR-022 open until explicitly accepted. No further target tools, retries,
helper/source/flag edits, prefix replay, queue release, task closure, component
filelist/segment transformation, archive, link, QEMU, runtime/private ABI or
physical-device qualification is included.
