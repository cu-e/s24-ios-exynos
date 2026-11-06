# VMBOOTCOLLECT-003: selected Linux FDT predicate correction

Original VM-040 owner `codex-guest-collector-20261106-eh` continues in the new
correction worktree, preserving all original physical source/control evidence.
Root authorized minimal corrections for REV-037's second measured P2 finding.

The published authored positive fixture omitted memory.device_type, although
the pinned shim selects a root child with device_type exactly memory. The old
collector also treated compatible properties as byte substrings and checked
only GIC addresses, accepting prefixed compatible strings and zero extents.
The review's source-backed Python reports remain preserved unchanged.

Hypothesis: require the selected root memory device_type and RAM span; match
complete NUL-terminated compatible-list tokens; and require the exact pinned
QEMU distributor/redistributor register spans. Correct only the new host fixture
to include its required memory device_type. This is a source-valid authored
Linux FDT fixture, never a QEMU-produced FDT or guest qualification.

Register this procedure before controls. Freeze the combined minimal correction
first. Focused stdlib Python controls must accept the corrected authored fixture,
reject the exact original frozen fixture, reject missing/wrong device_type,
prefixed and unterminated compatible properties and zero/shortened/overflowing
GIC spans, and accept exact compatible tokens within a valid list. Bind actual
pinned avfboot.c/fdtx.c and QEMU source identities and both old/new fixture hashes.
Do not rerun the original baseline matrix or the full19-case suite.

Also exercise the corrected real Python peer's paused input-FDT path once to
ensure its new fixture satisfies the same gate. Preserve exact argv, exit,
hashes, timing, /proc VmHWM and owned survivor checks with a256MiB address-space
limit and finite deadlines. No compiler, QEMU, guest, phone, common checks or
MAIN publication. Independent REV-037 recheck and integrator/root acceptance
remain required before original-owner closure.
