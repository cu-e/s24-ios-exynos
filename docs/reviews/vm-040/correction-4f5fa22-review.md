# REVCOLLECT-002: first correction still needs FDT closure

Reviewed operative source `4f5fa223a85f510f9515da80c1a1b557a820ca35`, metadata
`a2ed73accaff1cbf61af4050fb1e9b7dd2ce7f48`, in separate
`worktrees/vm-040-lease-20261106`. Tool SHA256
`341d813ca808cfdc9490a692dc4eb1261bf494c1964c19e4f653df130063bdc2`.
Original source/capsules and initial reviewer counterexamples remain unchanged.

Source delta adds immediately-pre-Popen memory/lease/Stop checks and keeps live
monitoring, removes the third sleep, requires memory type and exact compatible
list members, checks complete GIC tuples, and corrects the positive peer fixture.
Those changes address the initial explicit predicates, but the same FDT consumer
finding has two concrete residuals:

1. `node.count('/') == 1` includes `/`. A root `device_type=memory` plus root reg
   passes when no actual memory child has that type. The actual shim iterates
   direct children and would fail. Author independently flagged this boundary;
   the reviewer confirmed it with copied properties.
2. `arm,pl011\0ns16550a\0` at the selected UART node passes exact PL011 member
   matching. The actual shim first searches `ns16550a` and therefore selects
   UART_8250 at the PL011 address, not the required PL011 driver. No C execution
   is claimed: this is an exact consumer-selection source predicate mismatch.

The copied valid memory-type positive passes. Raw pure-source result is
`runs/correction-fdt-residual-1/report.json`; it binds the actual corrected tool
SHA and both accepted malformed cases. Inline Python ran under256MiB AS with
LC_ALL=C and a10s timeout; no child/compiler/QEMU was used.

The process recheck was prospectively planned before execution. An initial
reviewer indentation error prevented parsing/main/any child; raw failure and
correction hashes are preserved in `runs/recheck-preparation-failure.json`.
After correction the controller rejected its first external resource admission,
with3 checks and **zero children**: `runs/correction-4f5fa22-1/report.json`.
The rejecting sample was held in a local variable and not retained by the initial
review reporter. A read immediately afterward showed MemAvailable14695912KiB,
full PSI avg10=2.02 and some=3.51 in the tool transcript; these are a subsequent
observation, not the exact missing rejection sample. They are consistent with
accepted helper full-pressure threshold2. No claim about a producer failure or
process-regression pass follows. Improve reviewer sample persistence prospectively
and resume process cases only after stable actual resource admission.

Author/root were notified of exact residuals. The author prepares a NEW follow-up
worktree while preserving both original and first-correction witnesses. No source
fix is made by the reviewer. A separately planned final recheck will test exact
new bytes and these preserved cases, plus bounded needed positives. This phase
remains FAIL/changes-required until that evidence exists; no genuine kernel/PID1/
PSCI instruction or real guest shutdown is qualified. No broad producer suite,
compiler, QEMU, common check, phone action or unrelated-process signal occurred.
