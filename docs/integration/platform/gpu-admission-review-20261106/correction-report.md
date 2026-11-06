# GPU launcher correction recheck

Accept source correction212c28f / final cbc57f7 for the bounded disabled GPU
admission contract. The P2 recorded by PLATGPU002 is resolved; its original
source, counterexample and failure record remain unchanged. This is not a GPU
build, sanitizer run, final helper/profile adoption or whole GPU012 completion.

Launcher ea82de7b blocks SIGALRM, SIGTERM and SIGINT before disarming its timer
and restoring every original handler, then restores the exact caller signal
mask last. Only the guarded finally AST changes. Executor99b6, disabled/null
policydf865 and all seven native/portable/ABI/fixture bodies remain identical.

Independent PLATGPU003 passes36 focused checks. The exact original real-SIGINT
restoration seam now raises the original default KeyboardInterrupt only after
all handlers and the caller mask are fully restored. Repeated all-three signals
at restoration, first TERM at timer disarm, caller-blocked pending INT and
callback-first/repeated cancellation also preserve their original semantics.
Pending caller-blocked INT remains pending until the caller explicitly unblocks
it; pending signals are not drained or swallowed. All handlers and masks are
repaired after each owned Python-only case. No child engine or process matrix
was replayed. Current-image VmHWM17748KiB; no compiler, sanitizer, root allocation
or target process ran.

Retained native and separate host plan metadata is re-pinned to the corrected
launcher and its new physical worktree; original plans remain unchanged. The
71 author controls are retained and their selected hashes are inspected rather
than replayed. The prior31 canonical API/source checks and36 current preparation
checks remain the bounded source basis; no1080-key/6722-header scan is repeated.

Actual execution remains blocked by execution_enabled=false/final_binding=null.
Final accepted input/runtime validator, RSS-only shared sanitizer API, exact
helper/profile/caller/launcher/root allocation and real native/host measurement
are still required. Old AF193 RLIMIT_AS is not silently lifted or treated as
ASan-compatible. Pending VM046 and later helper selection are not adopted here.
No backend, Metal registration, IOConnect, hardware or runtime proof is inferred.
