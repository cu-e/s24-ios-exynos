# VMBOOTCOLLECT-002: immediate pre-spawn admission correction

Original VM-040 owner `codex-guest-collector-20261106-eh` continues in the new
`worktrees/vm-040-lease-20261106` correction worktree. The original physical
`vm-040-eh-20261106` source, four commits and evidence capsules remain untouched.

REV-037 independently measured a P2 gap: the old loop checks lease at virtual
seconds0,1,2, then unnecessarily sleeps to3. A grant expiring at2.5 can permit
an owned process spawn before the first post-spawn guard rejects it. The review
used a real tiny Python child and retained its exact signals and zero survivors;
it launched no QEMU or guest. Preserve that finding and reproducer unchanged.

Hypothesis: remove the unnecessary last admission sleep, then recheck actual
resource admission, lease and Stop immediately before Popen, preserving the
existing post-spawn guards and owned cleanup. The corrected code must never
spawn after a late lease expiry/revocation, resource-floor failure or Stop.

Register this procedure before running the focused controls. Freeze the small
correction first. Use only the review's explicit unavailable-image/ROOT/protocol
seams to reach collect with a tiny owned Python argv. Use the genuine lease
validator, collect admission loop, own_process/Popen and cleanup implementations.

Exercise late expiry after sample3, explicit grant revocation, late low-memory
snapshot, Stop before spawn and one valid real tiny Python control. Spy on the
actual Popen boundary to count whether a process was created. Keep virtual lease
time separate from real watchdog time and actual /proc memory readings. Require
only two inter-sample sleeps, no unnecessary trailing sleep, zero Popen calls
for rejected admission, and natural exit0/no signals/zero survivors for the valid
Python control. No kernel, image admission or guest result follows from these
controls. Preserve exact source/reviewer input, argv, exits, hashes, time and
current-process /proc VmHWM under256MiB address-space/finite process deadlines.

Do not repeat the full19-case suite or the original failing baseline matrix.
No compiler, linker, QEMU, phone, production packaging, common checks or MAIN
publication runs. Send the exact correction commit/capsule to REV-037 for an
independent focused recheck, then kernel integrator/root. The original EH task
stays open until accepted publication/common checks.
