# STRMEM-002: exact extraction correction

Original STR-002 owner is codex-e1s-memory-20261106-sr2. This correction
worktree descends from immutable 6a1c05d. The original physical worktree, plan
a436b8b2, root failure 36686ca9 and compiler log remain unchanged. STRMEM-001
failed its first original-compile command before any binary: the extracted
actual choose_window body referenced earlier LOG_BASE/LOG_RESERVE declarations.

The checker now prepends those two exact donor declarations to selection.inc;
it asserts that both declarations are present and unique. Production patch,
actual-C harness and original/patched source pins remain unchanged. Host commands
use the same NDK27 clang18 with an explicit resource directory containing its
actual GNU host ASan/UBSan archives. The final plan pins all four archive files.
No compiler, runtime, installation or shared process policy was changed.

Selected plan: artifacts/e1s-loader-memory/prepare-fix1-ndk/plan.json, SHA256
cb3b5d9fe1ab8d4a4910689e37d80c30bb2efcd8b15881334663fa42ead45cbf.
Its commands field contains six ordered {id, argv, cwd} records; input_sha256
binds 24 files. Checker SHA256 is
57e1aae022bf67ab2c56f95c2b19afe693ede3d32a7785c781e6340a1440ed49.
Earlier prepare-fix1 and prepare-fix1-gcc plans are retained as unexecuted,
unselected proposals, not failed measurements. GCC's absent linker-script
targets were observed by file inspection; no GCC invocation occurred.

STRMEM-002 is registered as planned before any correction compiler run. Await
root's exact resource admission: one serial compiler, 256 MiB owned RSS,
120-second child / 600-second whole deadline, stable 4 GiB admission, and the
accepted RSS-only supervisor with no small RLIMIT_AS for ASan. Execute the six
commands once: two actual-C host builds/controls, then two freestanding AArch64
object compiles. Preserve actual errors, commands, exits, memory, cleanup and
hashes. Plan preparation itself does not establish a compile or test pass.

No e1s.py, shared process policy, SDK, target execution or phone operation is
included. Full DTB physical backing, firmware carve-outs, loader handoff and
hardware behavior remain unqualified.
