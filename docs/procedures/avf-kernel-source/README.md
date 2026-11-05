# VM-007: complete AVF XNU source and genuine configuration inputs

Date: 2026-11-05. Owner `codex-team-avf-kernel-source-20261105-cc`.
Branch/worktree `team/vm-007-20261105`, `worktrees/vm-007-20261105`.

Complete exact-pin guest source composition succeeds, including genuine HFS,
all mapped/layer inputs and actual full-tree applicability of all34 numbered
Scion patches. Both the baseline defconfig and the checked-in QEMU alternative
produce genuine checked .config/driver-selector/header inputs. **No compiler,
full header/setup/MIG/IIG route, full kernel build/link or guest was executed.**
VM-008 owns the next coherent header and representative-compile investigation.
Native E1S artifacts/features/exports and VM-002/KRN-026 ownership stay unchanged.

## Source identity and exclusions

| Input | Full commit | Canonical root Git tree | Materialized source |
| --- | --- | --- | --- |
| Scion AVF | `a6f4bc38aa244359cd365c976244a88c9d6b3304` | `220950a71b0fb70ac72cfb808d2d0201d083273a` | 979 files, 15,607,790 bytes |
| Public XNU8796.121.2 | `c54f35ca767986246321eb901baf8f5ff7923f6a` | `5ddd2a3ca101a2c644216c024fe4721b75808fad` | All4995 files, 70,366,487 bytes |
| Required public HFS | `31d5ec238dfab485e78a9a30b8b92d13e8914f03` | `52df595b48f607b79411a766b2f0d8b13acca8b9` | All70 genuine core/encoding list members plus2 root license/README files, 2,594,309 bytes |

