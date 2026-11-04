# English migration verification

Scope: host only. No ADB command, APK installation or phone operation is needed.

Inputs: source revision recorded by DOC-001, the working tree and original local profile files. Use an external 120-second timeout for each check. Stop by terminating the host process; no device cleanup is required.

1. Run `make check` and save stdout/stderr and the actual exit code.
2. Check maintained project text for Cyrillic, excluding the three explicitly preserved historical evidence JSON files. Imported snapshots and raw/local originals are excluded; the new English report is checked separately.
3. Check local Markdown link targets in maintained documentation and the English device report. Remote links do not require network revalidation for a translation.
4. Verify that original evidence bytes and their registry SHA256 values match the pre-migration revision. Compare English evidence views to their originals: only summary/limitations and explicit translation metadata may differ.
5. Verify unchanged task identities, existing task status/ownership/dependencies/scopes and project permissions. DOC-001 is the new translation task; language and reading-view fields are additive.
6. Verify the 35 existing capture checksums and the original private report checksum against their manifests/evidence. Do not recollect data to make this check pass.
7. Run `git diff --check` and regenerate STATUS.md using `make status`.

Pass requires all applicable checks to succeed. Missing private inputs make those integrity checks inconclusive; do not fabricate replacements. Save verification results and host logs under fixtures/public/english-migration/ without identifiers or device contents. This procedure validates translation and integrity, not a new hardware result.
