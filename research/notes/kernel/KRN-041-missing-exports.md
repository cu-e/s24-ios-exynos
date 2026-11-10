# KRN-041: the 37 missing kernel exports

Owner `claude-export-dossier-20261110-x41`, 2026-11-10. Evidence kind: host-test plus source review. Branch
`team/krn-041-missing-exports-20261110`, worktree `worktrees/krn-041-missing-exports-20261110`. Tool, patches and data:
`docs/procedures/krn-041/`. Measured run: `artifacts/krn-041/run-003/report.json` (experiment KRN041-002, 39 of 39 checks pass, tool
commit `7506b40735beac3cee6015dc9c7569d906a13305`). No kernel was booted and no device was used.

Sources: apple-xnu `c54f35ca767986246321eb901baf8f5ff7923f6a` (xnu-8796.121.2), HakiOS/Scion `a6f4bc38aa244359cd365c976244a88c9d6b3304`
(source id `scion-avf`, full tree in `references/hakios-scion-full`), HakiOS E1S tools `d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c`,
S24 port `c8860decc62c6d6180e609036d027a2997972420`. File:line references below are at these pins.

## Answer in brief

- Counts: 0 of the 37 need a real implementation for any kernel this project builds; 2 get source-backed stubs
  (`_pmap_has_iofilter_protected_write` returns false, `_pmap_cs_configuration` returns 0); 35 have no consumer and no public
  declaration and leave an opt-in export profile. For Apple's own kexts all 37 would need Apple's closed implementations; none is public.
- The only thing that references these names is the export list itself. In the STR-041 link no object, extra object or archive
  (1049 inputs) defines or references any of them. In KRN-024's RELEASE link, ld64 names `-exported_symbol[s_list] command line option`
  as the only referrer of each of the 37.
- Early boot to PID 1, guest and native: no effect. DEVELOPMENT arm64 does not pass the export list to the linker
  (`makedefs/MakeInc.def:819`), the kernel never reads the symbol-set plist at run time and arm64 has no runtime kext linker. What they
  do break is the build: the second `check_all_exports` pass and the Private symbol set, after the kernel is linked; and a RELEASE
  arm64 link, which fails outright (`makedefs/MakeInc.def:811-812`).
- In Apple's build these names can only come from the closed `lib<MACHINE>.os.<CONFIG>.a` that `makedefs/MakeInc.def:861-864`
  force-loads for T6000, T8101 and VMAPPLE. Every other machine configuration, including Apple's own public BCM2837, fails
  `check_all_exports` without it. That library was not inspected.
- HakiOS and the S24 port leave the lists unchanged and accept the `check_all_exports` failure (`make -k`). HakiOS's prebuilt guest kernel
  misses the same 37 plus 94 DriverKit/IIG names, which is a separate gap.

## What was changed and verified

- `0001-arm-pmap-unsupported-queries.patch` adds the two pmap queries to `osfmk/arm/pmap/pmap.c` next to
  `pmap_iofilter_protected_write()`, guarded to builds with no `XNU_MONITOR`, no `PMAP_CS` and no force-loaded closed library.
  Compiled under the exact STR-023 recipe (only source, object and depfile paths changed; the unpatched control compile has
  byte-identical `__TEXT,__text` and the same header set as the STR-023 object). Each stub is `mov w0, #0; ret`.
- `0002-no-apple-soc-library-exports.patch` removes the 35 from `config/Private.arm64.exports`. These are exactly the 35 lines the
  S24 port's legacy `0009-sweet-drop-apple-soc-only-exports.patch` removes from that file; 0009 also removed the two pmap names, which
  0001 implements instead. A guard rejects any removal of a name that is defined or referenced in a link input, declared in public XNU
  source or used by driver code; it rejects `_ml_static_ptovirt` and both pmap names as controls.
- A copy of the STR-041 kernel relinked with the patched `pmap.o` (only the filelist line and output changed) keeps the segment order
  and entry point, has no undefined symbol, and exports exactly the STR-041 set plus the two stubs.
- The genuine `SETUP/kextsymboltool` was built from c54f35ca for the host with HakiOS's Linux compatibility headers and run with the
  argument structure of `config/Makefile:120-134`:

