# VM-006: genuine AVF XNU source and build profile

Date: 2026-11-05. Owner `codex-team-avf-kernel-profile-20261105-bw`.
Branch/worktree `team/vm-006-20261105`, `worktrees/vm-006-20261105`.

The pinned AVF guest has a source-supported **ARM64 / DEVELOPMENT / BCM2837**
profile. Its genuine MakeInc link-variable expansion omits the **RELEASE-only**
forced `all-kpi.exp` export list. The preserved native E1S command actually uses
that list and remains blocked on its 37 missing exports. This source distinction
supports a separate coherent guest build investigation; it neither changes the
native requirements nor proves the guest has no unresolved references.

No complete kernel was built, linked or booted by VM-006. VM-002 remains blocked
on a qualified actual XNU image and execution. No compiler, QEMU, phone, ADB,
MMIO, firmware, SDK/binary acquisition or global installation occurs here.

## Exact inputs and measured source composition

[`inputs.json`](../../../fixtures/public/avf-kernel-profile/inputs.json) fixes
116 named files with full Git blob IDs, SHA256 and extents:

| Source | Full revision | Role |
| --- | --- | --- |
| [Scion AVF](https://github.com/Scion-Project/hackios-xnu-kernel/tree/a6f4bc38aa244359cd365c976244a88c9d6b3304) | `a6f4bc38aa244359cd365c976244a88c9d6b3304` | Actual build scripts/configuration, overlays, 34 ordered numbered patches, shim, source dependency/tool adapters |
| [Public XNU8796.121.2](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a) | `c54f35ca767986246321eb901baf8f5ff7923f6a` | Base MakeInc/MASTER/board/initialization/mockfs and unchanged native export declarations |
| [E1S donor](https://github.com/RNDMBG/iOS-On-S24/tree/c8860decc62c6d6180e609036d027a2997972420) | `c8860decc62c6d6180e609036d027a2997972420` | Independent native source preparation, machine config, loader/DT/GIC and return path |

The verifier rechecks actual Git tree entries at those fixed commits and every
owned-cache blob/content identity. Every Git child sets `GIT_NO_LAZY_FETCH=1`
and `GIT_OPTIONAL_LOCKS=0`; absent objects are never hydrated into references.
Missing public text was explicitly fetched into the owned cache and verified
before reuse. Failed HTTP, absent guessed paths and one rejected blob response
are retained in acquisition journals; later complete acquisition is separate.

An owned subset receives the genuine base patch, selected overlay files and
all 34 ordered numbered patches through actual `git apply`. The subset is
**14 named board/config/initialization/mockfs/interrupt/console/exit files**.
Successful subset application is not a claim that every patch applies to a
complete kernel tree. The graph records unreviewed full overlay/driver/HFS/IIG
subtrees by exact Git tree ID and preserves that remaining full-preparation gate.

The real composed MakeInc ARM64 link-variable fragment is extracted unchanged.
GNU Make expands it for DEVELOPMENT and RELEASE without executing kernel build
recipes. DEVELOPMENT has alias and symbolset inputs but no forced export-list
flag; RELEASE adds `-exported_symbols_list,OWNED_PROFILE_TARGET/all-kpi.exp`.
The base patch and all numbered patches are accounted for before this oracle.
No flag is deleted by a fabricated build wrapper. Symbolset generation and
`check_all_exports` can still fail: Scion's `tools/make-kernel.sh` judges those
post-link failures only after requiring a real kernel file. That policy is not
an image/link pass here.

The actual native KRN-030 report, 37-name source mappings, compiler/linker/runtime
and two accepted public header-component manifests are hashed before/after
review. None is edited. Source graph, per-fact line/hash bindings, real commands
and Make output are in the retained report. Eight controls reject wrong pin,
missing actual PSCI input, changed real build selector, mixed E1S board, reuse of
E1S objects, false SDK-free stock route, false build-ready status and pruned
native export contract.

## Guest versus native requirements

| Requirement | Actual AVF guest source | Preserved native E1S source |
| --- | --- | --- |
| Build selector | `xnu-build.sh`: DEVELOPMENT/BCM2837, ARM64, BUILD_LTO=0, DO_CTFMERGE=0 | Independent E1S machine patch and existing qualified native command; do not substitute guest selection |
| Source preparation | Public XNU + `hakios.patch` + `xnu/files` + mapped/layer drivers + HFS + every numbered patch | Public XNU + embedded `redwood.patch`/files + ordered E1S patches; separate provenance |
| Boot/DT | AVF Image enters EL1 from FDT, constructs Apple DT/bootargs/DRAM/GIC/UART/chosen PSCI | Native loader checks EL1, rebases supplied Apple DT/DRAM/ramdisk/boot CPU and framebuffer/log regions |
| Interrupt/timer | Composed BCM2837 defines generic GIC, ARM architected timer; GIC source routes virtual timer INTID27 | E1S macro also selects generic GIC/timer/PSCI support; native loader declares GICD `0x10200000`, GICR `0x10240000`, which are source facts, not MMIO measurements |
| Console | VMAPPLE_UART/PL011 for QEMU; patch1000 supplies byte-wide NS16550 for AVF; addresses from translated FDT | Native loader framebuffer/reserved log path is distinct; this task does not qualify a working E1S physical UART |
| Text/link | ARM64 image base `0xfffffff007004000`, prelink base `0xfffffff004004000`; shim requires text at least +48MiB from virtual window base `0xfffffff004000000` | Existing native layout/export command stays byte-preserved; no guest object/archive may be substituted |
| Root executable | Genuine MOCKFS option/files and raw-executable mount backend; shim appends `rd=md0` for a nonempty ramdisk unless overridden | Mockfs exists in E1S source too; actual native root/media/boot remains unqualified |
| Stop | Patch1001: no-loader halt/panic calls PSCI SYSTEM_OFF; reset calls SYSTEM_RESET; `/chosen/psci-method` chooses HVC/SMC; `avf_exit=0` opts out | Native loader-return source/reservations remain distinct; no Android recovery/physical stop guarantee follows |
| Export-only names | Default DEVELOPMENT omits RELEASE forced export enforcement; actual guest undefined/provider closure remains unmeasured | Actual native full-link failure diagnoses 37 preserved required exports; KRN-026 remains owned/blocked |

## SDK, headers and reusable components

The stock donor setup route explicitly requires `$THEOS/sdks/iPhoneOS16.5.sdk/usr/include`
and copies pre-generated DriverKit headers from MacOSX13.3 Kernel.framework.
Its IIG shim fails on a missing header and otherwise can emit an empty
implementation TU. The compiler wrapper invokes `/usr/bin/clang`, suppresses
warnings and includes a constant allocator-signature fallback when genuine
builtins are absent. These are exact upstream route facts, not selected private
ABI qualification and not proof that all public-source preparation routes need
an SDK. This task neither runs that installer nor acquires those inputs.

The project already has a source-qualified public installed-header subset,
public Availability/TargetConditionals inputs and matched compiler resource
recipes. The pthread component documents 1,794 installed entries, 36 native
filtered-empty entries and **76 unavailable generated inputs**; it is not a
complete SDK. The matched ARM resources are compiler headers, not SDK headers.
Their source/recipes can be considered for a fresh guest header route. Existing
E1S generated board/MIG/IIG/include products cannot certify guest compatibility.

Reusable candidates, bound by accepted manifests and measured hashes:

- Custom compiler `artifacts/xnu-compiler-cxx-storage/source-build-session2/clang`,
  SHA256 `7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82`;
  real allocator builtins must stay enabled in the guest profile.
- Source-built ld64 `artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld`,
  SHA256 `f3cab070fef2c3fb39687e31bab86193f34ab95215fc4dbc8783f2a4f741563e`.
- Qualified board-independent cc_kext archive SHA256
  `67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5`,
  plus its descriptor and **link-only** resource root from KRN-025. This is not
  corecrypto or a compile-header resource root; full member behavior is not qualified.
- Accepted public header installation/resource-generation recipes and genuine
  pinned pthread/firehose source, with their existing component limitations.

Rebuild all guest configuration/doconf/setup/MIG/assembly/generated IIG products,
objects, filelists, alias/symbolsets/layout/version metadata and the pthread/
firehose libraries against coherent guest exported/installed headers. Preserve
native source/features/exports and all prior object/library artifacts. No E1S
compiled object or board-sensitive archive is admitted as an AVF object.

## Next work and reproduction

[`next-build.md`](next-build.md) specifies the gated preparation/build sequence.
First stage the complete pinned donor/public sources in fresh owned storage and
regenerate guest headers using qualified public recipes; measure exact remaining
inputs instead of assuming the upstream SDK installer is the only route. The
stock SDK/IIG route remains unavailable as supplied, and a replacement public
header/tool route is not yet qualified for the complete guest. Full guest
object/reference/link/image/mockfs/PSCI execution remains future measured work.

Reproduce only the bounded source review, with a fresh output directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/research/avf-kernel-profile/verify.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --cache /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-006-20261105/artifacts/avf-kernel-profile/source \
  --out artifacts/avf-kernel-profile/NEW-review
```

Acquisition uses `source.py` and an explicit named request list; never run donor
setup/phone scripts to obtain missing inputs. Evidence and artifact index will
bind the final tested implementation commit and exact existing output paths.
All commands have 20-second deadlines and owned-session cleanup; measured source
checks use a 256MiB address-space/session RSS budget, no compiler/build/guest.
Final acceptance and common repository checks belong to coordinator review.

Scion root license covers loader/tools with MIT and kernel derivatives APSL2;
XNU retains APSL/per-file notices. E1S loader files retain GPL2-only notices and
embedded HakiOS its own notices; no blanket E1S additions license is inferred.
Only independently authored tooling/docs and provenance metadata are committed;
upstream source and license bytes remain together in the local source cache.
