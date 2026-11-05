# KRN-031 integration experiment plan —2026-11-05

Owner codex-team-kernel-xts-20261105-br, branch team/krn-031-20261105.
Original accepted KRN-029 is done; its adapter/vendor/suite/runtime stay unchanged.
Bind actual XNU c54f35ca767986246321eb901baf8f5ff7923f6a and selected donor
c8860decc62c6d6180e609036d027a2997972420, APSL/donor/Mbed component notices,
KRN029 exact source/layout/CPU capsule, KRN030 genuine runtime/native graph.
No restricted Apple corecrypto implementation is reused.

Interfaces before implementation: kernel_provider.c/h will expose two genuine
const ccmode_xts objects, const getters and one once-only prepare call. Typed
forwarders invoke real private accepted adapter modes after acquire-ready checks.
Public608/48-byte metadata is tied to actual selected declarations and checked
against BOTH actual private factory outputs before release publication. Idempotent
prepare is safe; in-progress/failed preparation cannot expose modes. No context
or function-pointer ABI casts. No registration occurs inside the helper.

Fresh copied mc_provider receives two static const-descriptor slot references
and prepare-before-register; retain all34 original relocated slots and deferred
SHA256 assignment. Fresh copied actual XNU AES-XTS caller maps NULL returned by
xts callback to genuine CCERR error status without signature changes. Preserve
all other actual native features, exports, compile profiles and existing ports.

Before execution register KXTS-001. Verify all accepted parent/source/tool hashes,
apply exact source patches only in fresh owned outputs, compile actual native
provider/caller/adapter/AES/helper TUs one at a time<=256MiB RSS. Inspect actual
56-field448-byte table layout, exactly two new relocations, original34 retained,
deferred SHA256, remaining19 unsupported slots, imports/provider closure and
unchanged unrelated982 graph/dependency/export/feature inputs. Publish coherent
replacement/additional-component manifests, not a full kernel image.

Use real wrapper positives and rejection/error-propagation controls, plus actual
prepare/publication/size/factory mismatch controls. Native ARM caller execution
requires explicit coordinator exclusive256MiB guest grant before any QEMU run.
Existing accepted shim/QEMU/runtime helpers remain immutable; any new mapping
or test fixtures are owned synthetic support, never kernel/provider stubs. Guest
<=512MiB owned RSS with finite session cleanup. No full native relink, heavybuild,
phone, global install or shared-reference/artifact mutation. Enforce MemAvailable
>=4GiB and root aggregate<=2GiB scheduling. Record raw commands/exits/times,
source/tool/commit/artifact hashes and actual limits; preserve failures.
Full crypto, remaining private ARM exports, Apple private ABI, full kernel and
native device operation remain unqualified. Retain in_progress for review.
