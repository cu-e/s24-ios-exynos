# Executable GPU phase admission contract

`admission.py` writes phase-specific plans and reconstructs every proposed
command before admission. `launcher.py` hashes the actual executor bytes before
evaluating them, and runs admission in its own process under a 600-second timer.
SIGTERM/SIGINT/SIGALRM raise one cancellation through shared cleanup; subsequent
signals are recorded without interrupting that cleanup. Existing timer authority
is refused. Prior handlers are restored on exit. No subprocess, process broker,
GPU provider or Apple type is implemented in either file.

The native phase has exactly three genuine C++ adapter/policy/C dispatcher
commands. Full inherited flags, argument order and genuine cwd remain fixed;
only source/-o/-MF change. After a future admitted compile, the existing exact
bounded inspector parses actual objects and retains methods, allocator metadata
and unresolved imports without stubs. The explicitly separate host-sanitizer
phase has three commands for portable fixture compilation/link/run; it does not
compile Apple classes or claim native ABI or hardware. Original source hashes
and a closed kernel source-file set refuse added provider/type code.

Both phases currently refuse before budget reservation, actual output creation
or any child. `admission-policy.json` is hash-pinned in the executor and has no
final accepted binding. Supplying an approval file cannot bypass this. The
production caller does not accept an alternate helper path from command line.
Future enabling requires one reviewed source/policy freeze after final VM044/046
acceptance, not a sequence of intermediate physical helper upgrades.

The final binding must pin actual accepted helper, profile/qualification and
complete namespace/input keys, supervisor, acceptance receipts and a separately
reviewed scoped input/runtime validator. Its `validate(MAIN, plan, binding)`
contract must reject changed tools, ELF interpreter/transitive libraries/loader
search precedence, inherited and new source/header namespaces, missing forced
includes, source/output aliases, unexpected output shadows and wrong profile.
Before reservation it requires output absence; subsequent serial calls permit
only declared prior products, dependency files and owned logs, and verify prior
products/depfiles/input identities. This validator is deliberately absent here;
the current source does not fabricate acceptance for a future interface.

Native dispatch delegates to accepted `run_child`; host sanitizers require an
accepted `run_child_rss_only` API with the same signature and all RSS, budget,
stable-admission, Landlock, timeout and cleanup guarantees, except no conflicting
RLIMIT_AS. The real AF193 has no such API and is refused. No equivalence to an
existing RSS-only supervisor is claimed: none has been shown to satisfy the
complete ProjectBudget/caller/namespace contract. Shared API changes need their
own assignment after VM044 release, independent review and root allocation.

The caller uses exact `project_approval(..., executor_path=__file__)`, checks
root-slot source-plan equality/hash and exact 256MiB combined owned RSS, then
reserves once and invokes one command at a time. Shared release is attempted
only after shared child cleanup; retained live identities cause release refusal.
No local queue/broker or arbitrary signalling is substituted. Root allocation
must bind this caller, launcher/plan, original owner, registered actual
experiment, independent `gpu-userclient` shard and canonical fresh output.
Whole-phase cancellation is installed before validation/admission. Compiler
stable-admission/global six/6GiB remain shared-policy requirements.

The source controls exercise cancellation after recorded fixture readiness;
they do not qualify cancellation during Popen initialization, SIGKILL of the
controller, session escape, future helper changes or final budget allocation.
Those remain explicit final-admission review gates. Repeated signal handling
does not replace a separately reviewed external watchdog or prove arbitrary
callbacks finite. The future scoped validator must also verify actual source
and host runtime snapshots immediately before each child; these tests execute
no loader tool main or sanitizer. Actual target compile, portable-policy runtime,
ASan/UBSan, IOConnect, Xclipse backend and hardware remain unmeasured. This work
is independent roadmap preparation, not a first-console prerequisite.
