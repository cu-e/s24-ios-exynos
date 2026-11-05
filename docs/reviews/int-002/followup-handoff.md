# REV-024 followup: retain RSS policy without the extra AS cap

Exact source delta 6b4464c639efa4f1de359abe870b6be3ee0c0458 passes independent
bounded review. No actionable finding remains in this delta. Its parent is the
first published MAIN 4bea9b59d1d24c2f7f53f4028769b6e420be556e. Original review
081cb6229547feb1309e0b03a986955cf35117a0 and its evidence remain unchanged.
The CLI-only artifact-list wrapper is commit
d7e6a3264f7d5ab500be6ed9c77a2b303adb1922, SHA256
9cc1450346a07a6986dcc1fe937c48f65961c93f16a9013e6bc1a3856a0717d7;
REVGATE-001 is now recorded using that wrapper. Its initial schema rejection is
preserved. No review result was relabeled to erase a failure.

The first real publication ran the actual common check. Its 153 tests had one
lifecycle-test failure when javac initialization returned 1; overall make exited
2. The published HEAD remained intact and the owned session ended with zero
survivors, peak 180,826,112 bytes. Root's separate javac -version differential
isolated the additional AS cap: compressed-class-space reservation fails under
2 GiB AS and succeeds without it. This is separate from the user's owned-RSS
limit. The actual failed capsule SHA256 is
70120b4c75cb0af2cd34e7120b58f928368ee0ed58fcd4135ce46ae520e40822;
the root diagnostic SHA256 is
d80103b5406fbf08a9186ce2babe76679dd8985f151da2e62a22efcdae8f22c5.

The independent followup audit verified all eleven producer capsule bindings
and exact committed bytes for all three changed files. An explicit full-source
normalization proves the production changes consist only of removing the
resource import, AS-limits callback and preexec_fn, and setting the evidence
AS-override field to null. Stable admission, two-job settings, sampled aggregate
RSS at 2 GiB, pressure/deadline stopping, owned-session cleanup, exact plan/source
binding and continuous integration flock are unchanged. No test changed, test
was skipped, or JVM option was introduced.

REVGATE-002 was verified planned before execution. Two narrowly targeted real
supervisor probes passed in 1.232 seconds of test time. A fixture-only make
checks the same flock and runs actual javac -version, which exits 0 with
javac 25.0.1 and inherited AS [-1,-1]. The sampled owned-session peak was
144,736,256 bytes; no owned process survived. The retained failure probe still
rejects exit 7 and cleans a same-session descendant in a separate process group.
The reviewer controller's sampled current-image VmHWM was 23,855,104 bytes.
Both probes use the actual changed common_check and unchanged supervisor.
Their tiny make executable is isolated from the project workload. Admission is
explicitly substituted. No Java source or other source compilation occurred.

The original failed pipeline, root differential, producer capsule and both
review generations remain hash-bound. This bounded result does not establish
fresh project common success or stress-test the 2 GiB RSS/180-second stop paths.
The integrator must still obtain the fresh exact candidate/approval/resource
lease and run the actual MAIN common check. No reviewer MAIN publication,
project make check, compiler source build, QEMU, phone or ADB action occurred.
Keep REV-024 with its original cs owner until that fresh acceptance passes.
