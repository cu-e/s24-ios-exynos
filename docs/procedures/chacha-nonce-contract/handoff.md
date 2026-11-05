# KRN-037 nonce contract handoff

Owner: `codex-team-chacha-nonce-contract-20261105-bx`; branch/worktree `team/krn-037-20261105` / `worktrees/krn-037-20261105`. KRN034 implementation and every other owner's reservation remain unchanged. Keep this source investigation in progress pending coordinator review.

**No applicable selected-version nonce increment behavioral contract was recovered.** The bounded source-fact investigation and14 checks/11 negative controls pass; all-ten callback acceptance remains false. No nonce increment implementation, fallback success or translated restricted body was produced. No compiler, QEMU, build, crypto execution, device or MMIO operation occurred.

## Supported selected facts

Selected XNU is `c54f35ca767986246321eb901baf8f5ff7923f6a`. Its `EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h`, SHA256 `583085c5a52979eb28bdec94a69d00b4c3536034c8f9763de9de1bb1101e0a93`, declares a12-byte nonce, mutable nonce parameter and integer result for `ccchacha20poly1305_incnonce`. It has no named incnonce documentation. These declaration facts establish no encoding or success contract.

Five selected source surfaces were independently identity-checked against exact Git tree blobs: that external header, `libkern/crypto/corecrypto_chacha20poly1305.c`, `libkern/libkern/crypto/chacha20poly1305.h`, `libkern/libkern/crypto/register_crypto.h`, and `bsd/netinet6/esp_chachapoly.c`. They expose declarations/table forwarding; the named ESP consumer has no incnonce occurrence and four setnonce occurrences, constructing its explicit nonce separately. ESP protocol construction does not specify this general API's increment operation. These are bounded named-surface observations, not a binary-demand or all-consumer compatibility claim.

The [selected header](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h) and [ESP consumer](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/bsd/netinet6/esp_chachapoly.c) are the primary selected citations. Complete revision/path/blob/SHA256/byte identities appear in `fixtures/public/chacha-nonce-contract/contract-facts.json`.

## Bounded official historical coverage

The following official XNU headers were fetched transiently through exact peeled commit references. Complete byte counts, SHA256 and canonical Git blob IDs were verified. None supplies incnonce-specific documentation or increment implementation; each has one bare declaration and the12-byte nonce constant. Tag numbers are source identities, not assumed matching OS/firmware versions.

| Official tag | Peeled commit | Header Git blob |
| --- | --- | --- |
| xnu-8796.101.5 | aca3beaa3dfbd42498b42c5e5ce20a938e6554e5 | a4acf0e51bfe87e92731dbcace608fded228213c |
| xnu-8020.121.3 | fdd8201d7b966f0c3ea610489d29bd841d358941 | f2ce5e2654eae15e679679bee42334fb0355e3d6 |
| xnu-7195.141.2 | 776661b72c2db9861865df68d309f6f35faccff4 | f2ce5e2654eae15e679679bee42334fb0355e3d6 |

