# STR-010 native DEVELOPMENT BSD syscall generation

Owner `codex-e1s-development-syscalls-20261106-sr10`, fresh worktree from accepted
MAIN cc55be2237977a27b4549f41de12b4914951566c. STR009 and STR004 were DONE before
atomic claim-next returned STR010. This packet prepares generation; it has not
run unifdef, makesyscalls, a compiler or a guest.

The accepted full-eight-component descriptor SHA256
`6b0ac2c8e82b2837a94f628ee5c291105559a0607e3febac56fc7e7b6527cf9a`
binds the actual DEVELOPMENT/ARM64/E1S BSD Makefile
`c5af4f56b5277f0d149869f1b20ac5ee950a4ae242e73426b491084e4e6f12f9`,
115 native CONFIG_DEFINES and MACH_ASSERT=1. All selected sources use STR004's
fresh c886/c54+STM source profile8ef30b4a and manifestf884bf7f. The owned input
fixture and exact generation plan retain these full identities and all command,
tool and staged-copy bindings. Original files and generated config witnesses
remain unchanged.

Nine actual bounded Make variable/dry-run queries succeeded with exit0. They
use byte-identical owned copies of the actual BSD Makefile and query inputs,
the existing standalone Linux tool mapping, original MakeInc.def/rule and fresh
native source root. No source generator/build recipe was executed. Source
MakeInc.def would probe CC during parsing unless BOUND_CHECKS were specified;
root explicitly approved query-only0/1 bindings. The two actual variable queries
differ only in BOUND_CHECKS. UNIFDEF, MAKESYSCALLS, SEED_DEFINES, TARGET and exact
CONFIG_DEFINES are identical, and the relevant source rules have no dependency
on CFLAGS_BOUND_CHECKS. These query values are not compiler feature evidence or
compiler flags to adopt. Future native compilation needs its own genuine result.

The actual native SEED_DEFINES is **empty**. Do not copy the legacy helper's
`-DXNU_NO_TYPE_BUILTINS=0` seed assumption or preprocess under all CONFIG_DEFINES.
The original selection rule uses UNIFDEF plus SEED_DEFINES only and retains
unselected C conditionals for actual compilation. The header query inherits the
exact native BSD CONFIG_DEFINES export; it is not replaced with a guest/RELEASE
selection. The old tools/build/xnu_kernel_syscalls.py remains a source reference:
its hardcoded RELEASE context and four-output implementation are never invoked.

`generation-plan-001.json` requests six serial commands under a separate root
grant: real unifdef stdout selection, then original makesyscalls.sh modes table,
names, systrace, header and proto. They produce one selected master plus
init_sysent.c, syscalls.c, systrace_args.c, sys/syscall.h and sys/sysproto.h.
Each mode is tied to an actual Make dry-run. The script writes files relative
to cwd; TARGET only provides pathname provenance in its generated comments.
C and sys-header directories therefore sit beneath one fresh owned generation
root. Header metadata/cscope recipe bookkeeping is retained in the query logs,
not executed in old prefixes.

Root uses the exact pinned existing run_child/owned_cancellation/qemu_host
interfaces, not BCM module globals or a new executor. All command cwd, outputs,
temporary files and split stdout/stderr remain inside that one Landlock root.
Unifdef raw exits0/1 are explicitly accepted and recorded. Only after terminal
success may root stream-copy its actual stdout byte-identically to the selected
master, as the original helper already does. Other exits or partial output stop
qualification. Then five genuine script invocations run in their owned cwd.
No new shared helper or source implementation is copied into maintained code.

Register E1SDEVELOPMENTSYSCALLS-001 against this existing procedure before actual
execution. Root must independently review the exact frozen plan and grant it.
Requested bounds: one command at a time,256 MiB aggregate owned RSS,30-second
child deadlines,300-second whole deadline and verified session cleanup. Preserve
raw failures, selected stdout/master identity and all five output hashes. New
headers/C files qualify only their genuine source-generation context; no object,
complete kernel, private ABI, native image, syscall runtime or phone claim follows.
