# REV-010 handoff — 2026-11-05

Owner `codex-team-review-cc-runtime-20261105-bl`.
Branch/worktree `team/rev-cc-kext-20261105` /
`worktrees/rev-cc-kext-20261105`, base integrated main dc09c05.
Owned paths: only `docs/reviews/krn-025`.
Reviewed implementation c512e446fe2b6fe96b7b47c7304b7861525c2023 and
c0c69ee1fe8d0ac84dbc7700dfaf5e03b2e1cce6; final prose
6dbcd7cddf485ebc7f0e51d1fab200213794cf7b.

Result: bounded no P0/P1/P2 finding. README contains source-line and actual-byte
assessment. REV-010 remains in progress until coordinator acceptance. Original
KRN-025 ownership, shared references/prefixes, compiler/resource and artifacts
were not changed. No native/ARM execution, full runtime/compiler rebuild, kernel
link, SDK/global install or device action was performed.

CCREV-001 was planned before verification and retained as fail: five source/byte
groups pass, then my positive-image check incorrectly used external exports for
native hidden helper definitions. Real helper symbols are private/local N_SECT
entries and imports are empty. The original reviewer runner is saved locally at
artifacts/rev-krn-025/failed-inputs/review1-reproduce.py. No candidate defect was
inferred. Its evidence was recorded unchanged.

CCREV-002 was separately planned before the corrected invocation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-025/reproduce.py review2
```

Exit 0; UTC `2026-11-05T16:19:11.109090+00:00`; eight groups / 13 commands.
Twelve exit 0, original-source UBSan negative exits 1 with actual negative-left-
shift diagnostic. Corrected real source passes 132,225 independently authored
bitwise-oracle cases under full O3 ASan+UBSan, every valid count/boundaries/random
values. One small owned job at a time, 30-second deadlines, 256 MiB sampled group
RSS bound and finite cleanup; no live owned descendants on any completion.
Actual process VmHWM 31,360 KiB; peak sampled owned child RSS 80,972 KiB. No
inherited ru_maxrss is promoted to a new footprint.

Independently verified 4706 original artifact hash entries in CCKEXT004/013/014/
015/017; 472 exact Git-blob sources, 149 declaration blobs/symlink payloads and
509 original / 514 corrected dependency witnesses. Actual 287 source-to-native-
command/member bindings preserve 125 outline atomic and six profile selections.
Only ashrti3 source changes; 286 unaffected objects and the corrected native TU
are byte-identical to the original build. All 287 actual ARM64/iOS16.5 members,
318 definitions / 47 explicit lazy-member imports match. Archive remains
67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5.
Retained real helper image has genuine hidden helper definitions/no imports;
seven backend journals match expansions, six invalid links fail without images,
and the real owned timeout reaches finite SIGKILL/no-live-descendant outcome.
Fresh original-driver -### resolves the exact absolute link-only runtime archive
without a literal bypass. No new native link or original stop-control rerun.

Evidence:
`worktrees/rev-cc-kext-20261105/artifacts/rev-krn-025/review2/evidence.json`

SHA256: `463653f0cc89df25d150d49988dbc8dbd4c2cba18b8d364d5823d42d4a3f548b`.

Report SHA256:
`685a9472dc9063e1658d2adb394224c5096fa899a8bbd3cb1a2ff056a13d037a`.

Report retains exact commands, exits, stdout/stderr, source/tool/reviewer hashes,
capsule identities, explicit imports and process observations. Generated data is
local/untracked; committed files contain only reviewer code and prose.

Next: coordinator inspect/accept review commit and evidence, run/assess primary
integration checks and decide completion. Use the exact link-only resource root
with the original driver/outer -lcc_kext; preserve separately qualified compile
headers. Arithmetic source tests do not qualify all 287 runtime behaviors, and
userland-importing lazy members do not prove complete kernel provider closure.
Private Apple ABI, full SDK/crypto/kernel/runtime/native gates remain unknown.
