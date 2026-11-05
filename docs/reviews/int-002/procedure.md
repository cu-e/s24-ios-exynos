# REV-024 independent gate review procedure

Owner: codex-review-guest-headers-20261106-cs. Actual atomically acquired task:
REV-024; root confirmed role swap from the initially expected REV-023.
Worktree: worktrees/rev-vm008-20261106; branch team/rev-vm008-20261106.
Only docs/reviews/int-002 is maintained by this reviewer.

Review frozen INT-002 commit 8042e6529e34d470620940e9263ede76e9331b18,
its four committed files and producer capsule SHA256
2807bf0826091372c20b5ff1c8a35d7ee02fb4575f9114c6f3a32fff5f10273c.
Stream all hashes, bind committed bytes independently and inspect actual reports.
Run bounded temporary Git/flock tests under a 256 MiB data limit and a 2 GiB
address-space limit so the real common-check preexec cap can be retained. The
producer suite separately runs under its documented 256 MiB address-space cap.
Independently probe stale candidate rejection, lock contention, dirty registry
preservation, symlink parent rejection and inherited lock lifetime. Probe the
actual common-check supervisor with a tiny fixture-only make executable and
owned descendants; this is no project make check, compiler, or guest. Record
actual exits, commands, source/tool hashes and limitations. Preserve failures.

Do not publish to MAIN or run project common checks. No compiler, QEMU, phone,
ADB, SDK acquisition, shared Git hydration or unrelated process termination.
Do not complete REV-024 before independent integrator acceptance and fresh MAIN
checks. Root resource leases and concrete approval remain required for actual
publication/common checks.
