# CCPROV-005: distinguish compiler support from crypto provider

2026-11-05. Same KRN-023 owner and owned paths. This correction supersedes the
CCPROV-001 through004 interpretation of `-lcc_kext` as a crypto provider.
Their56-slot/21-unsupported measurements remain valid independent observations.

1. Pin and hash exact selected Clang Driver.cpp, ToolChain.cpp and Darwin.cpp
   at xnu-tapi revision fa9443738c1a18accef4244732ec6d6ee97a8133; compare with
   actual retained compiler-source lineage. Preserve Git no-lazy-fetch guards.
2. Assert the unconditional user-flag rewrite and Darwin compiler-rt resource
   selection/existence gate. Execute genuine existing Clang `-###` using the
   preserved selected full-link arguments and inspect the backend arguments.
   Measure current resource directory and runtime path without building it.
3. Execute a plan with explicit `-Xlinker -lcc_kext` as a forwarding control,
   without invoking ld64 or creating any fake archive/provider. Reject altered
   rewrite, runtime name/existence policy and crypto-identity assertions.
4. Remove the irrelevant libcc_kext search-directory inference. Retain the
   native input flag as a compiler-support provenance fact, separately from
   crypto callback/provider/init/rights qualification. Correct next gates and
   maintained summary; preserve superseded historical evidence unchanged.
5. Replay the bounded source/table/type audit with fresh evidence after the
   narrow correction commit; record exact source/tool/commit/commands/exits,
   existing artifact hashes and handoff. Retain in_progress for coordinator.

No phone, ADB, root, MMIO, flash, emulator, compiler-runtime/provider build,
global installation or shared-reference fetch. Only sequential small layout/
signature compilers and driver plans, commands <=45seconds and RSS <1GiB.
