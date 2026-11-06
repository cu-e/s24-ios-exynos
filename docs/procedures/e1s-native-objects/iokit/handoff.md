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

Root later authorized source planning at CM final `1e5a2ee8` using the unchanged physical STR-030 fix2 caller SHA `2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f`. The strict eight-field [build manifest](../../../../fixtures/public/e1s-native-objects/iokit/build-001-slice.json) preserves the entire ordered IOKit102 partition. Original-owner actual host-test experiment `STR027BUILD-001` is registered and remains planned. The sole actual source-plan export exited 0; [plan receipt](plan-001-receipt.json) binds exact physical JSON/raw evidence and [procedure](build-001-procedure.md) freezes the intended future execute request. Root common84 PASS and explicit ProjectBudget/outer-watchdog admission are still required before any actual execute. No future output, private projection, loader, or compiler ran.

## Actual STR027BUILD-001 terminal failure, root wave85

Root dispatched the exact frozen caller/manifest/plan once under wave85, GNU timeout 1890 seconds with TERM/30-second kill grace and root PSI guard. The observer did not launch another executor. Wrapper identity was PID1112197/start_ticks62162874; terminal wrapper exit1. Root's actual command, approval/allocation pins, raw report and every retained compiler/loader log are bound in [actual evidence](build-001-evidence.json). Raw owned report SHA-256 is `63606bb1a309893be47b7df3bc0556b640a193046f95d8d9081f9470e4453554`.

The actual trusted-loader gate passed. Five compiler rows exited0 and produced fresh ARM64 Mach-O objects with actual MD/input/resource qualification: `OSObject.iig.cpo`, `OSAction.iig.cpo`, `IOService.iig.cpo`, `IOUserClient.iig.cpo`, and `IOMemoryDescriptor.iig.cpo`. Their observed dependency counts were180/178/344/341/324 (348 unique paths combined). Object and MD bytes were hashed against the report; headers identify genuine ARM64 MH_OBJECT. Peak sampled controller+child RSS across completed rows was157601792 bytes; controller HWM81911808 bytes.

The sixth row, `IOBufferMemoryDescriptor.iig.cpo`, started but was terminated with exit-15 after `ValueError('Project budget lock acquisition timed out')`. It is resource-deferred, resource qualification inconclusive, object not produced and inputs not observed. Its sampled RSS peak0 is a missing pre-termination sample, not proof of a zero-resource compiler. No compiler error diagnostic occurred in observed stderr. The remaining96 rows were not dispatched. Overall failure is `Stop after failed/deferred native row`; budget release also timed out. Seven terminal child-session checks report zero RSS/processes, and `owned_survivors` is empty; root's wave release was false at the receipt. Root owns broker review and release.

Actual `STR027BUILD-001` is recorded exactly once as FAIL; source-only receipts, plans, outputs and all failed bytes remain immutable. STR-027 remains in progress and does not meet102-object acceptance. No retry, fix, compiler/loader/generator/Make/target tool rerun, resume credit, or new executor is authorized. Next action is root review of admission/release failure before a separately approved change or fresh experiment. No provider, link, private37 ABI, runtime or hardware claim follows from these five objects.
