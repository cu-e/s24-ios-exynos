# INT-003 platform integration handoff

Owner `codex-integrator-platform-20261106-cn`, permanent crypto/drivers/platform
integration role. Worktree `worktrees/int-platform-20261106`, branch
`team/int-platform-20261106`, initial base
`aac27cfbc0d71b34eda33ddf366c72427507ae0b`. Only own reporting under this directory;
component and independent-review files are exact scoped cherry-picks, with no
original-owner, registry, generated-view or shared input edits.

## KRN-036 + REV-021: prepared, publication pending

The bounded CBC-CS3 component is accepted for isolated integration based on
the exact frozen implementation/review, verified real capsule/log/dependency
bytes and independent no-finding recommendation. Overall integration remains
pending root's concrete plan approval, shared-lock publication and common check.
No MAIN publication or common/algorithm/guest run has occurred from this role.

Original ordered commits:

1. `09111a944045ffad348e790c9f7377f6628ca0b5`
2. `89ff8f2a6f616c5a3662f8e91cb54396318eb405`
3. `8a4233a4446dc05fa70ad53921b779f50762f8a8`
4. `55ea7b7d0e49d87c72c2c6953934ecc33cc8c200`
5. `80ee7fde7b7a67310a8eecdb1a015aa6aa8081ad`
6. `b9fa5ca8ecae38d42474bd02dfa5324aac937238`
7. `8b961ac546f9819ae231cdfd5df40fe6d6f7cb73` (independent review).

Exact source-to-candidate mapping is in cts3-prepared.json. Prepared component
tip `86e9b5ef6b281a7262d62698ea3d23959f435985`; subsequent commits add only these
integration reports/tools. Every replay patch matches original binary/full-index
Git diff bytes and all68 final component/review files match frozen source hashes.
The 18 implementation/procedure and50 independent-review paths are scoped.
Candidate `git diff --check` passes. Dependency KRN-029/032/038 statuses are done.

PLATINT-001 was registered before verification. Actual commands, both exit0:

```sh
PYTHONDONTWRITEBYTECODE=1 GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 \
python3 docs/integration/platform/verify_cts3.py cts3-binding1
PYTHONDONTWRITEBYTECODE=1 GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 \
python3 docs/integration/platform/prepare_candidate.py \
  artifacts/platform-integration/cts3-binding1/evidence.json cts3-prepare1
```

Audit verified623 unique actual inputs and128 read-only Git commands, including
the implementation capsule `a95b5c69a14519bc2cfc2da8dea025a684bda3a82647b27e66d93d90109afc57`
and review capsule `19069702c8083d8428dfda91bd337708449ceec86f7a0907d4792a84236fae3c`,
all actual dependency/artifact/source hashes, committed final bytes, canonical
AES archive members, selected Git reads, unchanged compiled-source continuation,
retained failed stages and quiescent guest results. Actual old host/ARM28794,
381 CS3/18 CBC records and independent7722 checks remain original measurements.
They were not rerun. Prospective admission used three samples >=4GiB; audit
actual VmHWM26008KiB. Local evidence directories are
`artifacts/platform-integration/cts3-binding1` and `cts3-prepare1`; their immutable
digests are in cts3-prepared.json.

Production native `__memcpy_chk` provider closure remains false; fixture memory
and AES CBC16 are test-only. NFS ignores the size_t return and its native error
integration remains unqualified. Provider/private ABI/FIPS/side-channel/native/
full-kernel gates remain explicit. Only original cb/ck owners close their tasks
after final coordinator integration acceptance; INT-003 does not impersonate them.

## Shared gate and next step

INT-002's kernel integrator owns the sole `tools/integration_gate.py`. Use its
frozen/root-reviewed tool for both integrators. One stable
`MAIN/state/.integration.lock` covers operative fresh HEAD/path/source mapping
and evidence checks, approved FF-only publication and one common check. No outer
lab lock is held. Strong source/candidate patch equality, stable lock inode,
pre-publication4GiB admission, aggregate RSS monitoring and dirty-path protection
are required. Initial protocol peer findings were sent before tool freezing.

Root has not yet authorized this concrete candidate for MAIN publication/common
check. Prepare the exact plan with current frozen tip, path set, commit mapping
and actual bindings; run only shared-gate audit after the protocol is reviewed.
If protocol publication advances MAIN, refresh/revalidate the isolated candidate
and plan before approval. Preserve unrelated dirty MAIN ledger/views and never
copy this worktree's stale ledger. Failures retain actual published/check state,
without implicit rollback.

KRN-039 initial frozen a948c6e/16a4b98... candidate is not accepted here. Producer
ci reported first CPU failure before DES at an unaligned pre-MMU DT load, with
zero surviving children and lease released; guest compile flags are being
corrected while native algorithm/helper objects remain unchanged. Wait for its
new final capsule/frozen series and REV-022 final independent review before
accepting039. No other guest is authorized from this integration role.
