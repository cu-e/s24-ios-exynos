# AVFSOURCE-001: complete source composition and genuine guest configuration

Date: 2026-11-05. Task VM-007. Owner codex-team-avf-kernel-source-20261105-cc.

Stage exact public source at Scion a6f4bc38aa244359cd365c976244a88c9d6b3304,
XNU c54f35ca767986246321eb901baf8f5ff7923f6a and HFS
31d5ec238dfab485e78a9a30b8b92d13e8914f03 in owned caches/fresh outputs.
First inventory canonical Git trees and source requirements; never acquire
prebuilt OS/app/SDK/firmware payloads as a side effect of a broad donor archive.
Required source trees/scripts/overlays/drivers/layers and licenses must be
complete for the actual composition, with explicitly recorded exclusions for
non-source/non-build artifacts and full canonical tree metadata retained.

Use only explicit primary public acquisition into owned caches, streaming and
bounded. Every Git child disables lazy fetch and optional locks; shared
references/native/prepared trees remain immutable. Explicit own-cache fetches
are allowed; no silent shared promisor hydration, SDK/binary acquisition or
donor setup/installer/phone script execution.

Compose complete public XNU, pinned Scion base patch and full overlays/mapped
and selected-layer drivers, required HFS/core/encoding/patch inputs, then all34
ordered numbered patches. Verify actual full-tree applicability. Execute only
reviewed genuine source/configuration generation for an explicit ARM64,
DEVELOPMENT, BCM2837 profile; capture .config, driver selections and their
source-generated headers/MASTER outputs. Do not compile or claim full setup,
MIG/IIG/installed SDK headers, and do not reuse native E1S generated artifacts.

Bind input/archive/member/Git tree/blob and every composed output/config identity
in an immutable reusable manifest. Validate real wrong-source, missing-patch,
missing/mismatched-driver, changed-config/mixed-board/native-output reuse inputs;
retain failures and commands/exits/hashes. Source-only graph/manifest pass is
not a full kernel, ABI, crypto, header, link, guest or device result.

No compiler/fullbuild/link/QEMU/phone/MMIO/device or SDK acquisition. One source
operation at a time, finite stage deadlines/owned cleanup, streaming hashes and
bounded cache reads. Save scoped implementation/evidence/handoff; retain VM-007
in_progress for coordinator review. VM-008 owns the later coherent public
header/setup/MIG/IIG/representative-compile route.
