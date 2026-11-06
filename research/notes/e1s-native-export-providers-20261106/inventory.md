# Native E1S provider inventory, 2026-11-06

RES-010, owner `codex-platform-inventory-20261106-ip2`; source review at MAIN
`862b64a8`. The exact 37-symbol inventory and selected input digests are in
`inventory.json` and `source-bindings.json`. This reuses the existing KRN026
audit and KRN030 actual link, with targeted checks of the current native source;
it does not repeat their builds or full-tree searches.

**No compatible local implementation is established for any of the 37 exports.**
They are mandatory exports in the measured RELEASE configuration. KRN030's
genuine native link, including qualified compiler runtime, failed with exactly
these 37 export-option references, no new missing names and no image. Thus these
measurements identify no additional external library required by that particular
body graph. They neither prove reachability nor predict a fresh DEVELOPMENT
body's imports.

| Export family (all exact spellings in inventory.json) | Available local source/provider | Exact missing input |
| --- | --- | --- |
| IOUnifiedAddressTranslator: 14 methods, gMetaClass, superClass, vtable (17) | Export spellings only; KRN026 found no selected public declaration, IIG or implementation | Licensed/provenanced matching ARM64 class declaration, inheritance/layout/vtable and dispatch contract, real method/data definitions and dependencies. Mangled names do not provide return types or private ABI. |
| pmap_iommu_init/iovmalloc/map/unmap/iovmfree/ioctl/alloc_contiguous_pages (7) | Selected `osfmk/arm/pmap/pmap_iommu.c` is the same public placeholder already compiled without providers | Matching ARM64 implementations, actual allocation/mapping/cache/TLB/ownership/fault contracts and board integration. Recompiling this placeholder adds no bodies. |
| nvme_ppl_get_desc, sart_get_desc, uat_get_desc (3) | Required exports; no implementation established in the audited selected source | Genuine descriptor types, operations, ownership/security semantics and compatible implementation. Apple NVMe/SART/UAT interfaces cannot be inferred from symbol names or substituted with E1S UFS/GPU code. |
| t6000dart_get_desc/vo_tte; t8020dart_get_desc/vo_tte (4) | Required exports; no matching implementation established | Their exact Apple SoC DART descriptor/translation formats and implementation, or a separately reviewed source-backed platform contract. |
| t8110dart_get_desc/max_translation_levels/vo_tte/vo_tt_index (4) | Same unavailable provider boundary | Matching descriptor/translation geometry, lifecycle and implementation. No evidence identifies this Apple DART interface with Exynos hardware. |
| pmap_has_iofilter_protected_write, pmap_cs_configuration (2) | Genuine declarations in `osfmk/vm/pmap.h`; x86 implementations explicitly report unsupported; ARM `pmap_cs.c` is a placeholder | Real selected ARM64 capability/configuration semantics and implementation. Returning x86 false/zero would invent E1S security facts. |

The selected source pins are Apple XNU
[`c54f35ca767986246321eb901baf8f5ff7923f6a`](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a)
and S24 donor
[`c8860decc62c6d6180e609036d027a2997972420`](https://github.com/RNDMBG/iOS-On-S24/tree/c8860decc62c6d6180e609036d027a2997972420).
Primary source locations are `config/Private.arm64.exports:78–119`,
`config/Private.exports:776/780`, `osfmk/vm/pmap.h:856/902`,
`osfmk/x86_64/pmap.c:3405/3419` and the two ARM pmap placeholders.
Current STR004 files retain the audited placeholder bytes. STR014 changes only
six other translation units; it supplies no provider for these exports.

## Native body and private ABI boundaries

For RELEASE export compatibility, all 37 remain open; KRN026's original blocked
owner is untouched. For a first native DEVELOPMENT body diagnostic, none of
these 37 is established as a missing body-provider prerequisite by the retained
RELEASE result. The genuine `makedefs/MakeInc.def:812–820` populates the RELEASE
export-list link flag and leaves its DEVELOPMENT counterpart empty. This is
the upstream configuration rule, not permission to delete exports: DEVELOPMENT
still requires `all-kpi.exp`, aliases and symbolsets (`:849–855`), and the
configuration export/symbolset checks retain their authority.

Native E1S execution still needs real page tables/CPU entry/RAM/interrupt/console
and eventual device DMA isolation. A future E1S DMA implementation must follow
the matching Exynos hardware and XNU ownership/security contracts. There is no
source evidence here making any Apple DART/SART/UAT/NVMe symbol an early E1S
runtime requirement, nor evidence that those runtime/security contracts are
already satisfied. Fresh body/link and later runtime measurements must decide
their actual demands. Private Apple consumer compatibility additionally needs
the unavailable typed ABI above.

## Smallest next work, reusing existing inputs

1. Consume the already prepared STR014 six-port derivative explicitly. Do not
   repeat the body plan's now-completed source-port application or edit STR004.
   Keep STR009 configurations, STR010 syscall/STR012 version products, and exact
   STR011 generated-producer contracts. STR013's actual compiler probe exited 1
   on unsupported `-fbounds-attributes`; its accepted receipt `01d70064…` selects
   the genuine Make `BOUND_CHECKS=0` branch (CM review `f78e2a94…`). Do not rerun
   the probe. Its separate assym `-S` attempt failed for the missing mandatory
   sanitizer ignorelist, so no offsets exist yet. Supply that genuine recipe
   input, then finish assym and actual STR015 MIG generation under their owners.
   This missing generation input is distinct from the 37 private providers.
2. Finish the fresh DEVELOPMENT graph/header/layout closure and actual selected
   IIG outputs. Preserve all component and direct-tail recipes/filelist order,
   sanitizer ignorelist, aliases and symbolsets. Old 982 RELEASE objects and
   guest BCM2837 objects receive no DEVELOPMENT qualification.
3. Reuse compiler `7972eb28…`, native ld/libtool and the source-qualified
   compiler-rt archive `67304a15…` through Clang's `-lcc_kext` translation and
   explicit **link-only** resource root. That archive is compiler support,
   not corecrypto. Rebuild genuine Firehose `a641558f447659d90ad002ef0ee6f0212273fbfc`
   one-TU and pthread `a6c70ca0e544347a0377babf748f831577ec24f9` three-TU
   providers in the new DEVELOPMENT context, or separately prove old-byte
   compatibility. Existing native archives are inputs to that assessment;
   successful guest archives do not establish native layout compatibility.
4. After source/header/graph acceptance and a separate root grant, run the first
   bounded genuine DEVELOPMENT body-link diagnostic. Act on its actual missing
   references. A speculative crypto archive or all 37 unavailable Apple private
   providers is not a supported prerequisite for that diagnostic. If the new
   body actually requests one, open a narrowly typed implementation/input task;
   preserve the error rather than invent a body or suppress an export.

Corecrypto table/callback completeness, KATs, private ABI and actual native
hardware/recovery remain separate. No SDK/Apple binary, compiler, generator,
linker, device action or common check was used for this inventory. This report
does not qualify an image, boot or runtime.
