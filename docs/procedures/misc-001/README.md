# MISC-001 host source audit

Scope: host-only review and specification for haptics, NFC, biometrics, video codecs and external display. No hardware access, security identities, raw personal captures, firmware acquisition or upstream script execution.

Procedure: inspect named text at pinned `s24-linux` 417484173abc2c4fa93e738ea82ad9f2e84911b1 and cross-check `s24-bsp-reference` f85e53cfa5497ead5d78821efbac84e51f37a4e1 via read-only Git objects. Record source paths and SHA256. Compare with the sanitized DEV-001 profile. Describe exact known source inputs, unresolved inputs, interfaces and independent native acceptance for all five boundaries. Run the owned source-audit checker against pinned Git objects, including revision/hash/missing-object negative controls; it must never claim runtime qualification. Save dated commands, exits, tool version, artifacts, hashes and a handoff. Coordinator owns final integration and global checks.

The primary reference checkouts are read-only. Any generated report belongs in this worktree's `artifacts/misc-001/`. This procedure does not authorize device actions.

Reproduce from the task worktree:

```sh
python3 src/platform/misc/check_sources.py \
  --repo /home/egor/dev/pet/s24-ios-exynos/references/s24-linux \
  --comparison-repo /home/egor/dev/pet/s24-ios-exynos/references/s24-bsp-reference \
  --negative-controls
python3 -m py_compile src/platform/misc/check_sources.py
git diff --check
```

Implementation: [requirements](../../../src/platform/misc/README.md), [source index](../../../src/platform/misc/sources.md), [manifest](../../../src/platform/misc/sources.json), [checker](../../../src/platform/misc/check_sources.py). No peripheral driver/runtime interface was implemented. Native acceptance is described separately for each peripheral and remains unexecuted.

Initial orientation used ordinary `git show`/`git cat-file` reads against the primary references before recognizing they are promisor clones. Git may have hydrated missing text blobs during those reads; no intentional checkout/ref edit or upstream code execution occurred. Subsequent verifier reads explicitly disable lazy fetching and optional locks. Use only a worktree-local reference if more objects must be acquired. The failed first experiment-plan command (procedure supplied as prose instead of an existing path) registered no experiment; MISCHOST-001 was successfully registered against this procedure before the substantive manifest/check execution.