Primary repositories are [Scion](https://github.com/Scion-Project/hackios-xnu-kernel/tree/a6f4bc38aa244359cd365c976244a88c9d6b3304),
[Apple public XNU](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a)
and [Apple public HFS](https://github.com/apple-oss-distributions/hfs/tree/31d5ec238dfab485e78a9a30b8b92d13e8914f03).
[`inputs.json`](../../../fixtures/public/avf-kernel-source/inputs.json) binds the
immutable acquisition manifest, complete canonical tree metadata, exclusions,
input roots and ordered patch list. [`qualified-source.json`](../../../fixtures/public/avf-kernel-source/qualified-source.json)
binds the final composed manifest, both output trees and actual configs. Complete
source caches refuse reopening for acquisition; verification uses a fresh output.

Scion's canonical tree has999 files. Exactly20 prebuilt kernel/loader/userland
executables/dylibs were excluded **before content acquisition**; prebuilt notices
and checksum metadata remain. No broad donor archive downloaded those binaries.
HFS's full373-member canonical tree is retained as metadata; only its exact
required lists plus root license/README are materialized, and301 unrelated
members are explicitly excluded. Required source closure is complete, not an
assertion that unrelated HFS tests/assets or prebuilt binaries were copied.
The complete Git root is independently reconstructed from all canonical member
IDs, including excluded metadata, without acquiring excluded binary contents.
Materialized files are bound individually by Git blob ID, SHA256, size and mode.
The final guard also checks that all20 excluded prebuilt object IDs are absent
from both owned CAS and the owned Git promisor cache; the metadata fetch did not
hydrate those binaries.
No executable ELF/MachO/PE magic was found in the materialized source inspection.

Existing public Git blobs are read-only streamed into owned CAS storage. Missing
source blobs use explicit exact-pin/explicit-blob fetches into owned partial Git
caches; shared promisor stores never hydrate. All Git commands disable lazy
fetch and optional locks; hooks are disabled on owned Git operations. Fixed-size
streaming avoids collecting the full source/archive in memory. All modes and
source/license bytes are preserved. There is no SDK, firmware or binary payload
acquisition, donor installer/phone script, global install or device operation.

## Full composition, not a subset

The implementation follows the actual pinned xnu/apply.sh order in fresh owned
storage, without running its fetch/installer paths:

1. Copy all4995 public XNU files and actually check/apply Scion's base patch.
2. Copy **all103** source overlay files from xnu/files.
3. Copy all70 source files named by genuine HFS core/encoding lists and actually
   check/apply hfs.patch at the exact HFS pin.
4. Copy all102 drivers/map entries to their actual kernel destinations.
5. Execute the reviewed genuine `hakios-config.py external-files` on complete
   pinned source/layers. The checked-in qemu device.conf layer is present; it
   contributes no additional driver-file mapping. No external device repository
   is silently fetched from devices/manifest.conf.
6. Actually `git apply --check` and `git apply` **every34 ordered numbered patch**
   across the complete prepared tree, rather than VM-006's14-file subset.

This produces5271 common source files. Both subsequent config/driver generations
produce5273 source/input files: the two new driver header/MASTER files plus the
actual BSD/IOKit conf changes. The original public Private.exports and
Private.arm64.exports bytes are unchanged; native37 requirements are not pruned.
Canonical actual output Git trees are generated from owned source bytes, checked
against an independent full-file/mode/blob snapshot, not inferred from filenames.
Original source snapshots are revalidated after composition. Shared reference
working-source/index and accepted native/component parent witnesses are compared
before/after the final run; no old source tree or artifact is a writable output.

## Two genuine profiles, one shared source lineage

Architecture/board defaults are bound to unchanged genuine xnu-build.sh:
ARM64 / DEVELOPMENT / BCM2837, BUILD_LTO=0, DO_CTFMERGE=0. Future execution must
set MACHINE=BCM2837 explicitly. This task runs the source .config/driver
configurator, not make/doconf or compiler-generated board/header recipes.

| Fact | Baseline `defconfig` | Genuine device `qemu` defconfig |
| --- | --- | --- |
| Source config | configs/defconfig | devices/qemu/configs/qemu_defconfig; includes common_defconfig, open.config, virt.config |
| Driver count | 44 | 8 |
| CONFIG_DEVICE | Empty | qemu |
| Phone firmware request | None | None |
| Runtime arguments reported by source | Captured in actual-profile-show log | virtio_net=1 |
| Compiled source/header effects | Actual MASTER.hakios, hakios.drivers.h and BSD/IOKit conf inputs | Same four genuine output kinds with narrower selectors |

QEMU's eight selected drivers are `virtio_sound exynos_spi virtio_input
virtio_net exynos_poweroff ufs virtio_blk wifi_sta`. It removes36 of the
baseline's44 selected drivers through a **checked-in source profile**. No source
file or native export is deleted to obtain that result. It still retains Exynos
SPI, Exynos poweroff, UFS and WiFi-station surfaces; it is not declared an
exclusively virtual or proven compatible kernel. Source poweroff has a halt_off
boot-argument gate; no physical register access was executed or authorized.
Standard/common source and libraries such as HFS/APFS/mockfs/crypto are not
removed by these optional driver selectors. Real setup/header/provider/import
requirements must still be measured in VM-008.

The QEMU alternative is the more focused source-supported candidate for AVF plus
an owned PID1: it excludes36 phone-specific driver selections while retaining
virtual I/O paths. Baseline remains a separately captured reference. **VM-008
must explicitly choose and qualify a descriptor; this task does not silently
replace the selected baseline or claim boot compatibility.** The config profile
does not itself prove that raw PID1, PSCI exit, timer/UART or guest kernel works.

Genuine configuration commands set the documented HAKIOS_VERSION_SUFFIX to
`-ga6f4bc38-source`. This yields the actually reported version
`2.1.13-hakios-darwin22.5-ga6f4bc38-source` and prevents kernel-version.py from
walking into a containing repository and running its `git update-index` path.
GIT_CEILING_DIRECTORIES also bounds discovery. This is an explicit reproducible
source version override, not a claim of a clean binary build. Donor source bytes
are unchanged beyond each owned .config; native/shared source stays read-only.

## Failures and controls

The first acquisition retained a real Git delta/Out-of-memory diagnostic under
a 256MiB virtual-address limit. Git's default pack mmap/cache policy was the
issue: process-local packedGitWindowSize=1m, packedGitLimit=16m and
deltaBaseCacheLimit=4m allowed all4995 unchanged XNU blobs to stream. No shared
pack was repaired or rewritten, and a diagnostic saying "corrupt" after malloc
failure is not treated as proof of actual pack corruption. The successful full
blob/hash replay is independent evidence. This task retains the original failure.

The initial compose guard falsely compared Path-component ordering with string
path ordering; source dictionaries were byte-identical. That failed run remains
saved. The corrected snapshot uses one explicit path order, and the actual
full-tree composition succeeds. Negative controls use real wrong/missing source,
patch, mapped-driver and config inputs plus mixed-board/RELEASE/native-output
reuse profiles. They do not change accepted original/source/output trees.

The final full-source composition at `ed9fdbf01497e3721a33839bfe2b0d35897e5247` passed100 bounded commands,
eight negative controls and20 actual absent-prebuilt-object probes. Sampled
owned RSS peaked at61.3828125MiB, under256MiB. The immutable reusable descriptor
and complete-cache reopen rejection receive a separate commit-bound verify run
with nine negative controls. Evidence will bind both exact runs, commands/exits,
source/output/config/parent identities and retained failures.
Main common checks and acceptance remain coordinator review steps. Stay source
only: no compiler/header-route/fullbuild/link/QEMU/phone/MMIO, private Apple ABI,
SDK equivalence, native operation or XNU/PID1/boot claim.

## VM-008 handoff and read-only verification

The reusable descriptor records both full source roots/configs:

- Common source tree `188f23441033a5c673367a24b35814289a57a75e`.
- Baseline tree `9eac2aced3b5388e64f35f4466bbdbfae4da5eea`, .config SHA256
  `956fcf04bfb38242017c6515db7ae6844067fd1fc5fcd140c2685604160c91a0`.
- QEMU tree `6a955269a8f4e17d21239f75cef9fbe66cffc56c`, .config SHA256
  `1571c785ae12ed79858fb9c81ebfce4ecd5414e4ce6af906820f6b9d61f68394`.

These outputs and originals are frozen by content/mode/Git identity manifests.
Copy a chosen source/config into a **new VM-008-owned** preparation area before
any setup/header generation. Do not regenerate in these published trees, reuse
E1S objects/headers/archives, run donor installers, use allocator fallback or
emit empty IIG implementations as a substitute for genuine inputs. Actual full
public-header namespace/MIG/IIG/representative compile remains VM-008 work.
VM-002 still needs a complete qualified actual XNU image and real owned PID1/
stop execution; this source result does not satisfy that acceptance.

Read-only component verification from MAIN after integration, fresh output:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/build/avf_kernel_source.py verify \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --cache /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-007-20261105/artifacts/avf-kernel-source/cache \
  --stage /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-007-20261105/artifacts/avf-kernel-source/compose-final-ed9fdbf \
  --out artifacts/avf-kernel-source/NEW-verify
```

Final descriptor/API verification at `01fe7a189583ccc12cbd4a824a7a0a53c1c30aef`
passed8 read-only child commands, nine negative controls and20 excluded-object
checks; sampled owned RSS peaked at53.61328125MiB. No source regeneration occurred.
All shared/native parent witnesses match the full composition run. All source
runs use one owned process session at a time, per-child256MiB address-space and
sampled aggregate RSS limits and finite120/180/240-second stage deadlines with
owned cleanup. These are sampled peaks, not continuous-memory proofs. The first
failed short pack read had no resource sample; its0 field is not zero-memory
usage. No swap/cache/global-process action or heavy build lease is used.

Only authored tooling/docs and sanitized source/provenance metadata are committed.
Source and complete component license notices remain together in owned artifacts:
Scion MIT loader/tools and APSL kernel derivatives, public XNU/HFS APSL/per-file
notices and third-party notices. No blanket license replaces individual notices.

Final measurements and the 81118-artifact index are bound by
[`evidence.json`](evidence.json). Qualified source counts and canonical descriptors
are source-only; the next native/header/kernel/guest gates remain explicit.
