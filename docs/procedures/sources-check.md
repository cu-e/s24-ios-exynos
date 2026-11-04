# Source checkout verification

Run `python3 tools/sources.py fetch ID` to explicitly retrieve a registry-pinned repository. This creates only its ignored references/ checkout, with hooks disabled, blob filtering, optional sparse review files and no recursive submodules. Existing work is never reset, cleaned or overwritten. An interrupted initial fetch may leave an incomplete checkout: inspect it before moving it aside and retrying.

`python3 tools/sources.py verify ID ...` is read-only and checks the recorded origin, full HEAD SHA, tracked/untracked changes and review-file hashes. Save its JSON lines in a dated run directory. Verification does not execute upstream code or establish licensing/measurement truth; review individual headers before incorporating code.

Offline regression tests create temporary Git repositories and check mismatched revisions/origins, dirty/untracked files, invalid paths and existing-work preservation. No network is used by those tests.
