# Full E1S kernel prerequisite gate

BLD-001 built the freestanding loaders and applied the full E1S source delta. It did not compile XNU. KRN-001 owns the full kernel/dependency build.

```sh
python3 tools/build/kernel_preflight.py
# Only when these local inputs actually exist:
python3 tools/build/kernel_preflight.py --sdk /path/to/iPhoneOS16.5.sdk \
  --dependency-tools /path/to/pinned/hakios-build-tools
```

The initial check reports no configured SDK or dependency tool directory and exits 2. This is a concrete missing build input, not proof that no SDK exists anywhere on the machine. Do not download Apple SDK/userland/firmware automatically, substitute a different OS profile or report source patch application as a kernel compile. SDK presence still needs provenance and tool ABI review. Preserve any check_all_exports failure; a linked Mach-O alone does not satisfy full-build acceptance.

## Reassessment of 2026-11-10 (KRN-001, `claude-takeover-20261110-6c8f`)

The blocked reason above (no iPhoneOS16.5 SDK) is no longer what stops KRN-001. The current state of each acceptance item:

1. **SDK/dependency provenance and exact toolchain.** No Apple SDK is needed for the kernel itself. The STR-041 native DEVELOPMENT link passes `-L` only to empty `unavailable-sdk/usr/local/lib/kernel{,/platform}` directories (`docs/procedures/e1s-native-link-image/plan-001/plan.json`). Its three archives (`libfirehose_kernel.a`, `libpthread_kext.a`, cc_kext) were built from pinned open source in STR-018. Driver, clang, ld and setsegname tuples are recorded in that plan and in `docs/procedures/e1s-native-link-image/evidence.json`. `kernel_preflight.py` still checks only for an SDK, so its exit 2 is historical and does not measure this route.
2. **Full E1S build including exports.** The 1042-body image is linked: SHA-256 `4c9536d8…595f`, 0 undefined symbols; STR-037 rechecked it on 2026-11-10. KRN-041 retained precise failure evidence: with the genuine lists, check_all_exports misses exactly 37 names. With `0001` and `0002`, a relinked test copy passes both check_all_exports passes and all seven symbol sets. KRN-042 reproduced this from main with identical machine code. **Open:** no build tool applies 0001/0002 yet, so the canonical image is not the export-checked one.
3. **Kernel/payload/ADT validated separately from the freestanding loader.** The kernel is validated (two independent Mach-O parsers). **Open:** the payload (`SWEETXNU`: kernel, ADT and ramdisk for the S24-port loader) and the E1S ADT are not. The upstream `mkadt.py` needs the D22AP `/product` tree, which `fetch_d22ap.py` downloads from an Apple IPSW. That is Apple data, which the project does not fetch without the owner's decision. Payload assembly is also the work of NAT-006, which is currently in progress under another owner (`agy-nat006-20261110-aca2`). KRN-001 waits for that result rather than duplicating it.
