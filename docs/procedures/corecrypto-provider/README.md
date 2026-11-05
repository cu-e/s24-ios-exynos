# Selected corecrypto provider audit

Task KRN-023, owner `codex-team-corecrypto-20261105-at`, 2026-11-05.

**Correction:** the initial audit incorrectly equated `-lcc_kext` with a
corecrypto/KEC provider archive. Selected Clang treats that token as a compiler
support request. Its Darwin override selects a compiler-rt resource archive
and silently omits it when absent. The crypto table measurements below remain
valid; CCPROV-001 through004's archive-identity inference is withdrawn.

Planned source-review experiment CCPROV-001:

1. Bind selected full XNU and donor Git revisions, register_crypto header/body,
   current native link arguments/evidence and actual minicrypto table object.
2. Identify the current primary public Apple corecrypto revision and default
   license; inspect only public metadata/named source text in owned ignored
   outputs. Do not incorporate or compile restricted provider source.
3. Compile one genuine selected-header layout probe using the measured real
   mc_provider recipe and existing qualified compiler. Independently inspect
   actual Mach-O offsets/table raw bytes and relocations; trace missing slots
   to source consumers. Identify all omitted slots, not only the eight already
   sampled by KRN-016. Check selected RSA callback signatures against genuine
   declarations and execute a deliberately incompatible-type compile control.
4. Produce a repeatable provenance/input/ABI checker with real source/hash,
   callback-byte/relocation, required-link-library and incomplete-provider
   negative controls. No provider archive or fake declarations are generated.
5. Record exact commands/exits, source/tool/commit hashes, existing artifacts,
   measured unavailable inputs and next integration gates. Commit owned paths
   only; retain in_progress pending coordinator acceptance.

Resource bounds: sequential small compiler work, each command <=45 seconds,
child peak RSS <1 GiB; no heavy builds, global installs, phone, ADB, root, MMIO,
flash or emulator. Shared references/artifacts remain read-only. Passing audit
or algorithm KATs establish neither link closure nor ABI/runtime/FIPS/native
compatibility. Coordinator owns shared make check after integration.

## Findings and exact source boundary

The selected [XNU registration header](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/libkern/libkern/crypto/register_crypto.h)
has 56 pointer members. A genuine arm64/iOS16.5 probe compiled with the existing
qualified selected compiler/profile measures size448, alignment8 and every
member's offset/storage. [registration-abi.json](../../../fixtures/public/corecrypto-provider/registration-abi.json)
enumerates **all56** members with actual raw-zero/relocation state, target
symbol, offset, source-demand count and referenced file/line/object. The header
is unchanged in the prepared selected source. Exact header identity is part
of this ABI observation; no SDK/private provider ABI compatibility follows.

The unchanged selected donor `mc_provider.o`, SHA256
`cf555d23591177363e3cda65ffdf1de553ac0387bec35ded9c724bad2826c923`,
has34 active callback/descriptor relocations and22 static zero slots. One zero,
`ccsha256_di` at offset48, is populated before registration in `minicrypto_init`.
The remaining21 are unsupported. The earlier eight were a measured sample,
not the complete unsupported set.

| Unsupported group | Members | Offsets in bytes |
|---|---|---|
| AES-XTS | encrypt, decrypt | 144,152 |
| AES-GCM modes | encrypt, decrypt | 160,168 |
| GCM helper callbacks | init-with-IV, increment-IV | 176,184 |
| ChaCha20-Poly1305 table | function table pointer | 192 |
| DES modes | ECB encrypt/decrypt, CBC encrypt/decrypt | 200,208,216,224 |
| Triple DES modes | ECB encrypt/decrypt, CBC encrypt/decrypt | 232,240,248,256 |
| DES key helpers | weak-key check, odd-parity update | 264,272 |
| CTS3 padding | encrypt, decrypt | 280,288 |
| RSA | make public key, PKCS1v1.5 verification | 304,312 |

Selected wrappers directly consume several missing slots: AES-XTS setup
explicitly panics if either mode is absent; GCM/ChaCha/DES wrappers dereference
missing descriptors/helpers; RSA wrappers dispatch through the two empty
callbacks after their size admission. File/line demand witnesses are in the
catalog. Source references do not establish runtime reachability. A zero
source-demand count means no direct reference in the scanned selected source
text/two inline headers; it does not prove a member safe to omit from private
consumers, macros, external kexts or future configurations.

