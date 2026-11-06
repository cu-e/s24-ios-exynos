# STR-022 osfmk-a source-slice handoff

Owner: `codex-e1s-native-objects-20261106-sr22`.
Branch: `team/str-022-e1s-native-osfmk-a-20261106`.
Worktree: `worktrees/str-022-e1s-native-osfmk-a-20261106`.
Base: `415c9a1fcad73cb47affcedbb037520ce973f888`.

The sole MAIN ledger atomic claim-next returned STR-022, exit 0. Root82
accepted STR016 and routed this claim. This preparation is limited to the
source slice and provenance in
`fixtures/public/e1s-native-objects/osfmk-a/slice.json`; it does not create
an executable compiler plan or authorize target tools.

The accepted MAIN qualified interface SHA256 is
`c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579`.
It binds graph `2fa82dd9`, partitions `25199660`, portable profile `a65f70a1`
and read-only consumer-005 descriptor `00a9d47c`. The slice preserves exactly
osfmk ordered objects `[0:160]`, selection indices 0 through 159, from
`osfmk/gssd_mach.o` through `osfmk/atm.o`. It matches both the accepted
partition IDs and the original component ordered_OBJS without reordering.
The next excluded object is `osfmk/coalition_notification_user.o`.

Each selected entry retains its graph row literally and carries the accepted
consumer-context actual source binding separately. The graph's 23 historical
pending-generated-source labels remain unchanged; the consumer descriptor
supplies their accepted actual placement identities. The other 137 rows are
native derived sources. This preparation does not remeasure a compiler input
closure or rerun a producer, Make query or feature probe.

The source provenance remains STR014, native DEVELOPMENT / ARM64 / E1S,
BOUND_CHECKS=0 from the shared actual STR013 feature receipt. The explicitly
accepted external portable compiler input is
`SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0`; it is not relabeled as a generated
native default. No source, configuration, recipe flag, generated provider or
historical witness changed. No RELEASE/BCM/guest object or old key was adopted.

Preparation used a bounded stdlib-only `python3.12 -s -` extraction command,
exit 0. It streamed the five descriptor hashes, asserted their accepted pins,
compared the two ordered selections and selection indices, and wrote the
literal rows plus consumer source bindings. The resulting
[source-slice evidence](source-slice-evidence.json) records these checks and
the artifact hash. This establishes source selection/provenance only.

Root subsequently authorized one source-only plan through the frozen physical
STR030 caller SHA256 `2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f`.
The strict eight-field native manifest and all old source-only witnesses are
preserved separately. The one export exited zero with empty stderr and plan
SHA256 `ad5e964ed3fb7ab347f5b50dc35f8fff4393ad5d09b6565bbe7a8e92221be287`.
See [procedure](plan-001-procedure.md) and [receipt](plan-001-result.json).
Planning RSS was not measured and remains unqualified. The declared actual
output and all private projections remain absent.

Root dispatched STR022BUILD-001 once under wave85. The raw trial remains FAIL:
five actual objects passed compiler, MD/input and resource qualification, then
`osfmk/kdp_common.o` was deferred before compiler because project admission
reported `Stale executor reservation; root must reconcile survivors`. The
raw SHA256 is `74ac81f1fdcbfb22b42bd0c32687f8af767a7ba255887229475ec1e9b116dfa1`.
The [failed result](build-001-result.json) and
[read-only physical audit](build-001-physical-audit.json) preserve exact root
argv/exit1, five ARM64 Mach-O objects, 412 unique actual MD dependency hashes,
own reservation complete and zero current owned survivors. Original001 FAIL
was recorded through MAIN lab.py, CLI exit 0. No repair or retry followed.

Root separately authorized one new source-only suffix plan, preserving the
five qualified prefix origins from failed001. New STR022BUILD-002 selects
original IDs `[5:160]` (155), `kdp_common.o` through `atm.o`. Its strict manifest
SHA256 is `c7e10be7c2b480a2637729785a6763a73788d8edb87f552627007c0398c08a4f`;
the single plan export exited zero with empty stderr and plan SHA256
`cb9247af83a76b1055d438f6b454dabb78be221a8b51e37f080885e5ef6d3d61`.
See [new procedure](plan-002-procedure.md) and [receipt](plan-002-result.json).
Fresh build-002 remains absent and planning RSS unqualified. Same physical
caller, source and recipe flags remain unchanged.

Root dispatched002 once in wave88. It remains FAIL: 21 new objects passed
compiler, MD/input and resource checks; `ipc_notify.o` was not started after
project-admission lock acquisition timed out. Raw SHA256 is
`aba8b6d7e2d235950bb190079507605658ac33d455d1ca93dcc27ebcd06ae75a`.
The [002 physical audit](build-002-physical-audit.json) checked 21 Mach-O
objects, exact argv and 494 unique actual dependency files; own reservation
was complete, release error absent and current owned survivors zero.
[002 failed result](build-002-result.json) leaves outer wrapper exit pending
root's final aggregate and preserves actual completed child exits. 002 FAIL
was recorded once through MAIN lab.py, CLI exit 0; later root outer exit belongs in an additive handoff, not a second
experiment record. Root separately accepted the original five prefix objects;
the original001 failed parent remains unchanged.

Root authorized one new source-only003 plan for original osfmk-a `[26:160]`,
134 IDs, excluding actual001 five plus actual002 21. The single export exited
zero with empty stderr; its plan SHA256 is
`de79537b317f562fe2442ad215172f83d546156b4e635e9eaba312b7f7266ccd` and
strict manifest SHA256 is
`db07027c689d64111fa4ee910830fbc85550c61a381594d61cef55ff9e8ca6a5`.
See [003 procedure](plan-003-procedure.md) and [receipt](plan-003-result.json).
Fresh build-003 remains absent, same caller2676/source/flags, planning RSS
unqualified. No actual134 result or complete160 composition is claimed.

Next: wait for root wave88 reconciliation and a new exact strictly serial
native allocation and execute grant for STR022BUILD-003. Do not duplicate the
executor, rerun planning or reexecute the 26 prefix objects. Any actual
compilation requires
a separate root allocation: one serial
compiler, at most 512 MiB combined owned RSS, within the root six-job/six-GiB
wave. Preserve future failures and fresh actual MD closure. Independent review
and root publication/common acceptance precede closure. New003 preparation ran
the source-only caller once; it created no private projection and invoked no
loader, compiler, generator, linker, QEMU or device operation.
