# KRN-038 handoff

Owner `codex-team-crypto-source-integrity-20261105-bz`, 2026-11-05.
Branch `team/krn-038-20261105`, worktree `worktrees/krn-038-20261105`.
Only `tools/research/crypto-source-integrity`,
`fixtures/public/crypto-source-integrity` and
`docs/procedures/crypto-source-integrity` are changed. Task remains in progress
for coordinator review and common checks. Do not complete or modify KRN-028.

## Findings and correction

All 67 named catalog inputs were independently compared to complete canonical
inputs. There are three historical Mbed TLS strict-prefix truncations:

| Path | Old / complete bytes | Complete SHA256 |
|---|---:|---|
| `library/gcm.c` | 37470 / 44572 | `202ac639d0c3ce4d34025c68614023c1ac9381e80f0b210acf3204ff4a97f8b3` |
| `include/mbedtls/mbedtls_config.h` | 146493 / 159124 | `004edfaa0f9877a9f3baa7911ab708fd9d7c615f836f6b6674434e337145b7be` |
| `include/mbedtls/check_config.h` | 37470 / 48196 | `66696df9cc3f7cbbe84786046937242b18140963b94c34347404f7827c428efa` |

The other 64 inputs, including all 29 BearSSL entries and both component license
files, match complete canonical bytes. Historical cache hashes match the old
catalog, including the three partial files. HTTP 200 and those self-consistent
hashes were insufficient upstream-completeness proof. The cause of the partial
responses is unknown.

All 44 named API declarations and entire function bodies remain present in the
old prefixes and are re-established against complete canonical members. The
five GCM production bodies end by line 701; the cutoff is inside self-test code
at line 1117. Default configuration review lacks its final 12631 bytes; the
configuration-check header lacks 49 additional error directives and ends in an
identifier at line 900. Detailed impact, full identities, source lines and
bounded prior-claim requalification are in README.md and the two fixtures.
The historical KRN-028 full-source provenance claim is superseded for the three
listed inputs. Its check outcomes, selected-layout measurement and parsed
vector evidence remain historical records, unchanged. No missing algorithm
behavior is inferred from a source-presence check.

Canonical Mbed TLS pin is `068ff080b369adfac81509f9b57b2afabaf82dc5`.
The full accepted official archive SHA256 is
`ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937`.
All 38 named members are regular, uniquely named entries under that revision's
archive root. BearSSL pin is `7bea48e5e850ab4cafbe68d3765cdaba13a86d6f`;
the actual Git commit object, tree and each of 29 blob identities are checked
read-only. The complete-source manifest binds exact members, sizes, SHA256,
computed Git blob IDs, repository pins, licenses and old identities. Component
notices are checked; Apache-2.0 is elected for dual-licensed Mbed, MIT preserved
for BearSSL. No restricted source bodies are added.

KRN-029 XTS was independently qualified against the full archive and remains
valid. Its `check_config.h` was already complete. This audit separately replays
the accepted `common.h` include-only patch from exact canonical SHA256
`adfd493f8ecb11f87f7e75f270a97cbd05d1902345ef32db51d39c076e4f8fde`
to accepted SHA256
`3f7b4261ac2b7b429d0e7729aedeb4c26ad6a5e29d8878ad0437e68bbf4b2381`.
It does not rerun XTS vectors or establish additional runtime semantics.

Findings were promptly relayed to the coordinator for DES/GCM/ChaCha/RSA.
The coordinator confirmed on 2026-11-05: DES used 15 complete archive members
plus its named common patch; GCM consumed the full archive before compiles;
ChaCha audited 17 canonical files and replaced its partial check_config input;
RSA checked all 33 files against canonical Git, including 15 historical-catalog
overlaps. These consumer statuses are coordination reports, not new consumer
tests by this task. No consumer implementation was changed here.

## Actual verification and evidence

Implementation commits: `378d1fb` and
`76175ede93110642346a3fc597f9d5edef7128b9` (the frozen final tested commit).
CRYSRC-001 was registered before discovery; CRYSRC-002 before final verification.
Three bounded discovery passes progressively added full-body extents and actual
patch/member/archive controls. Their original outputs are preserved. No failed
source measurement is hidden. An initial ledger registration rejected the raw
capsule's artifact dictionary; the unchanged capsule was referenced by a new
MAIN-relative list envelope and registration then passed. The final recorder
captures the actual child exit and writes that envelope directly.

Final command, exit **0**:

```sh
PYTHONDONTWRITEBYTECODE=1 GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 \
python3 tools/research/crypto-source-integrity/run.py \
  --run final-commit1 --experiment CRYSRC-002
```

Final source audit: **67 entries, 64 matches, 3 exact truncations, 44 complete
API bodies, 14 rejected negative controls**. Actual `/proc/self/status` VmHWM
41480 KiB, VmRSS 36504 KiB; no inherited `ru_maxrss` is treated as fresh memory.
All 67 historical source hashes and the shared complete archive were rechecked
unchanged at run end. Git lazy fetching and optional locks were disabled.

The controls reject the real partial header with its matching wrong raw hash,
a same-length byte change with a matching self-hash, wrong revision, wrong
member, a valid different member's contents, the real BearSSL parent revision
with current bytes, truncated Bear source, truncated full archive, changed
archive revision, modified patch base, modified patch result, unpatched result,
wrong patch member and wrong patch context. Complete canonical inputs and the
exact accepted include-only patch are positive controls.

Final MAIN-relative evidence:

* `worktrees/krn-038-20261105/artifacts/crypto-source-integrity/final-commit1/ledger-evidence.json`
  SHA256 `e7b634659e038aab56af76f2b4b3fa5ae44e35536c5c8df6e94183344236806c`.
* Inner `evidence.json` in the same directory:
  SHA256 `51bca1e7ebf66033874c22364661d6b9e29a21058a0fbbf94897d6d15d7d7a00`.
* The ledger envelope binds 73 actual local artifacts: all Git read command
  stdout/stderr, generated manifests, raw capsule and recorder stdout/stderr.
  The raw capsule also records source inputs, exact commands/exits, source/tool/
  Python/Git identities and all controls. Public qualified-evidence.json binds
  this capsule and the published tool/fixture hashes.

No network acquisition, extraction, compiler, algorithm execution, QEMU, device,
heavy build, install or shared-reference/cache mutation occurred. Source-only
qualification does not establish a full provider, native kernel execution,
FIPS, side-channel resistance, private Apple ABI or selected wrapper return
handling. Common `make check` is left for coordinator integration; no broad
backend build or duplicate runtime test is needed. Next: inspect the scoped
correction commits and immutable capsule, integrate, run common checks, and
explicitly accept before ledger completion.