| Kernel | Export lists | Pass without Private | Pass without Unsupported | Symbol sets |
|---|---|---|---|---|
| STR-041 | genuine | exit 0 | exit 1, 37 missing | Private fails (37), six pass |
| STR-041 | 0002 profile | exit 0 | exit 1, 2 missing (the pmap queries) | not run |
| relinked with 0001 | genuine | exit 0 | exit 1, 35 missing | not run |
| relinked with 0001 | 0002 profile | exit 0 | exit 0 | all seven pass |
| HakiOS prebuilt guest (`prebuilt/hakios-kernel`, SHA256 03e794e8...) | genuine | exit 1, 91 missing | exit 1, 131 missing (the 37 + 94 DriverKit) | not run |
| same | 0002 profile | exit 1, 91 missing | exit 1, 96 missing (2 pmap + 94 DriverKit) | not run |

- RELEASE-style link (the relinked object set plus `-exported_symbols_list`, as RELEASE arm64 does): with `all-kpi.exp` regenerated from
  the genuine lists (byte-identical to STR-041's) ld64 fails on exactly the 35, each referenced only from the export list; with the
  profile lists it links with no undefined symbol. These are DEVELOPMENT objects; this is not a RELEASE kernel.
- Host finding: on Linux `lseek()` on `/dev/null` returns 0, so kextsymboltool's `seekFile()` fails after the membership decision
  whenever the recipe's literal `-output /dev/null` is used. The tool writes to a scratch file instead; a control with `/dev/null` fails
  only with `couldn't write output` and no missing name. A Linux `make` build therefore cannot pass `check_all_exports` as written, even
  with complete exports. HakiOS's `tools/make-kernel.sh` accepts every `check_all_exports` failure, so it would also hide a real one.

Reproduce: `python3 -I docs/procedures/krn-041/missing_exports.py --run NEW_NAME [--guest-kernel PATH]` from the worktree (about 10 s,
peak child RSS about 300 MB). It writes only `artifacts/krn-041/NEW_NAME/`.

## Per-symbol table

Generated from `artifacts/krn-041/run-003/report.json` and `docs/procedures/krn-041/dossier.json`. "Apple-side consumer" is an
inference from names and public comments; no Apple kext was examined. Notes in brackets follow the table.

| # | Symbol | Signature | Export line | Consumers in our kernels | Apple-side consumer | Required implementation | ABI | Public source | Early boot: guest / native | HakiOS / S24 port |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `_pmap_has_iofilter_protected_write` | extern bool pmap_has_iofilter_protected_write(void) | config/Private.exports:776 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | kexts that write PPL-filtered MMIO registers; inferred [P1] | stub (0001): returns false | C, AAPCS64; bool in w0 | decl osfmk/vm/pmap.h:856; x86_64 body osfmk/x86_64/pmap.c:3419; arm64 none | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 2 | `_pmap_cs_configuration` | extern int pmap_cs_configuration(void) | config/Private.exports:780 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | code-signing clients reporting pmap_cs settings; inferred [P1] | stub (0001): returns 0 | C, AAPCS64; int in w0 | decl osfmk/vm/pmap.h:902; x86_64 body osfmk/x86_64/pmap.c:3405; arm64 none | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 3 | `_pmap_iommu_init` | no declaration; C symbol, type unknown | config/Private.arm64.exports:78 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 4 | `_pmap_iommu_iovmalloc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:79 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 5 | `_pmap_iommu_map` | no declaration; C symbol, type unknown | config/Private.arm64.exports:80 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 6 | `_pmap_iommu_unmap` | no declaration; C symbol, type unknown | config/Private.arm64.exports:81 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 7 | `_pmap_iommu_iovmfree` | no declaration; C symbol, type unknown | config/Private.arm64.exports:82 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 8 | `_pmap_iommu_ioctl` | no declaration; C symbol, type unknown | config/Private.arm64.exports:83 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 9 | `_pmap_iommu_alloc_contiguous_pages` | no declaration; C symbol, type unknown | config/Private.arm64.exports:84 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | PPL IOMMU clients (Apple DART/SART/NVMe/UAT kexts); inferred [P2] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public; pmap_iommu.c is a placeholder | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 10 | `_nvme_ppl_get_desc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:85 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | Apple NVMe (ANS) driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 11 | `_sart_get_desc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:86 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | Apple SART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 12 | `_t8020dart_get_desc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:87 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T8020 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 13 | `_t8020dart_vo_tte` | no declaration; C symbol, type unknown | config/Private.arm64.exports:88 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T8020 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 14 | `_t6000dart_get_desc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:89 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T6000 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 15 | `_t6000dart_vo_tte` | no declaration; C symbol, type unknown | config/Private.arm64.exports:90 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T6000 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 16 | `_t8110dart_get_desc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:91 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T8110 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 17 | `_t8110dart_max_translation_levels` | no declaration; C symbol, type unknown | config/Private.arm64.exports:92 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T8110 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown (function or data unknown) | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 18 | `_t8110dart_vo_tte` | no declaration; C symbol, type unknown | config/Private.arm64.exports:93 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T8110 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 19 | `_t8110dart_vo_tt_index` | no declaration; C symbol, type unknown | config/Private.arm64.exports:94 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | T8110 DART driver; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 20 | `_uat_get_desc` | no declaration; C symbol, type unknown | config/Private.arm64.exports:96 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT client; inferred [P3] | remove from profile (0002); Apple kexts would need the closed PPL IOMMU code | unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 21 | `__ZN26IOUnifiedAddressTranslator10gMetaClassE` | IOUnifiedAddressTranslator::gMetaClass | config/Private.arm64.exports:103 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | static data: IOUnifiedAddressTranslator::MetaClass object; size unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 22 | `__ZN26IOUnifiedAddressTranslator10superClassE` | IOUnifiedAddressTranslator::superClass | config/Private.arm64.exports:104 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | static data: const OSMetaClass * const; superclass unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 23 | `__ZN26IOUnifiedAddressTranslator17getPageTableEntryEy` | IOUnifiedAddressTranslator::getPageTableEntry(unsigned long long) | config/Private.arm64.exports:105 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 24 | `__ZN26IOUnifiedAddressTranslator18setClientContextIDEjb` | IOUnifiedAddressTranslator::setClientContextID(unsigned int, bool) | config/Private.arm64.exports:106 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 25 | `__ZN26IOUnifiedAddressTranslator21removeClientContextIDEv` | IOUnifiedAddressTranslator::removeClientContextID() | config/Private.arm64.exports:107 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 26 | `__ZN26IOUnifiedAddressTranslator19isPageFaultExpectedEyj` | IOUnifiedAddressTranslator::isPageFaultExpected(unsigned long long, unsigned int) | config/Private.arm64.exports:108 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 27 | `__ZN26IOUnifiedAddressTranslator22registerTaskForServiceEP4taskP9IOService` | IOUnifiedAddressTranslator::registerTaskForService(task*, IOService*) | config/Private.arm64.exports:109 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 28 | `__ZN26IOUnifiedAddressTranslator23createMappingInApertureEjP18IOMemoryDescriptorjym` | IOUnifiedAddressTranslator::createMappingInAperture(unsigned int, IOMemoryDescriptor*, unsigned int, unsigned long long, unsigned long) | config/Private.arm64.exports:110 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 29 | `__ZN26IOUnifiedAddressTranslator23getTotalPageTableMemoryEv` | IOUnifiedAddressTranslator::getTotalPageTableMemory() | config/Private.arm64.exports:111 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 30 | `__ZN26IOUnifiedAddressTranslator3mapEP11IOMemoryMapj` | IOUnifiedAddressTranslator::map(IOMemoryMap*, unsigned int) | config/Private.arm64.exports:112 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 31 | `__ZN26IOUnifiedAddressTranslator5doMapEP18IOMemoryDescriptoryyj` | IOUnifiedAddressTranslator::doMap(IOMemoryDescriptor*, unsigned long long, unsigned long long, unsigned int) | config/Private.arm64.exports:113 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 32 | `__ZN26IOUnifiedAddressTranslator5unmapEP11IOMemoryMap` | IOUnifiedAddressTranslator::unmap(IOMemoryMap*) | config/Private.arm64.exports:114 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 33 | `__ZN26IOUnifiedAddressTranslator7doUnmapEP18IOMemoryDescriptoryy` | IOUnifiedAddressTranslator::doUnmap(IOMemoryDescriptor*, unsigned long long, unsigned long long) | config/Private.arm64.exports:115 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 34 | `__ZN26IOUnifiedAddressTranslator8taskDiedEv` | IOUnifiedAddressTranslator::taskDied() | config/Private.arm64.exports:116 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 35 | `__ZN26IOUnifiedAddressTranslator12commitUnmapsEv` | IOUnifiedAddressTranslator::commitUnmaps() | config/Private.arm64.exports:117 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 36 | `__ZN26IOUnifiedAddressTranslator14prepareFWUnmapEyy` | IOUnifiedAddressTranslator::prepareFWUnmap(unsigned long long, unsigned long long) | config/Private.arm64.exports:118 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | non-const member function; parameter types from mangling; return type and virtual or not unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |
| 37 | `__ZTV26IOUnifiedAddressTranslator` | vtable for IOUnifiedAddressTranslator | config/Private.arm64.exports:119 | none: 0 definitions, 0 references in 1049 link inputs; RELEASE referrer: the export list only [C] | UAT clients, likely GPU or coprocessor kexts; inferred [P4] | remove from profile (0002); a stub class would invent an ABI | vtable; slot count and order unknown | none public | none / none [B] | kept, failure accepted / kept; legacy 0009 removed it [H] |

[C] Consumers in our kernels. `nm -A -g` over the 1042 objects of the STR-041 `link.filelist`, `version.o`, `lastkerneldataconst.o`,
`lastkernelconstructor.o`, `nonlto.o`, `libfirehose_kernel.a`, `libpthread_kext.a` and `libclang_rt.cc_kext_ios.a`. Scanner controls:
`_panic` is referenced by 467 inputs, `_ml_static_ptovirt` by 5. Code under project `src/`, HakiOS `drivers/`, `xnu/files/`, `avf/`,
`xnu-deps/iig-impl/`, S24-port `xnu/hackios/files/` and `shim/`, and lines added by project, HakiOS and S24-port patches, contain none of
the identifiers (for the class, `IOUnifiedAddressTranslator`). KRN-024 native-session2 (RELEASE link) lists only
`-exported_symbol[s_list] command line option` as referrer of each of the 37.

[B] Early boot. DEVELOPMENT arm64: the link does not use the export list (`makedefs/MakeInc.def:819`); `symbolsets.plist` goes into
`__LINKINFO,__symbolsets` (`makedefs/MakeInc.def:852`) for the host kernel-collection builder and no XNU source reads it; no arm64 or
x86_64 MASTER configuration enables `CONFIG_KXLD` (`config/MASTER:523`), so no kext can be linked at run time; nothing calls the names.
Effect on reaching PID 1: none, for (a) a QEMU/KVM guest built from the HakiOS BCM2837 base, whose `board_config.h` block defines no
`PMAP_CS`/`XNU_MONITOR` and which is not in the force-load list, and (b) the native E1S kernel. Measured for the native E1S image
(STR-041) and for HakiOS's prebuilt guest image; VM-002's own guest kernel did not exist yet. A RELEASE arm64 build is the exception: its
link fails until each name is defined or removed (`makedefs/MakeInc.def:811-812`).

[H] HakiOS: `tools/make-kernel.sh:7-24` runs `xnu-build.sh -k` and accepts only failures of the symbol-set and `check_all_exports` targets,
then requires the kernel file; `xnu/README.md:35-36`; HakiOS E1S tools `xnu/README.md:67-69` ("the error was there before any of our
changes"). S24 port, current E1S path: lists unchanged, build stops in `check_all_exports` after linking `mach.development.e1s`
(`xnu/hackios/README.md:38-40`, `xnu/e1s/README.md:298-301`, `docs/e1s-bringup.md:52-54`). Legacy SM7150 series:
`xnu/legacy-sweet-patches/0009-sweet-drop-apple-soc-only-exports.patch` removes all 37. Neither implements any of them.

[P1] `osfmk/vm/pmap.h:845-871` documents register-level MMIO filtering: support "determined by pmap_has_iofilter_protected_write()",
and `pmap_iofilter_protected_write()` panics on unsupported devices; this pmap's version does exactly that
(`osfmk/arm/pmap/pmap.c:12352-12357`). `osfmk/vm/pmap.h:891-902`: `pmap_cs_configuration()` returns 0 in the default configuration,
and 0 never means secure; the bit definitions it refers to are not public. `pexpert/pexpert/arm64/board_config.h` defines `PMAP_CS`
and `XNU_MONITOR` only for T6000, T8101 and T8103. The x86_64 bodies (`osfmk/x86_64/pmap.c:3405`, `:3419`) return the same values;
0001 does not rely on them.

[P2] `osfmk/arm/pmap/pmap_iommu.c` is a placeholder. The pmap keeps IOMMU hooks that nothing in public source sets: `PVH_FLAG_IOMMU`,
`PVH_FLAG_IOMMU_TABLE` and `pvh_ptep_is_iommu()` (`osfmk/arm/pmap/pmap_data.h:170-191`, `:449`); `tools/lldbmacros/pmap.py:825-844`
reads a `ppl_iommu_state` whose descriptor names its owner ("t8020dart/nvme_ppl/etc"). `osfmk/tests/pmap_tests.c:443`
`test_pmap_iommu_disconnect()` returns `KERN_SUCCESS` without a body. With no PPL in our builds and a Samsung SysMMU instead of a DART,
our drivers have no use for this interface.

[P3] Per-IOMMU PPL descriptors and translation helpers for Apple SoC blocks (DART generations T8020, T6000, T8110; SART; the NVMe
controller's PPL queue; UAT). `osfmk/conf/Makefile.template:326` sets a warning flag for a `t8020dart.o` that is not published. None of
this hardware exists on Exynos 2400 or in a QEMU/KVM guest.

[P4] The class is an OSMetaClass class (`libkern/libkern/c++/OSMetaClass.h:1842-1850`, `:2024-2028` define `gMetaClass` and
`superClass`); `__ZTV` is exported so that a kext subclass or the collection builder can patch against the vtable. The mangled names
give parameter types and show the methods are non-const; they do not give return types, the superclass, which methods are virtual, the
member layout, the vtable slot order or pointer-authentication diversifiers. No header, `.iig` or `.cpp` exists at the pin. Any stub
would invent that ABI, so the class is left out of the profile rather than stubbed.

## Integration notes

- Apply 0001 in source preparation for E1S and for the guest; it applies to upstream and, with an offset, to the HakiOS-derived native
  tree. Apply 0002 only for E1S and BCM2837 profiles, never for T6000, T8101 or VMAPPLE.
- With 0002, regenerate `all-kpi.exp` and `symbolsets.plist` from the profile lists. The relinked copy here keeps STR-041's
  `symbolsets.plist`, which still lists the 35, so it isolates the effect of 0001 only.
- To make `check_all_exports` meaningful on Linux, give kextsymboltool a regular `-output` file (or fix `seekFile()` for character
  devices) and stop accepting its failure wholesale.
- The guest needs the same two patches, and in addition its own fix for the 94 DriverKit/IIG names if it is built HakiOS's way.
- KRN-026 is not changed. Its blocked reason asks for provider implementations of all 37. This note shows that nothing in our kernels
  requires them; whether that resolves KRN-026 is for its owner and the coordinator.

## Not established

- The contents of Apple's `lib<MACHINE>.os.<CONFIG>.a`. `nm` of `libT8101.os.DEVELOPMENT.a` from a KDK would show which of the 37 it
  defines; it is an Apple binary and is neither available nor to be committed.
- Which Apple kexts use each name. The Apple-side consumer column is inference.
- A booted kernel with these changes, a guest built by VM-002, and a real RELEASE kernel (needs RELEASE-compiled objects).
