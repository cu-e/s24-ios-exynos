# Bounded kernel-wait findings

## R3: repeated cancellation interrupts signal-context restoration

Priority P1. Exact operative source f2023bd02bab4400e6a4ca19033c5b78baeb8b57485258afeda9e46891585796, commit5ce6da69aa605acf553843db2a0dad58dfe28b98, physical `worktrees/vm-044-ep-fix4-20261106`. Producer005 zero-timeout observation remains unchanged and does not demonstrate repeated cancellation restoration.

REVCONTEND-003 was persisted before the control. Actual command: constrained Python `timeout --kill-after=2s 12s python3 -s docs/reviews/vm-044/restoration-control.py --tool /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-044-ep-fix4-20261106/tools/build/avf_kernel_objects.py --expected f2023bd02bab4400e6a4ca19033c5b78baeb8b57485258afeda9e46891585796 --out /home/egor/dev/pet/s24-ios-exynos/worktrees/rev-vm044-eq-20261106/docs/reviews/vm-044/runtime/restoration-original` exited1. Stable memory/PSI preflight and after snapshot passed.

An isolated owned Python3.14 interpreter installs a callable one-shot outer alarm of0.9 seconds and blocks on a real flock held by its owned child. Another owned child sends the first actual SIGINT after0.05 seconds. A controlled wrapper at the actual handler-restoration call sends a second real SIGINT immediately before restoring the captured SIGALRM handler. The second KeyboardInterrupt aborts bounded_flock's finally. No cancellation exception is fabricated.

Observed after0.06331 seconds: original signal mask[], resulting mask[14] (SIGALRM blocked); original handler not restored, remaining handler named expired; original outer timer erased to[0,0]. Both children were terminated/reaped, current-image VmHWM26,857,472 bytes. The fixture repairs only its own signal context after recording the failed state; that repair is not attributed to production code. Exact raw result and driver report remain under runtime/restoration-original*.

The current finally masks only SIGALRM while restoring timers/handlers/mask. SIGINT can therefore interrupt that restoration and leak replacement state into the caller, losing an existing outer deadline. Requested correction must preserve the earlier context across repeated cancellation at this seam and leave cancellation deliverable after restoration. Use a NEW physical source worktree, retain the failed witness, and narrowly recheck the changed restoration behavior. No whole contention benchmark rerun is justified. Sent immediately to EP, root and INT002.
