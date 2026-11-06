# STR026BUILD-001 wave85 handoff

Original owner `codex-e1s-native-objects-20261106-sr26` observed the one root
dispatch. No worker executor, retry, fix or target tool was started.

The actual caller returned exit 1. Raw evidence at this worktree's
`artifacts/e1s-native-compile/execute-001/evidence.json` has SHA-256
`34f2f7373d26f3b70b62d5442756e900f58a81eab4c2294217c54d3b4f83d226`.
The sealed conventional `wave85-evidence.json` has SHA-256
`d066970c9919ae7e7c95a63d6f75a9625174951269fc223251b91843b3ffb33a`.
The detailed product index at
`fixtures/public/e1s-native-objects/bsd-c/wave85-products.json` has SHA-256
`3cc5d75104a3c6ef222a9fb83f15bfd9a241f6f39a266f8661b0054ef13a0710`.

Five original-order objects passed compiler exit 0, ARM64 Mach-O validity,
actual MD/input hashes and resource qualification: `subr_xxx.o`,
`counter_test.o`, `sys_eventlink.o`, `sys_generic.o`, and `sys_pipe.o`.
Their exact object/MD hashes, argv, recipe/source bindings, resources and
515 unique actual dependency paths/hashes are retained. Stream hash reads
confirmed every preserved object, MD file and recorded dependency. The
original `sys_pipe.o` contains a genuine 64-byte
`__DATA_CONST/__kalloc_type` section. No new type-check bypass or stub was
introduced. All five compiler stderr files contain warnings and no compiler
error/fatal-error diagnostic.

The sixth identity, `bsd/sys_record_event.o`, was deferred before child
launch. Its admission error was
`ValueError('Stale executor reservation; root must reconcile survivors')`;
resource qualification is inconclusive. The caller stopped with
`ValueError('Stop after failed/deferred native row')`. There are 163
uncompiled identities: this deferred row plus 162 not attempted. The failed
admission, partial products and all logs remain immutable. They do not
establish completion of the 168-object task.

Root wrapper PID/start was `1112193/62162867`, dispatched at
`2026-11-06T14:01:55.551782+00:00`, ending at
`2026-11-06T14:02:53.806932+00:00`. Caller elapsed time was 45.571464
seconds. The explicit project-budget-v1 slot used one serial compiler,
512 MiB owned-tree cap, 120-second child deadlines and an 1800-second
worker bound, with root's external GNU timeout at 1890 seconds, TERM and
30-second grace. Peak helper aggregate owned RSS was 163020800 bytes;
controller actual `/proc` VmHWM was 81809408 bytes. Child VmHWM was not
separately recorded. Own commands observed a project RSS peak of 617496576
bytes and zero project swap. Actual command/resource samples remain beside
the raw report.

The caller recorded no owned survivors. The STR-026 reservation is
`complete`; eight exact wrapper/controller/compiler/loader PID-start
identities were absent on read-only cleanup observation. The snapshots and
root command receipt are under
`artifacts/e1s-native-compile/wave85-intake-001`. The worker did not release
or reconcile the global allocation. Root owns the stale-reservation review.

No full kernel/link/provider/private ABI, runtime, boot/image or hardware
qualification follows. STR-026 remains incomplete. A later remaining-slice
source plan or execution requires its own authorization and fresh output;
this failed attempt must not be overwritten or resumed.
