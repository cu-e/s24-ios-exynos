# VMBOOTCOLLECT-004: root exclusion and unambiguous UART consumer

Original VM-040 EH owner continues in `worktrees/vm-040-consumer-20261106`, based
on correction freeze a2ed73a. Both earlier physical source worktrees and all
original/correction/reviewer capsules remain unchanged.

REV-037 independently confirmed a residual source predicate mismatch: root path
`/` also has one slash, but the real shim's memory loop excludes root. It also
confirmed that a valid PL011 compatible token followed by ns16550a selects the
shim's priority8250 path, contrary to the selected PL011 contract. The evidence
is reviewer `runs/correction-fdt-residual-1/report.json`; no C or guest ran.

Hypothesis: explicitly exclude root from the memory-child selector and require
one unambiguous canonical PL011 compatible node with no ns16550a candidate.
Compatible properties inspected for selection must be terminated token lists.
The same selected canonical GIC consumer must be unique. These are narrow
selected-input constraints, not a parser redesign or general board support.

Register before focused pure-Python controls. Accept the unchanged corrected
source-valid authored child-memory fixture and valid PL011 token lists. Reject
root-only memory, priority8250 on the canonical or another node, competing PL011
or GIC consumers and unterminated compatible lists. Check that a root memory
property does not hide an otherwise valid child. Preserve exact bytes/properties,
source/reviewer hashes, actual command/exit/time and /proc VmHWM under256MiB.

Run no child process, QEMU, compiler, phone or common checks. The independent
process recheck was deferred before spawn due host PSI; do not bypass that
gate or repeat it here. A passing authored fixture remains host source-control
evidence, not actual QEMU FDT or kernel/guest qualification. Send the exact new
freeze to REV-037 and integrator/root, retaining all prior failed boundaries.
