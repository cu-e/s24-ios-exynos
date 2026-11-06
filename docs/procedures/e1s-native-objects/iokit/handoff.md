# STR-027 IOKit source slice handoff

Owner: `codex-e1s-native-objects-20261106-sr27`. Task remains in progress.
Worktree: `/home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106`.
Branch: `team/str-027-e1s-native-iokit-20261106`, based on `415c9a1fcad73cb47affcedbb037520ce973f888`.

Root authorized the atomic claim and source slice/provenance only. The accepted qualified graph descriptor is SHA-256 `c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579`; the partition, portable profile, and consumer context remain pinned in [source-slice.json](../../../../fixtures/public/e1s-native-objects/iokit/source-slice.json).

The slice preserves all 102 IOKit identities in native Makefile order, indices 0–101. It binds each original recipe file, the compact JSON hash of its unchanged selected compiler vector, and the accepted selected source. The 85 derived native sources retain STR-014 lineage. The 17 genuine IIG implementation entries bind the STR-017 producer descriptor, original producer path/hash, and shared-context path/hash. Historical graph `pending-genuine-generated-producer` labels are preserved as historical fields; they do not replace accepted consumer-context source bindings.

Native E1S/ARM64/DEVELOPMENT, source capacity ten CPUs/four clusters, existing BOUND_CHECKS=0 receipt, and the separately approved `-DXNU_NO_TYPE_BUILTINS=0` portable profile are preserved. No feature probe, Make query, generator, compiler, loader, archive tool, target tool, or common check ran. No RELEASE/BCM/guest objects were adopted. No private CWD projection or caller execution plan exists for this task.

The bounded source consistency command was:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s artifacts/e1s-native-objects/iokit/source-slice-001/prepare_slice.py
```

It exited 0. [Source evidence](source-slice-evidence.json) records the retained script hash/path, manifest hash, checks, wall time, `/proc` high-water RSS, and 256 MiB address-space/30 s CPU/60 s whole-process limits. There were zero child processes. This checks ordered provenance, recipe/source bytes, and genuine IIG placement; it does not qualify compiler input or dependency closure.

Next: wait for root's reviewed STR-030 native caller interface and explicit resource budget. Then use that single existing caller for the registered source plan, owned private CWD/output derivation, and later separately authorized actual compilation. Preserve native recipe arguments and typed generated mode distinctions. Actual acceptance still requires 102 fresh ARM64 Mach-O objects, actual MD closure and genuine generated inputs, retained failures, independent review, integration/common checks, and root acceptance before owner closure. Provider, link, private37 ABI, runtime, and hardware obligations remain downstream.