The [registration body](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/libkern/crypto/register_crypto.c)
retains a table pointer, with the first non-NULL registration winning. It
performs no table copy, size/version negotiation or callback validation, and
publishes `crypto_init`. The selected donor also registers its own PRNG and
uses `STARTUP(EARLY_BOOT, STARTUP_RANK_FIRST, minicrypto_init)`. Its small
selftests and strictFIPS=0 DRBG setting do not establish complete algorithms,
entropy quality, initialization ordering, thread/interrupt safety or FIPS.
No registration was executed by this task.

## Compiler support request and separate crypto initialization

Pinned [MakeInc.def](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.def#L859)
sets `LD_KERNEL_LIBS = -lcc_kext`; the selected donor retains it. KLINK-011's
three recorded actual driver/linker-plan commands retain that exact flag.
Its two full-link attempts fail with no image, first at missing firehose,
then at missing pthread after supplying only the genuine firehose archive.
Those are outer Clang arguments, not proof that ld64 receives a literal
`-lcc_kext` search, or that this token names a corecrypto provider.

Exact selected Clang source is
[apple-libtapi fa9443738c1a18accef4244732ec6d6ee97a8133](https://github.com/tpoechtrager/apple-libtapi/tree/fa9443738c1a18accef4244732ec6d6ee97a8133).
[Driver.cpp:494](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/Driver.cpp#L494)
unconditionally rewrites the user library token to `OPT_Z_reserved_lib_cckext`.
[Darwin.cpp:2839](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/ToolChains/Darwin.cpp#L2839)
overrides the generic literal-library handling: it selects
`ResourceDir/lib/darwin/libclang_rt.cc_kext_ios.a` for iPhoneOS and appends it
only when `getVFS().exists(P)`. These three exact source blobs also match the
retained source lineage of the actual qualified compiler; hashes are in
inputs.json. This is compiler-runtime support, independent of crypto provider
identity, registration, callback coverage and runtime assurance.

The corrected audit runs the preserved genuine selected Clang driver with
`-###`, identifies its actual resource directory, and inspects backend ld64
arguments. A missing resource archive is silently omitted. An explicit
`-Xlinker -lcc_kext` plan is a literal-forwarding control and does not supply
or qualify any archive. No ld64 command is executed by these plans. The former
libcc_kext search-directory inventory was irrelevant to Darwin's compiler-rt
resolution and is removed. KRN-024 assesses the current full link; KRN-025 owns
compiler-runtime qualification. Neither is a crypto-provider implementation.
The local plans reproduce the retained KLINK-011/VCOMP-002 driver profile;
KRN-024's current-profile report is a separately hash-linked owner witness.

The current coherent982-object symbol-consumer graph has no reference to
`_corecrypto_kext_start` or `_corecrypto_kext_stop`. The public provider defines
those entry points, but this audit does not demonstrate archive-member
extraction or execution of its initializer. The static-kernel startup hook,
PRNG ownership and first-registration ordering must be explicitly qualified;
the compiler-support flag and an exported crypto start symbol establish
neither extraction nor execution of a crypto provider.

## Public provider research and licensing

Primary [Apple corecrypto](https://github.com/apple/corecrypto/tree/9612a959abb6eac0aac3ee6a7245c46365c9d81b)
is available at full SHA `9612a959abb6eac0aac3ee6a7245c46365c9d81b`, the
2026-05-22 release. Named commit/directory metadata, README, license and kext
registration source are pinned and hashed in ignored local research storage.
The [default license](https://github.com/apple/corecrypto/blob/9612a959abb6eac0aac3ee6a7245c46365c9d81b/License.txt)
limits its grant to90-day internal security/function evaluation, prohibits
redistribution, and requires prior written permission for other purposes.
Public source availability does not supply this project's integration rights.
No restricted implementation is compiled or committed. More permissive
Isabelle-library exceptions do not provide a kernel crypto provider grant.

The named public kext registration source assigns43 of the selected56 members.
It does not assign `ccdigest_final_fn`, five generic digest callbacks, or seven
generic HMAC callbacks. The selected direct-text scan finds no demand for
those13. Therefore this **does not prove binary incompatibility**, a compile
failure or an Apple ABI requirement that every field be populated. The audit's
deliberate full-table-coverage policy is conservative and explicitly separate
from actual profile requirements. Function/context/mode structures, target
options, ISA/DIT/PAC assumptions, current source age versus iOS16.5, imports,
startup/entropy integration and applicable use rights still need assessment.
This is a research candidate, not a qualified replacement archive. This audit
does not claim that no other licensed implementation exists.

## Reproduction and experiment history

Use the main registry for plans before running. Named source metadata can be
fetched explicitly into the owned ignored prefix; no provider build occurs:

```sh
python3 tools/research/corecrypto/audit.py --run fresh-audit --fetch-metadata
# Or use existing pinned named metadata offline:
python3 tools/research/corecrypto/audit.py --run fresh-offline-audit
```

`--root` selects the shared laboratory; `--metadata-root` selects an explicit
snapshot. Public metadata hashes are fixed in inputs.json; changed responses
fail rather than silently update provenance. The first larger commit-API
response was incomplete; its failure record is retained, and bounded Git
commit/directory endpoints replaced it. No full repository clone was required.
Every auditor subprocess now receives `GIT_NO_LAZY_FETCH=1` and
`GIT_OPTIONAL_LOCKS=0`, so missing objects fail rather than hydrating a shared
promisor checkout. A real missing-object negative exits128. Earlier reads and
CCPROV-001/002/003 lacked those flags; incidental shared-reference hydration
cannot be excluded retrospectively. No intentional shared fetch/checkout was
issued, and restricted public text was downloaded only into the owned prefix.

CCPROV-001 failed after a real successful layout compile because the auditor
hashed relative dependency names against its own cwd. Its failed source and
outputs are retained. CCPROV-002 resolves names against the exact recorded
compiler cwd and passes41 actual checks, with peak child RSS136460KiB. It
records99 genuine probe dependencies. CCPROV-003 replay is bound to
`e4e11be38ee3d41b233f58b8d4c9234c2af93e28`: all42 checks pass, with peak
child RSS160224KiB. CCPROV-004 is the final replay bound to the subsequent
Git-read guard commit: all43 checks pass, including29 negative controls,
with peak child RSS160140KiB. It hashes957 selected C/C++ sources scanned for
direct demand, verifies the maintained56-slot catalog, records79 demand
references and99 probe dependencies, and measures the startup-symbol inventory.
[qualified-audit.json](../../../fixtures/public/corecrypto-provider/qualified-audit.json)
links the exact existing evidence capsule and its immutable digest.
These historical capsules retain their original bytes and are superseded for
the cc_kext interpretation. [driver-correction.md](driver-correction.md)
plans the source-backed mapping check, real driver plans and correction replay.
The corrected final capsule is **CCPROV-007**, bound to
`5e7d3bb81bbb107f908738d93e86108892af16e6`:56 checks pass, including33 negative
controls, with peak child RSS160192KiB. Its plan registration precedes the
actual replay. The table/catalog is unchanged, and the driver source mapping,
actual backend omission, explicit forwarding and source-policy negatives are
additional evidence. CCPROV-006's56 checks also passed, but the pending plan
acquired the ledger lock2seconds after that audit began; its workflow deviation
is retained, and CCPROV-007 supplies the correctly planned final replay.

Controls change all21 actual zero-slot bytes individually and one active
relocation, alter a real source hash, remove the required library flag, compile
a deliberately incompatible RSA callback type, and reject candidate use rights
or incomplete conservative coverage. The genuine header positively matches
both RSA callback typedefs to their actual declarations. The two sequential
small compiler calls preserve the real target/config/includes and emit only
a measurement object or an expected signature failure. No algorithm KATs or
fake archive/providers are used. All source/tool/command/output hashes,
actual exits and resource measurements remain in the local evidence capsule.

## Concrete next gates

1. Supply an applicable provider source/build revision and rights for the
   intended use; preserve provenance and component notices. Public evaluation
   text is not a redistribution grant. Donor code also retains per-component
   provenance limits; a directory license is not a new blanket grant.
2. Define the selected required callback profile from real consumers, including
   externally used/private interfaces. Bind exact function signatures, nested
   descriptors/context sizes, alignment/ownership and PRNG/entropy interfaces
   to genuine provider target objects. Do not fill gaps with zero stubs.
3. Integrate one intentional startup/PRNG owner before consumers and reconcile
   the donor's EARLY_BOOT first registration. Prove archive-member extraction,
   initialization order, immutable table lifetime and proper failure handling.
4. Integrate a genuine crypto implementation under its actual chosen build
   artifact identity only when inputs/rights permit. Audit its members/imports
   and full selected link independently of compiler-runtime support. Preserve
   the native `-lcc_kext` request and assess its Darwin compiler-rt expansion;
   KRN-025 owns that separate support-library gate. KRN-024 and KRN-008 own
   full link/integration; KRN-004 retains private-ABI qualification.
5. Algorithm, side-channel, entropy, negative/error/lifecycle and runtime tests
   remain necessary after ABI/link qualification. Passing KATs, this source
   audit or a linked image cannot establish FIPS validation or native operation.

No phone was accessed. Full crypto, encrypted-volume/signature/network-security
coverage, FIPS, Apple interoperability, full kernel and native-device status
remain false. KRN-023's outcome is a repeatable bounded source/input/ABI audit.
