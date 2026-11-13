# NAT-126: sc9 no-PMIC display-recovery control (host)

Owner claude-opus-nat116-20261113. Reuses the genuinely rebuilt NAT-125
kernel; image sc9 explicitly e1spmic=0, so neither ACPM probe nor recurring
PMIC power-key reads becomes available. The no-response touch guard also
prevents IRQ/thread startup. This is a two-path control, not a causal isolation.

Checks: three focused tests pass (disabled PMIC produces no probe/commands;
real guard/negative guard/synthetic responding touch; actual image cmdline),
448 project tests pass, counted derivation matches, missing-decision gate
stops without write/reboot. Actual ARM64 PMIC-init disassembly saved locally;
boot-arg condition branches before ACPM probe. NAT-125 compile/link evidence
pins source, object hashes and zero undefined symbols. No new native evidence.

Preserves product ADT, DECON kick, no marker overdraw, md0/md1, watchdog and
150-second kernel/475-second loader bounds. Kernel SHA-256:
a31e746c961beae19a58deef24a9e0df72e3764fd66478eb0e369b936eba485a.
RECOVERY SHA-256:
0580150ea177ce4471d4461735af482664f1987a9b6238fca28d6ddc7f70b2cf.

Next is separate NAT-127 under decision 0051. This run uses decision 0044,
not additional PMIC-writing authorization. Ask physical display observation,
but restore stock RECOVERY and verify Android without waiting on that answer.
The pre-registered analyzer is nat-123/analyze124.py; no inference of physical
visibility from memory pixels, no acceleration or FPS claim.
