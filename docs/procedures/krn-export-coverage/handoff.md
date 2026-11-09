# KRN-040 handoff

Measured the linked native kernel (`worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001/kernel/kernel.unstripped`)
against the two export-file sets of the `check_all_exports` recipe.

| Pass | Export entries | Missing |
| --- | --- | --- |
| without Private | 4254 | 0 |
| without Unsupported | 5412 | 37 |

All 37 missing names come from `Private.exports` and `Private.arm64.exports`, and they are exactly the names
in KRN-026's `fixtures/public/kernel-export-gaps/inputs.json`: 17 IOUnifiedAddressTranslator,
7 pmap_iommu, 11 DART/SART/UAT/NVMe PPL and 2 pmap query names.

This is a re-implementation of the membership rule, not the genuine `check_all_exports`, which would probably fail on these names.
KRN-026 stays with its owner and needs the provider inputs it names.
