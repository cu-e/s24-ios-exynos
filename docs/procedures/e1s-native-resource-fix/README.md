# STR-039: matched Clang resource headers for the native E1S APFS object

Source-only preparation. No compiler, preprocessor, loader or Make query ran in
this task and no object was produced.

## Diagnosis

STR024BUILD-005 stopped at `bsd/apfs_deflate.o` (original index 109, slice 65)
with `fatal error: 'arm_neon.h' file not found` from
`bsd/miscfs/apfs/libdeflate/lib/arm/cpu_features.h:84`. The failed row is
preserved at
`worktrees/str-024-e1s-native-objects-bsd-a-20261106/docs/procedures/e1s-native-objects/bsd-a/build-005/failed-row-context.json`.

The genuine recipe already carries the source-selected
`-idirafter $(shell $(CC) -print-resource-dir)/include` from
`bsd/conf/Makefile.arm64`. Its recorded operand (argv index 217 of the failed
run) is `artifacts/xnu-compiler-cxx-storage/lib/clang/17/include`, which was
never materialized after the compiler moved to `source-build-session2/`. A scan
of all 1042 native recipes finds that operand, and any `-idirafter`, only in
`bsd/apfs_deflate.o`.

## Change

`fixtures/public/e1s-native-resource-fix/native_compile.py` is accepted caller
`2676a8ed` plus:

1. `rebind_resource`: for exactly `bsd/apfs_deflate.o`, replaces the single
   absent operand with
   `artifacts/xnu-kernel-resource-headers/generate-session1/resource/lib/clang/17/include`.
   Any other object carrying the operand, a changed operand, a duplicate or an
   existing old root is rejected.
2. `resource_inputs`: the root must be canonical and contain exactly
   `arm_neon.h`, `arm_bf16.h`, `arm_acle.h` with the RHDR-002 hashes. The three
   files enter the admitted input index, so the existing namespace walk and MD
   dependency qualification cover them.
3. One `RUNTIME_SHA` repin. Host `/etc/ld.so.cache` changed through an ordinary
   `dnf` ldconfig on 2026-11-09 (dnf history 286). All five pinned libraries,
   their aliases and `ld.so.conf` are byte-identical to the accepted runtime;
   `runtime.json` differs from accepted `94685ae6` only in that one hash.
   The real library mapping is still measured by the loader step at execution.

Header authority: `docs/procedures/avf-resource-namespace/guard-session3/qualification/canonical-resource-proof.json`
(`25024c71`) ties compiler `7972eb28` to report `41cfca89` and the three header
hashes at public LLVM revision `fa944373`. Only the generic tool and header
facts are reused; no guest manifest, flag set or object is adopted.

## Reproduce

```sh
python3 -I fixtures/public/e1s-native-resource-fix/native_compile.py plan \
  --manifest $PWD/fixtures/public/e1s-native-resource-fix/source-only-manifest.json \
  --manifest-sha256 9815a019ef75b6947a28485a2defcd690acc5d2fb139419f7a4d4f076eac7058 > artifacts/e1s-native-resource-fix/source-plan-apfs.json
python3 -I fixtures/public/e1s-native-resource-fix/check_source_only.py \
  --plan artifacts/e1s-native-resource-fix/source-plan-apfs.json \
  --out artifacts/e1s-native-resource-fix/source-only-checks.json
```

The source-only manifest requires an active STR-039 claim by its recorded owner.

## Not established

Whether APFS compiles with these headers, the object contents, the remaining 61
BSD-a objects, the full 1042-body image, runtime behavior or anything on the
phone. Those need a separate preregistered compile task.
