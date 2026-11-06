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

Next: wait for publication/common84 PASS and root's exact native allocation
and execute grant for STR022BUILD-001. Do not duplicate the executor or rerun
planning. Any actual compilation requires a separate root allocation: one serial
compiler, at most 512 MiB combined owned RSS, within the root six-job/six-GiB
wave. Preserve future failures and fresh actual MD closure. Independent review
and root publication/common acceptance precede closure. No compiler, caller,
private projection, generator, linker, QEMU or device operation ran here.
