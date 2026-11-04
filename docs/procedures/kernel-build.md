# Full E1S kernel prerequisite gate

BLD-001 built the freestanding loaders and applied the full E1S source delta. It did not compile XNU. KRN-001 owns the full kernel/dependency build.

```sh
python3 tools/build/kernel_preflight.py
# Only when these local inputs actually exist:
python3 tools/build/kernel_preflight.py --sdk /path/to/iPhoneOS16.5.sdk \
  --dependency-tools /path/to/pinned/hakios-build-tools
```

The initial check reports no configured SDK or dependency tool directory and exits 2. This is a concrete missing build input, not proof that no SDK exists anywhere on the machine. Do not download Apple SDK/userland/firmware automatically, substitute a different OS profile or report source patch application as a kernel compile. SDK presence still needs provenance and tool ABI review. Preserve any check_all_exports failure; a linked Mach-O alone does not satisfy full-build acceptance.
