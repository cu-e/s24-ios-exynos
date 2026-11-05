# KRN-029 handoff —2026-11-05

Owner: codex-team-crypto-xts-20261105-bg.
Branch: team/krn-029-20261105; worktree worktrees/krn-029-20261105.
Only owned paths src/platform/crypto/xts, docs/procedures/crypto-xts and
fixtures/public/avf-handoff/runtime.h are changed. Retain in_progress until
coordinator and independent acceptance; no task-done claim is made here.

The source implements genuine typed XTS encrypt/decrypt descriptor factories,
real software Mbed AES expansion/ECB, two separate keys, raw-IV encrypted tweak,
GF progression across split calls, copied const schedules, state/generation/
direction admission, numeric extent/count/overlap bounds and volatile zeroization.
See README.md for lifetime/profile/exact limits and next caller-integration gate.
No provider registration or Apple implementation reuse is included.

Registered XTS-001 before any compile/vector check. Development evidence stays
under artifacts/crypto-xts. Initial download of the Mbed archive failed with an
incomplete HTTP read; a named curl retry succeeded. Early retained compile
attempts found missing mode macros, lld address-space reservation, genuine
limits/assert header dependencies, entry relocation syntax, platform link flag,
fortified memory imports and a generic profile.h filename collision. The final
profile has a unique name, real software code, genuine selected/compiler headers,
a minimal attributed unused-assert include patch, real bounded guest memory
routines and actual executed function pointers. No failure is counted as a pass.

qualification2/evidence.json passed40696 host/40691 ARM checks; expanded
qualification3/evidence.json passed40708 host/40703 ARM checks,1220 records
(1200 primary NIST+20 independent OpenSSL). The five host-only checks execute
a real2^20-block unit and verify cumulative rejection; the ARM fixture does not
claim that maximum-size run. Both sanitizer negatives, four prohibited profile
negatives and four guest controls pass. Actual target layout: key608/16,
tweak48/16, AES288, descriptor80. Compile sampled owned RSS was below103MiB;
guest sampled owned RSS below61MiB. Final commit-bound replay is the acceptance
capsule referenced alongside this handoff, superseding these dirty-tree runs.

`make check` in the isolated worktree exited2 before tests because inherited
ignored devices/local-2026-11-05-session1.json is absent. No private inventory
was copied to work around this. Main common checks after integration are the
coordinator's acceptance gate. Full real XTS checker is independently runnable
from README instructions and records every command, dependency and tool hash.

Do not infer XNU/provider runtime, wrapper error propagation, private ABI,
full crypto, encrypted-volume/FIPS/side-channel/native-device support. The
selected kernel wrapper ignores the xts pointer return. Future integration must
qualify or fix caller error semantics, key/sector policy and provider ownership
under a separate scoped claim. No physical device action occurred.

Final clean replay: XTS-003, implementation7b7607b1f907d2e51dbb55766de9cdee772c0842
(after396517f55102a2ded50245b053684dfffb6c2ec8). Report:
worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2/evidence.json,
SHA256 c5064a512ba295d1cd447af1e73ac6fc4f9c0ffeaf5b78f09ca0f80fc1f6216c.
Qualified capsule: docs/procedures/crypto-xts/qualified-evidence.json.
Passed40708 host/40703 ARM checks; all1220 records,2 detector controls,
4 profile rejects,4 guest controls. Sampled owned peak106192896 bytes;
cumulative child ru_maxrss84952KiB. Every owned session cleaned up. The
memmove followup uses numeric rather than unrelated-object pointer ordering.
Implementation and evidence capsule are ready for coordinator/independent review.
