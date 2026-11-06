# VM022 cancellation and transformed-size correction

Original owner `codex-guest-exec-20261106-cu`, task VM022. Separate correction
worktree `worktrees/vm-022-tail-cancellation-20261106`, branch of the same name
under `team/`, based exactly on `0d68b46`. The reviewed previous worktree and
all its helper/control/plan bytes remain unchanged.

Independent REV039 found two blockers in the previous67ef helper: default
SIGTERM exits the controller before AF193's finally cleanup, and the raw-only
16MiB limit permits an unbounded transformed-file read. The reviewer used real
Python children and a sparse oversized file/read observer; no target tool or
production execution occurred. Reviewer commit74b5aa92cef44b7f279fb7f2e8841263d9c81c7c
preserves initial-evidence SHA256
bb2bda5e9bdcff8046728d7d4efef1e161628adac1789fc856e7cbc0cc237c55
and report SHA256 b7414b0085b3566da14133b01e634eda1dfde4de2c17d734b7cc90f547b6b96d.
The previous freeze has failed independent review and grants no execution.

The correction preserves AF193. Caller-owned `owned_cancellation()` installs
SIGTERM/SIGINT handlers for the complete tail invocation. During the common
runner call it records signals instead of raising asynchronously. The wrapper
around the actual budget.sample callback raises the dedicated Exception at the
already caught live-session work callback (or child-free admission), and never
at final sample(None) after a session. AF193 then finishes owned cleanup; the
wrapper propagates cancellation after the call and preserves its actual command
record on the exception. Thus a first signal inside the shared finally cannot
interrupt termination. Outside that deferred command region, cancellation can
unwind the source-only work directly.
The caller then records failure and releases any registered reservation before
the original signal handlers are restored. Repeated cancellation does not
interrupt that finite cleanup. Output creation/copy are inside the evidence
try/finally and reservation cleanup also checks its actual registered state.
The transform verifier now opens both files with O_NOFOLLOW/O_NONBLOCK, requires
equal regular sizes <=16MiB before reading either, reads at most expected+1
bytes from each actual FD, and rejects growth/truncation or changed FD/path
device/inode/size/mtime/ctime. Post-stat growth and path replacement therefore
cannot cause an unbounded read. Section and byte semantics remain unchanged.

## Source-only experiment AVFLINKTAILFIX-001

Hypothesis: actual owned SIGTERM/SIGINT unwind the accepted AF193 caller
boundary and leave no live owned child, with restored handlers; a sparse257MiB
transformed file refuses before reading. Register this procedure before tests.
Run `check-cancellation.py --main MAIN --out FRESH_OWNED_OUTPUT`. It launches
only bounded local Python controllers/children, using accepted AF193 and its
write confinement/finite cleanup. Each controller catches the actual dedicated
signal exception; the watchdog may clean only its recorded owned session if a
failure occurs and must report that as a failure. No compiler, section tool,
archive, linker, packager or guest runs. Budget120s/controller256MiB, stable
4GiB memory admission. Also rerun the previous tail source controls and derive
a new separately bound source-only plan after updating the original task's
worktree metadata. Preserve all earlier failed review evidence and attempts.
The corrected freeze still requires independent review and a new production
experiment/root allocation. No review/source-only experiment grants execution.

Final source-only correction: helper SHA256
`99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060`;
tail-fix-plan-2 execution-plan SHA256
`6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569`.
The previous24 recipe/parser controls pass. Cancellation-controls-3 passes seven
additional controls, including actual first work/cleanup cancellations and
repeated signals, a sparse257MiB file, symlink, real post-fstat growth and path
swap. The read operations were real bounded FD reads; no read mock was used.
The callback probe is explicitly a test double for the shared API surface,
never a ProjectBudget or fabricated root allocation. Actual child memory and
cleanup observations are retained; no production resource admission is claimed.
Cancellation-controls-1 remains preserved as a failed harness attempt: its
repeat-signal window extended beyond the controller's completed handler scope.
The fixture window was corrected without changing executor bytes. Independent
REV039 acceptance is still required; no target production ran.

Cancellation is also deferred across the actual reserve transaction and local
reserved=True assignment, covering AF193's post-persist/pre-registered window;
pending cancellation is checked immediately afterward before any child. The
source-only control invokes actual AF193 reserve with an explicitly local
transaction probe and real os.replace/SIGTERM. No canonical allocation changes.
