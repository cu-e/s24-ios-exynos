# GPU current source and admission review

The current three-recipe preparation preserves the earlier reviewed ingress,
policy and ABI sources. The frozen executable-admission contract is held on one
P2: a first cancellation arriving during launcher handler restoration aborts
restoration. Execution remains disabled; no production command, allocation,
actual GPU/native ABI or whole GPU012 completion is accepted.

The finding applies to launcher SHA b20a76972b5edf9a7834b19e7f07025c504afa9ff318a8126e349083f2bd530c
in source tip372535d. At launcher.py:41, finally disarms the timer and then
restores SIGALRM, SIGTERM and SIGINT without masking them. After an ordinary
callback return, the first SIGINT delivered immediately before restoring the
original SIGALRM handler enters the still-active stop handler at :25 and raises
Cancelled. It escapes the finally block; all three handlers remain replaced.
This contradicts the stated prior-handler restoration contract. Existing author
controls signal during callback execution and do not cover this first-signal
restoration seam.

Independent check.py uses the unchanged captured launcher bytes. A wrapper
intercepts only its actual signal.signal(SIGALRM, previous_handler) restoration
call and sends a real os.kill(self, SIGINT) before that call. The callback simply
returns23. The observed exception is Cancelled('signal-2'); SIGALRM, SIGTERM and
SIGINT all remain subject handlers. The review process then restores them in
its own cleanup. This is a source-process counterexample without a compiler,
backend fixture, root allocation or child process. Original EH was asked to
correct it in a new worktree, blocking all three signals through restoration
and restoring the exact prior mask last so pending caller cancellation retains
its semantics. Root independently agreed this hold.

The remaining narrow preparation checks permit continued source development:
seven original product/portable/fixture bodies match the current1f13443,
admission372535d and original source freeze. The earlier31 canonical public
API/source comparisons are reused; the complete1080-key/6722-header matrix is
not repeated. All three native commands retain the genuine selected cwd and
full argument order, changing only source/-o/-MF operands. The C dispatcher
uses its genuine default language standard. The three separate host commands
remain explicitly prospective and do not compile Apple classes. Neither phase
adopts unaccepted VM044 or consumer046 input identities.

Source authentication, snapshot and session-lifetime behavior is unchanged from
the earlier reviewed source: original current task/securityID, administrator and
entitlement checks; rechecking credentials at externalMethod; private request
and reply storage; serialized provider calls; retained client/provider/task
chain when actual quiescence is unknown. The provider stays abstract and its
readiness defaults false. Lack of an actual asynchronous drain path, accounting
and backend remains a future hardware constraint rather than fabricated proof.

Direct checks of the real disabled policy refuse both phases before budget
reservation, output or children. Actual AF193 has no run_child_rss_only API and
its host-interface test refuses without fallback. Historical source experiments
are now recorded, so calling full execute with their old plan refuses the
planned-experiment authority requirement even earlier; that check is recorded
separately from the direct missing-policy/API controls. Retained author35
controls and diagnostics were inspected, not replayed. Their Python cleanup
results do not establish future allocated execution, arbitrary cancellation
or ASan virtual-address compatibility.

Independent source2 completed36 checks in2.042s after three stable4GiB samples,
current-image VmHWM33636KiB. The review process's256MiB virtual-address cap caused
a preserved initial MemoryError in the bounded JSON reader before the actual
restoration test, while measured RSS was24684KiB. The harness was corrected to
use a1GiB virtual ceiling and explicit256MiB RSS checks; no target source or
production policy changed. Both the failed source1 record and its exact harness
snapshot are retained. No compiler, sanitizer, loader-main, linker, archiver,
root reservation, full namespace scan or guest was run.

Final scoped runtime/input validator, exact accepted helper/profile/caller/
launcher/approval pins, root allocation and the real RSS-only shared interface
are still absent. Future enabled resource/error-release paths need their own
exact review and admitted evidence; source control results confer no product,
portable-policy runtime, IOConnect, Xclipse, native ABI or hardware credit.
