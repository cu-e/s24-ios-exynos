# Source-available crypto candidate qualification

KRN-028 · owner `codex-team-crypto-candidates-20261105-be` · 2026-11-05.

Experiment CRYCAND-001 procedure:

1. Bind the selected XNU revision, genuine declaration/descriptor/context
   headers and accepted KRN-023 all56-slot/21-missing callback/demand catalog.
   Keep compiler-runtime support independent from crypto-provider identity.
2. Pin at least two primary real algorithm candidates to full commit IDs;
   acquire only named public sources/notices into owned ignored local storage.
   Inspect API definitions and algorithm bodies, component licenses, allocation,
   entropy, context ownership/alignment and kernel portability dependencies.
3. Map every missing callback to actual supported APIs or an explicit source/
   API gap, with concrete bridge requirements. Preserve XNU descriptor and
   caller-owned storage contracts; do not cast foreign contexts into XNU.
4. Build a repeatable requirements/source/hash verifier. Execute real omission,
   incompatible-assessment and source/provenance mutation controls. At most one
   tiny compile may inspect genuine selected types; no full library build,
   restricted Apple source copy, invented SDK declarations or empty callbacks.
5. Record dated commands/exits, pinned provenance, existing artifacts, hashes,
   exact scope and a concrete bridge plan/handoff. Commit assigned paths only;
   retain in_progress pending coordinator review. No FIPS/private ABI/crypto
   runtime/native success claim follows from this research.

Bounds: no phone/ADB/root/MMIO/flash/emulator/global installation; no heavy-build
lease requested. At most one small compiler process and child RSS <=256MiB.
Every Git subprocess disables lazy fetch and optional locks. Shared references
and artifacts are read-only; named public acquisition stays in this worktree.

## Frozen source candidates and requirements

The accepted KRN-023 catalog supplies all21 missing fields, offsets and direct
source-demand references. `requirements.json` binds them back to full selected
XNU `c54f35ca767986246321eb901baf8f5ff7923f6a` declarations and caller source,
including actual helper typedefs and the ten ChaCha function-table signatures.
The separate compiler-runtime `-lcc_kext` request is not a crypto provider.

