# Selected kernel AES-XTS integration

KRN-031 owns only the publication helper, two source patches, bounded builder,
component fixtures and this procedure. The accepted KRN-029 adapter, Mbed source,
headers and AVF runtime remain unchanged. No restricted Apple implementation is
copied into this change. Actual XNU/donor sources are read from pinned Git objects
with lazy fetch and optional locks disabled, then patched only in fresh owned
artifact copies. Preserve their original licenses/notices.

## Public modes and provider startup

`kernel_provider.h` uses the actual selected `ccmode_xts` declaration. The two
public descriptors are **const objects with static lifetime**. Their typed
callbacks forward to private modes created by the real accepted factory. Init
requires exact descriptor identity, not a caller copy; contexts retain KRN-029's
key/tweak address, storage, lifetime and serialization requirements. Private
modes never escape and are not mutated after ready publication.

A one-time atomic prepare moves0/unprepared to1/preparing to2/ready or3/failed.
The supported kernel call is serialized EARLY_BOOT, before crypto registration.
Acquire/release publication also rejects unexpected contenders during preparation.
A repeated ready call returns0 without rewriting objects. A failed factory or
contradictory metadata makes failure sticky. Before ready, getters returnNULL,
init returns a genuine call-sequence error and clears admitted key storage,
key_sched clears rather than accepting a successful schedule, set_tweak fails,
and block operations returnNULL. No successful unsupported callback is supplied.

The608-byte key and48-byte tweak constants are bound to accepted KRN-029 layout,
checked against both real private factories before release publication, and
compared with actual selected native declarations/object bytes. Descriptor80/8,
opaque context16-alignment, and fixed1072-byte caller storage are genuine target
measurements. A profile/layout change fails publication rather than silently
assuming a foreign context fits. Public bytes remain unchanged through preparation,
repeated/concurrent calls and actual encryption/decryption. C const/static-lifetime
is established; this component test does not qualify physical page write protection.

The fresh provider patch supplies two static descriptor references at table
offsets144/152 and prepare/getter checks before the existing deferred SHA256
assignment and registration. The real object has36 relocations: all original34
names plus these two references. Slot48 remains startup-deferred SHA256;19 other
fields remain unsupported zero entries. The real native BL relocations establish
prepare/getter/SHA256/register order within actual `minicrypto_init`. No PRNG,
digest, unrelated source, export list, feature setting or existing provider is
replaced. The helper does not itself register a provider.

## Actual selected caller patch

The genuine selected `libkern/crypto/corecrypto_aesxts.c` previously discarded a
NULL xts return and reported0 even on rejected block operations. Both directions
now return actual `CCERR_PARAMETER` when the descriptor rejects the operation,
while preserving set_tweak error propagation and all signatures. This status
expresses a rejected call; the pointer API does not expose a more detailed backend
reason. Existing non-multiple-of16 panic behavior is preserved. Key/tweak-length
policy and other original wrapper behavior remain separate caller contracts.

Actual selected caller code is compiled with the coherent native compiler/recipe,
not replacement SDK declarations or hand-written wrapper models. The full real
mc_provider object is compiled and decoded separately. The synthetic runtime's
`test_table` has only the two real XTS entries and exercises the genuine selected
registration routine plus caller; it does **not** execute full mc_provider startup,
its PRNG/digests or a full provider. Unsupported fields are not stubbed into success.

## Profiles and coherent native inputs

Original provider/caller compiler flags, features, header and export inputs are
retained, with only source/output/dependency paths and an owned include path
substituted. The actual compiler is the accepted storage-qualified native binary
SHA2567972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82.
New AES/adapter objects retain KRN-029's explicit software ROM-table,
general-registers-only/strict-alignment/no-outline-atomics profile; no ALT,
assembly, ISA acceleration, heap or entropy implementation is introduced.
The genuine Clang builtin header source is pinned as in accepted KRN-029.

`replacement-components.json` binds the two replacement sources/objects, three
additional real kernel objects, all980 other original identities and3156 original
dependencies. Actual imports resolve to retained genuine providers or the new
components; no new duplicate provider is accepted. Coherent native metadata,
features, aliases, layout, export lists and the accepted37 missing private ARM
exports are retained. The qualified287-member compiler-runtime archive is separately
rehash-bound as LINK-ONLY support. Its resource directory is not used for compiling
these kernel TUs; `cc_kext` is not a corecrypto provider. No full kernel link occurs.

## Host and ARM component evidence

The ASan+UBSan host publication fixture uses actual selected headers/helper/AES.
A fresh copy of the real factory has a deterministic entry gate so16 concurrent
contenders encounter actual state1. They reject without exposing modes; after
release the original real factory completes, and16 concurrent ready calls perform
real AES against independent expected data. A separate fresh real factory copy
reports a wrong size; the unchanged helper rejects publication permanently. These
controls are instrumented source variants, not substituted fake algorithms.

The ARM fixture links actual patched caller, publication helper, unchanged real
adapter/AES, genuine registration source and owned synthetic runtime services.
Zeroization delegates to accepted volatile stores; panic and stack-check failure
stop the guest. Its constant public stack canary is fixture support and no claim
about production entropy. Accepted runtime helpers and shim/QEMU remain unchanged.

Static descriptors contain actual linked high-VA callbacks. The new owned fixture
maps TTBR0 identity RAM/UART and TTBR1's39-bit VA alias atfffffff004000000 to
PA40000000..+256MiB using1282MiB blocks (L1index448,L2index32). Independent final
MachO inspection reads the actual test-table references, descriptor metadata and
all callback VAs. CPU output verifies linked code/descriptor/callback identity,
actual TTBR roots, SCTLR.M and table entries, then executes the real callbacks.
This is a synthetic component mapping, not XNU MMU policy or Exynos qualification.

Controls use wrong cookie, genuinely shifted high mapping, a corrupted expected
ciphertext in the actual owned payload, the genuine original unpatched caller
(error-propagation counterexample), failed real factory metadata, preserved panic
and spin timeout. No runtime marker is accepted without the matching linked
addresses, expected case outcome and cleanup. Factory-failure case executes zero
algorithm vectors and labels that explicitly. The primary vector/oracle corpus is
the accepted1200 full-block raw-tweak NIST records plus20 OpenSSL records.

Register a fresh experiment before each qualified replay. Native preparation is
one compiler at a time under256MiB monitored owned RSS and4GiB MemAvailable floor:

```sh
python3 tools/build/xnu_kernel_xts.py --root /home/egor/dev/pet/s24-ios-exynos \
  --run FRESH_NATIVE --experiment REGISTERED_ID \
  --host-controls --prepare-guest --prepare-controls
```

Before any guest, obtain the coordinator's exclusive lease. One guest RAM256MiB,
owned RSS<=512MiB, finite deadline and owned-session cleanup. Release after all
children quiesce; do not reserve it while preparing source. The guest command is:

```sh
python3 tools/build/xnu_kernel_xts.py --root /home/egor/dev/pet/s24-ios-exynos \
  --run FRESH_GUEST --experiment REGISTERED_ID --execute-guest --all-controls \
  --native-artifacts artifacts/kernel-xts/FRESH_NATIVE \
  --lease-grant 'Exact coordinator grant context'
```

No full crypto, private Apple ABI, FIPS, side-channel assurance, encrypted-volume
compatibility, full kernel/native image/startup, Exynos MMU or S24 operation is
qualified. Follow-up integration must consume the coherent manifests and preserve
all remaining unsupported/provider/runtime/hardware gates.
