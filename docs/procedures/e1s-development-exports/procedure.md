# Genuine native E1S raw export namespace

STR-011, original owner `codex-e1s-development-exports-20261106-sr11`.

Consume the accepted STR009 eight-component native DEVELOPMENT/E1S configuration descriptor and STR004 source/profile manifest. The fixture copies their actual configuration products into a fresh owned output, queries only a phony Make target and copies raw export bodies from the source manifest. No compiler, MIG, IIG, syscall script, version generator, recursive build or target executable is selected.

`MakeInc.dir` traverses `EXPINC_SUBDIRS` for MI and `EXPINC_SUBDIRS_ARM64` for MD separately. `MakeInc.rule` installs raw lists from `$(SOURCE)` and generated lists from the current producer directory. The fixture preserves those distinctions and leaves all generated outputs pending. Existing accepted STR010/STR012 products can be imported later by their explicit producer descriptors; this experiment does not fabricate their files.

The native Linux query shim retains its existing exact body. `BOUND_CHECKS=0` and `BOUND_CHECKS=1` are explicitly passed only for source-variable queries, skipping the parse-time compiler probe in `MakeInc.def`. Every queried export and MIG selection must agree between those settings. This does not measure bounds-attribute compiler support or qualify any compiler command flags.

Planned source-only command (fresh `prepare-001`):

```sh
python3 -B fixtures/public/e1s-development-exports/prepare.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out /home/egor/dev/pet/s24-ios-exynos/worktrees/str-011-e1s-development-exports-20261106/artifacts/e1s-development-exports/prepare-001
```

Run serially with finite 20-second Make query timeouts. Preserve real errors and partial outputs rather than changing source declarations or silently skipping a directory. Save every actual command, Make output, included Makefile identity, copied source/config hash and typed generated requirement. Before acceptance, apply bounded semantic rejection controls to provenance, traversal, path containment, conflicting destinations and generated/raw ownership. No broad source corpus replay or compiler execution is needed.

The result is a raw export namespace and MIG prerequisite inventory. Complete generated-header closure, 37 private exported ABI requirements, kernel/provider link, native startup, physical RAM and device behavior remain unqualified.