| Candidate | Exact primary source and notices | Main interface constraints |
|---|---|---|
| [Mbed TLS](https://github.com/Mbed-TLS/mbedtls/tree/068ff080b369adfac81509f9b57b2afabaf82dc5) 3.6.7 | Commit `068ff080b369adfac81509f9b57b2afabaf82dc5`; selected files state Apache-2.0 OR GPL-2.0-or-later, with the Apache choice used for a proposed port; component notices retained | Real AES/XTS/GCM/ChaCha/DES/RSA source. Whole-unit XTS differs from mutable tweak. GCM allocation/configuration paths differ. RSA import and public verification allocate, with no selected free hook. |
| [BearSSL official repository](https://www.bearssl.org/) | Commit `7bea48e5e850ab4cafbe68d3765cdaba13a86d6f` from the author's Git endpoint; actual LICENSE.txt and reviewed source files carry MIT notices | Real static-context ct cipher/GCM/RSA source. No reviewed public XTS/CBC-CS3 API. ChaCha AEAD API is whole-message. RSA key views borrow big-endian arrays; ownership/OID/return mapping remains. |

`candidates.json` contains67 named source/notice files with hashes,44 real API
declarations/algorithm bodies, and42 assessment rows: every missing field for
each candidate. A missing API remains a gap, not an empty callback. These are
bounded named-source assessments, not complete library dependency closures,
verified constant-time implementations, build passes or production endorsement.
No restricted Apple implementation is copied into maintained files.

The sole small compile includes actual selected headers and measures only
layout, using the unchanged qualified compiler/recipe. Actual values are:

| Selected contract | Measured bytes/alignment |
|---|---|
| ECB/CBC/XTS/GCM descriptor sizes | 48 / 40 / 80 / 80 bytes |
| Opaque mode context alignment | 16 bytes |
| Fixed ChaCha context | 256 bytes, alignment8 |
| Fixed XTS key-context storage | 1072 bytes each for encrypt/decrypt |
| Fixed AES-CBC key-context storage | 288 bytes |
| Fixed RSA public container | 1584 bytes, alignment8, maximum4096-bit key |

The compile exited0 with peak child RSS130620KiB. No candidate context was
compiled or proven to fit these limits. A foreign type's small apparent size
does not establish representation, ownership, constness or cleanup compatibility.

## Concrete implementation handoff

[bridge-plan.md](bridge-plan.md) is the next-interface plan, with AES-XTS in
the separate KRN-029 task first. It specifies all four selected XTS methods,
per-separate-key lengths, direction-specific data schedules, always-encrypt
tweak schedule, raw16-byte IV, XOR/AES/XOR and pinned GF128 progression, split
calls, pointer return, const-context adaptation and actual1072-byte bound.
It also records that the selected wrapper ignores the XTS callback's return.
No provider or adapter is implemented in KRN-028.

Other gates remain explicit: managed GCM's12-byte IV is4-byte salt plus an
8-byte big-endian counter; ChaCha increment semantics must not be guessed from
GCM. RSA needs genuine XNU number storage and endian/limits analysis, not a
foreign pointer cast or persistent heap context without a free hook. Desktop
entropy seeders are excluded from a proposed kernel raw-primitive selection.
Native/kernel context, side-channel, entropy and lifetime assurance remain open.

## Independent vectors and repeatable verification

For a later DES/TDES adapter, primary
[NIST CAVP vectors](https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/block-ciphers)
are acquired with archive/member SHA256: KAT_TDES.zip and tdesmmt.zip. Exactly
1000 ordinary ECB/CBC records across14 files are parsed and checked as data;
seven interleaved CBCI files are excluded from normal CBC. `KEYs` repeats one
8-byte key into K1/K2/K3; MMT files preserve distinct key fields and their actual
directions, including decrypt-only2-key cases. No candidate executed these
vectors here. They are DES/TDES vectors, not the independent XTS vectors that
KRN-029 must obtain. Informal vectors do not establish CAVP/FIPS validation.

Final CRYCAND-002 is bound to commit
`37c74737cc760602e9c392dccd1d67da13c48db8`:356 source/data checks pass,
including57 negative controls, with no further compiler invocation. The
verifier's peak child RSS is25680KiB; the sole earlier target layout compile
peaked at130620KiB. Its registered plan precedes the actual final run.
[qualified-audit.json](../../../fixtures/public/crypto-candidates/qualified-audit.json)
binds the exact existing capsule, hashes, scopes and acceptance assessment.

Register experiments in the primary ledger first. Existing pinned sources can
be verified offline without another compiler call:

```sh
python3 tools/research/crypto-candidates/verify.py --run fresh-audit
```

For a fresh isolated source cache, acquisition is explicit and hash-checked
before write, with safe named paths and Git fetching confined to its own bare
repository. It never runs upstream setup scripts or builds algorithm code:

```sh
python3 tools/research/crypto-candidates/fetch.py \
  --cache-root tools/research/crypto-candidates/local/new-cache
python3 tools/research/crypto-candidates/verify.py --run fresh-cache-audit \
  --cache-root tools/research/crypto-candidates/local/new-cache
```

The layout witness points to the one existing measured target object and its
source/compiler/dependency hashes. Repeating layout compilation is unnecessary
for the source verifier. `measure_layout.py` is retained for a separately
planned independent reproduction if needed.

Actual negative controls remove each candidate's assessment of each of21
fields, change pins/source bytes/real algorithm bodies, misrepresent whole-unit
XTS and whole-message ChaCha as the selected streaming interfaces, allow unsafe
foreign casts or persistent RSA heap contexts, confuse XTS stealing with
CBC-CS3, corrupt real vector lengths and misclassify interleaved CBCI.
Checks bind actual source and meaningful interface/ownership claims; none
implements or tests a substitute cipher. Acquisition failures for a nonexistent
Mbed license subpath and the first outdated NIST filename are retained before
the correct primary files were obtained. Source-cache verification is distinct
from a backend build or algorithm execution.

The coordinator owns common repository checks and integration. KRN-028 remains
in_progress until acceptance. Full crypto, private Apple ABI, FIPS, kernel link
and native-device qualification remain false.
