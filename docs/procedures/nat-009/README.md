# NAT-009 candidate integration and missing recovery proof, 2026-11-10

Host-only candidate, no MMIO executed on the phone. Depends on accepted
NAT-006 build-002 and NAT-007's GPL-2.0-or-later freestanding module. The
combined image also includes NAT-010 entry/coherency hardening.

`patch.py` adds a call to recovery_guard after BSS/vector/timer initialization
and before loader_main. There is no exception/halt watchdog pet or disarm.
The guard changes PMU 0x128600bc only when it equals 0x12345604, replacing it
with normal/UNKNOWN 0x12345600, followed by dsb sy and readback. Other markers
are preserved. A failed write stops before arming/handoff. This uses Samsung's
kernel definitions, not an invented zero marker; see NAT-007's primary citations
and runtime.json. The C objects have no absolute pointer relocations.

The guard arms cluster0 for nominal 30 seconds using OSCCLK2's source rate,
requires a decrement within 1,000,000 CPU iterations, and rejects the handoff if
none is observed. This tests initial clock liveness, not calibrated expiry or
future clock survival. XNU inherits the armed timer; there is deliberately no
pet from potentially hanging code. Even healthy XNU therefore resets after the
remaining interval unless a future qualified driver takes ownership. This is
a bounded boot experiment candidate, not a production watchdog service.

Reproduction: copy NAT-010/check-001/source to a fresh OUTPUT/source, run
`python3 docs/procedures/nat-009/patch.py OUTPUT/source`, then
`python3 docs/procedures/nat-010/build.py OUTPUT`.

## Acceptance gap and next step

The ARM build, no-ABS relocation check and independent RECOVERY verifier pass.
ASan/UBSan host tests cover five reboot markers and a stuck timer: the recovery
marker alone is replaced, other reasons remain intact, and a timer that never
decrements is disarmed and denies XNU handoff.
Integration is implemented. Overall acceptance remains INCONCLUSIVE:

- No applicable S-Boot source or trace proves whether INFORM3 is consumed,
  cleared, transformed or supplemented by another persistent recovery marker.
- No hardware expiry/return measurement establishes secure PMU write access,
  preserved clock/routing across XNU, or normal Android selection after reset.
- Consequently "any hang causes bounded SoC reset" and absence of a recovery
  loop cannot be inferred from register-file tests or a successful image build.

Required external fact: an applicable S-Boot reset/boot-target contract or a
separately authorized, verifiable NAT-004 hardware recovery experiment proving
one-shot RECOVERY behavior and return after watchdog expiry. Until that exists,
retain the pre-flash gate. Do not close NAT-009 as passed or flash this candidate.
The next owner can reuse all saved builds; no repeated rebuild is needed just
to restate this gap. Android and its partitions were untouched by this session.
