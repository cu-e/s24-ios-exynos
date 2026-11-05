# Complete crypto candidate source audit

KRN-038 is a source-only correction to KRN-028. Historical caches, manifests,
capsules and consumer implementations remain immutable. Only permissively
licensed Mbed TLS and BearSSL source bodies are inspected here. No compiler,
crypto implementation, emulator or device is executed.

CRYSRC-001 procedure, planned before verification:

1. Read all 67 named entries from the frozen KRN-028 catalog. Compare their
   recorded hashes/extents and actual historical cached bytes with complete
   canonical members, using the independently accepted KRN-029 official Mbed
   TLS archive and the exact-pinned official BearSSL Git objects. Require the
   full archive digest, revision/member identity and Git blob digest, rather
   than accepting an HTTP response's self-consistent hash.
2. Publish a corrected manifest under this task's new fixture path. Record
   both historical and canonical identities and every discrepancy. Reassess
   the 44 named API declaration/body facts and bridge assertions using complete
   canonical files; preserve their source-review limits.
3. Exercise actual truncated bytes with a matching wrong raw hash, changed
   revision, wrong archive member, changed bytes and patch pre/post controls.
   Inspect the separately qualified XTS include-only patch without changing it.
4. Save dated commands, exits, source/tool/output identities, actual process
   VmHWM, immutable capsule hashes and a handoff. Do not build or overwrite
   upstream caches. Keep KRN-038 in progress until coordinator acceptance.

## Result and correction

The audit finds **three strict-prefix truncations**, all in Mbed TLS. The other
64 entries (35 Mbed TLS and all 29 BearSSL files) are byte-identical to complete
canonical inputs. Historical cached bytes still match their recorded hashes;
that consistency did not establish complete upstream identity.

| Historical path | Historical bytes | Canonical bytes | Missing bytes |
|---|---:|---:|---:|
| `library/gcm.c` | 37,470 | 44,572 | 7,102 |
| `include/mbedtls/mbedtls_config.h` | 146,493 | 159,124 | 12,631 |
| `include/mbedtls/check_config.h` | 37,470 | 48,196 | 10,726 |

Use [the corrected manifest](../../../fixtures/public/crypto-source-integrity/complete-source-manifest.json)
for complete-source hashes, extents, full revisions, license choice and exact
archive members/Git blobs. Each entry retains its historical identity and the
comparison result. `git_blob_sha1` is computed with Git's blob framing; Mbed
identity is established by the complete qualified archive/member, while BearSSL
also matches the blob ID in the exact commit's actual Git tree. No new Git
acquisition, shared hydration or HTTP request occurs.

[Historical requalification](../../../fixtures/public/crypto-source-integrity/historical-requalification.json)
records every discrepancy, complete API body extents, source anchors, license
notice lines and the XTS patch's exact pre/post identities.

* `gcm.c` stops at line 1117 inside the `mbedtls_gcm_self_test` code, immediately
  after `key_len)`. Its missing tail includes further self-tests, cleanup and
  closing preprocessor directives. The five catalogued production GCM API
  bodies end by line 701 and are complete in the historical prefix. Their
  declaration/body facts and configuration-dependent inline/generic paths
  are re-established from the full canonical source. The historical whole-file
  provenance claim is requalified; that cache cannot stand as a complete
  self-test source or reproduce the unmodified upstream translation unit.
* `mbedtls_config.h` stops at line 4159 in a commented snprintf option. Its
  remaining option documentation and commented defaults are absent. This
  invalidates complete-default-configuration review, not a measured compiled
  profile (KRN-028 never compiled a candidate backend). No named API fact uses
  this header directly. Complete configuration and dependency qualification
  must use canonical inputs under each consumer's own profile.
* `check_config.h` stops at line 900 in `MBEDTLS_MD_CAN_SH`. The omitted suffix
  contains 49 `#error` directives, including threading, PSA and integer-width/
  assembly consistency checks, and closing directives. Complete prerequisite
  review and full-header identity were not established by the historical
  cache/hash checks. No named API fact uses this header directly.

The historical `qualified-audit.json` claims `source_provenance: true` for 67
complete pinned inputs and the associated whole-file assertions are superseded
by this correction. Its actual 356-check outcome remains an immutable historical
observation about the inputs and checks then used; passing those controls did
not detect these partial responses. The raw HTTP acquisition metadata records
status 200 for the truncated files. This audit does not establish why those
responses ended early.

All 44 named API declarations and **entire** function bodies are present in both
the historical prefixes and complete canonical inputs. This re-establishes
their bounded source facts. It does not promote token/presence checks to full
call-graph, context-fit, configuration, allocation or ABI proofs. In particular,
Mbed RSA allocation, Bear borrowed RSA byte arrays/local stack array, GCM
configuration-dependent ownership and the need for selected-mode adapters
remain source facts with the original implementation gates. KRN-028's selected
header/layout measurement and parsed vector corpus are separate historical
measurements; neither is rerun or invalidated here.

The accepted KRN-029 XTS implementation independently qualified its vendor
files from the **complete** official archive. Its canonical `check_config.h`
already has 48,196 bytes / SHA256
`66696df9cc3f7cbbe84786046937242b18140963b94c34347404f7827c428efa`.
This correction does not invalidate that implementation or its independent
vectors. The named `common.h` include-only patch is replayed from the canonical
base in memory and compared with the accepted local bytes; undocumented base,
result, context or member changes are rejected. This is source identity
qualification, without a new XTS semantic or execution claim.

## Reproduce

From this task's worktree, with the existing read-only source inputs available:

```sh
PYTHONDONTWRITEBYTECODE=1 GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 \
python3 tools/research/crypto-source-integrity/run.py \
  --run fresh-source-audit --experiment CRYSRC-002
```

The default Mbed input is the accepted KRN-029 complete archive, SHA256
`ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937`, from
the [official exact-pin archive](https://github.com/Mbed-TLS/mbedtls/archive/068ff080b369adfac81509f9b57b2afabaf82dc5.tar.gz).
BearSSL is read from KRN-028's existing bare repository at
`7bea48e5e850ab4cafbe68d3765cdaba13a86d6f`, originally acquired from the
[official repository](https://www.bearssl.org/git/BearSSL).
Mbed TLS's dual component license is preserved with the Apache-2.0 choice;
BearSSL's MIT license and per-file notices are preserved. The fixtures publish
metadata, not restricted implementation bodies.

The recorder saves the actual audit exit, stdout/stderr and a MAIN-relative
`ledger-evidence.json` envelope; the inner `evidence.json` retains detailed
source identities, command output hashes and controls. The audit compares its
generated manifests with the published correction. Calling `audit.py` directly
with `--publish` deliberately writes only these new owned fixture paths when
preparing a correction. Existing run names are rejected. All logs go to this
worktree's ignored `artifacts/crypto-source-integrity/` tree. Negative controls
use the real partial header, same-length modified bytes with a self-consistent
hash, wrong revision (including the real BearSSL parent commit), wrong member,
truncated archive and actual patch pre/post/context/member changes. No source
is written to a shared location, extracted, built or executed.
