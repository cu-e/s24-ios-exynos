# GPUINGRESS-004: atomic signal-state restoration

Original GPU-012 owner EH. New WT `worktrees/gpu-012-signalfix-20261106` from
frozen `372535dfe53b10b6350e7f9c2702062aac5b61c9`; preserve that physical WT,
`1f13443`, `de6c14a` and their evidence. INT003 found a concrete P2 in b20a7697:
first real SIGINT immediately before handler restoration raises Cancelled from
finally and leaves all three custom handlers installed. Reuse the independent
counterexample at `worktrees/int-platform-20261106/docs/integration/platform/
gpu-admission-review-20261106/runs/source2/evidence.json` unchanged.

Hypothesis: block SIGALRM, SIGTERM and SIGINT through timer and handler
restoration, then restore the exact caller mask last. This permits pending
signals to reach the caller's restored handlers and preserves caller-blocked
pending state without partial cleanup.

Register GPUINGRESS-004 before running the focused script:
`python3 -s fixtures/public/gpu-userclient/restoration_controls.py --out
NEW_GPU_OWNED_DIR --experiment GPUINGRESS-004` under the standard constrained
Python environment. It sends actual signals to its own Python process. Hooks
intercept only calls to the real signal.signal/setitimer restoration APIs;
the real kernel signal mask and real os.kill are used.

Test first SIGINT at handler restoration, repeated ALRM/TERM/INT there, first
TERM before timer reset, first/repeated callback cancellation, exact nonempty
old masks, caller-blocked and preexisting pending INT, and default caller
KeyboardInterrupt semantics. Require all handlers/timer/mask restored, original
handlers invoked only after full restoration, and pending INT held until the
caller explicitly unmasks. The harness repairs its own signal state even on a
failure and preserves reports. Generate two new source-only phase plans carrying
the corrected launcher hash and verify disabled-interface exceptions restore
state with no output/allocation. Record exact commands/exits/timing/RSS/hashes.

Do not repeat the previous35 controls or child-process matrix. No process engine
or subprocess is called by this focused proof. Admission executor, disabled/null
policy, seven native/fixture/ABI source files and physical AF193 remain unchanged.
No pending VM044/046 adoption, compiler, sanitizer, loader tool, root allocation,
archive/link, QEMU or phone action. Actual compilation/runtime/hardware and the
other previously unmeasured admission gates remain unqualified.