Primary header links: [8796.101.5](https://github.com/apple-oss-distributions/xnu/blob/aca3beaa3dfbd42498b42c5e5ce20a938e6554e5/EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h), [8020.121.3](https://github.com/apple-oss-distributions/xnu/blob/fdd8201d7b966f0c3ea610489d29bd841d358941/EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h), [7195.141.2](https://github.com/apple-oss-distributions/xnu/blob/776661b72c2db9861865df68d309f6f35faccff4/EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h).

The current official `apple/corecrypto` public heads `main` and `2026-05` both point to `9612a959abb6eac0aac3ee6a7245c46365c9d81b`; no tag was returned by the complete heads/tags query. Its actual local Git commit object was checked against its canonical commit SHA and contains no parent. This establishes no older commit reachable from those observed public refs; it does not establish that no historical delivery exists elsewhere. The parent metadata HTTP request was unavailable, so the final parent-count proof deliberately uses the provided read-only filtered Git object instead of a default value.

Six named older official delivery probes used HEAD only: `https://developer.apple.com/security/src/corecrypto/corecrypto-{2021,2022,2023}.{tar.gz,zip}`. Five returned404. The2022 tar.gz probe ended with RemoteDisconnected and remains inconclusive. No archive was downloaded and no agreement was submitted. The official `apple-oss-distributions/corecrypto` API endpoint returned404. The current [Apple security page](https://developer.apple.com/security/) linked only the current GitHub repository for corecrypto and contained no incnonce reference. These specific endpoint observations do not establish exhaustive archive absence.

## Current official availability and test facts

Current official Apple pin `9612a959abb6eac0aac3ee6a7245c46365c9d81b` is newer than the selected source profile. Six named files were read transiently with exact Git blob/SHA256 validation: public/private/internal headers, the implementation file and two test files. Restricted bodies were never saved, copied into tracked code or translated; only minimal source identities and facts are retained.

The implementation file `ccchacha20poly1305/src/ccchacha20poly1305.c` has Git blob `96e59142ea805fc98b297b83dbd9c20dd502486e`, SHA256 `fbb12a35123de83430be214ce2f212b7ec94ac90fc534ee54c5d047e23af9134`,34869 bytes. At the named incnonce definition, its only explicit return is nonzero1; a guard macro token is present, and no direct nonce/context argument reference occurs. Guard-macro semantics are not asserted. This is availability evidence for that newer source, not nonce encoding, selected API behavior or compatibility.

Both named official current tests have no incnonce substring:

| File under ccchacha20poly1305/crypto_test | Git blob |
| --- | --- |
| crypto_test_chacha.c | 5d5cbe936101637926ae9db0fc813fe3a7f58aa0 |
| crypto_test_chacha20poly1305_runner.c | 1a903479824e2be2e145446d2857d143f67a1ccf |

The current public header retains the declaration without incnonce-specific docs; private/internal headers add no occurrence. No inference is drawn from unrelated test vectors, high-level CryptoKit, GCM managed nonces or the generic ChaCha RFC. Public availability is not an integration/redistribution grant, and no restricted implementation is retained as a project cache.

## Exact remaining contract and actionable KRN034 gate

The following fields are explicitly null in the fact manifest:

- Byte encoding; incremented byte range; increment byte order.
- Overflow result and whether nonce bytes mutate on overflow.
- Permitted lifecycle states; state after increment; selected success behavior.

Required next input: applicable primary evidence tied to the selected API/version that defines those fields, or a provenance-qualified implementation/test contract usable within the project's restrictions. A matching signature,12-byte constant, newer unsupported placeholder or explicit ESP nonce does not supply it. KRN034 must not claim all-ten callback coverage, fabricate an always-success increment, substitute a GCM convention or equate the current nonzero return with selected compatibility. Remaining callback implementation/test work belongs exclusively to KRN034's owner.

Eleven actual fact/profile controls reject a changed selected SHA, newer or historical profile substitution, different GCM method, signature-based compatibility, guessed little-endian encoding, guessed full nonce range, guessed overflow success, borrowed reset lifecycle, promoted working placeholder and changed official source blob. The offline verifier intentionally checks this explicit unknown-contract profile; it is not a crypto implementation or a global source authenticity service.

## Reproducibility, failures and handoff

Final bounded fact/gate evidence: `worktrees/krn-037-20261105/artifacts/chacha-nonce-contract/qualification-session3/evidence.json`; adjacent `report.json` and `contract-facts.json` contain14 checks,11 controls, actual six guarded Git commands/tool hashes and exact cited observations. Tested implementation commit is `0f12af807eb634bf81cfba946ebeb4c70b039178`. `fixtures/public/chacha-nonce-contract/assessment.json` binds final evidence/report/manifest digests.

CHNONCE001 records an inconclusive review of unchanged raw acquisition: identities were acquired, but its whole-body availability recognizer was too strict and its HTTP commit metadata unavailable. CHNONCE002 retains the actual strict-classifier failure; CHNONCE003 retains the actual missing-metadata assumption failure. Their original outputs and exact owned checker versions remain available (including the earlier Git commit), with no restricted source bodies. CHNONCE004 uses the completed canonical source-fact stage from the retained failure and independently verifies the actual commit object; it does not relabel a failed report as a pass. The final replay fetched no new restricted body and never assigned behavior to the guard macro.

Reproduction commands are in README.md. The final committed fixture also passes the offline profile verifier. Bounded source-availability/fact criteria are assessed satisfied, including the expressly allowed precise missing-contract result; the nonce behavior and all-ten callback acceptance are not satisfied. Coordinator next: inspect the scoped commits and source facts, relay this gate to the original KRN034 owner, and assess this research task without promoting it to an algorithm or compatibility result. Retain KRN037 in progress until review acceptance. No other owner, source reservation or blocked KRN026 state changed.
