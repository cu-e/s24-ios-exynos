# KRN-023 handoff

Owner: `codex-team-corecrypto-20261105-at`, 2026-11-05.
Branch/worktree: `team/krn-023-20261105` / `worktrees/krn-023-20261105`.
Own only `tools/research/corecrypto`, `docs/procedures/corecrypto-provider`,
`fixtures/public/corecrypto-provider`, `patches/corecrypto-provider`.

Implementation/source-audit commit:
`e4e11be38ee3d41b233f58b8d4c9234c2af93e28`. The final evidence/summary commit
adds only these owned reports. No shared registry/generated views are included.

CCPROV-003 was planned through the main CLI before execution.
`python3 tools/research/corecrypto/audit.py --run source-abi-session3` exited0:
42 actual checks pass, including every21 unsupported slot mutation, active
relocation mutation, source hash/library flag removal, genuine incompatible
RSA type compilation and conservative incomplete/rights controls. The real
layout compile exited0; the deliberate signature compile exited1. Peak child
RSS160224KiB, sequential small compilers; no heavy build or provider build.
Commands/exits/source/tool/commit hashes and actual files are in
`worktrees/krn-023-20261105/tools/research/corecrypto/local/source-abi-session3/evidence.json`.
The public qualified-audit.json capsule binds that existing file's digest.

Findings: genuine selected table is448 bytes/56 slots. Existing minicrypto
has34 static relocations,21 unsupported static zeros and one deferred SHA256
descriptor assigned before registration. All56 slots and observed direct
source demand are catalogued. Registration stores the pointer without
size/version/coverage validation; startup, table lifetime and PRNG ownership
remain integration gates. Required cc_kext is unsupplied in measured explicit
library directories; no reference to public corecrypto_kext_start appears in
the coherent982-object consumer graph. No full-link pass follows.

Pinned public Apple corecrypto9612a959abb6eac0aac3ee6a7245c46365c9d81b is
restricted evaluation source, not an established integration grant. Its kext
assigns43 selected members and leaves13 untouched. No direct selected text
demand for those13 was found; this is not proof of binary incompatibility or
an Apple rule requiring all slots populated. Provider build was not attempted.
Named restricted research text remains ignored and is not redistributed.

Preserved failures: first large GitHub metadata response was incomplete;
bounded named endpoints succeeded. CCPROV-001's real layout compile succeeded,
then audit failed on dependency paths resolved against wrong cwd. Its failed
source/output capsule is retained and recorded. CCPROV-002 corrected cwd and
passed41 checks; CCPROV-003 additionally binds committed catalog and consumer
provenance and records the startup inventory. Original bytes remain unchanged.

Next: coordinator review/integration and shared checks; retain KRN-023
in_progress until acceptance. KRN-024 measures the current full link with
genuine firehose/pthread archives and retained cc_kext requirement. A matching
provider needs applicable rights, exact target/context/signature profile,
intentional startup/entropy integration and real archive/import/link/runtime
qualification. Full crypto/FIPS/private Apple ABI/full kernel/native device
flags remain false. No phone/ADB/root/MMIO/flash/emulator was used.
