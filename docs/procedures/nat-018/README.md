# NAT-018: integrate NAT-006 host tooling into main

2026-11-10. Owner: codex-nat006-main-20261110-r4.
The owner explicitly requested integration into main. Host work only; no phone
command, image build, flash or reboot was performed for this integration.

Source: branch `team/nat-006-recovery-image-20261110`, final commit
`d20cc17742a2` and parent WIP `ac22ef588e08`. The exact full hashes and nine source
file identities are in `artifacts/nat-018/integration-001/source-manifest.json`.
This preserves the RECOVERY builder, independent verifier, runtime-FDT harness,
two loader patches, tests and original host evidence.

Integration used `git merge --squash --no-commit` to incorporate the final tree
without importing historical device identifiers into main's commit history.
Eight of the nine files are byte-identical, including the original evidence.json.
The maintained handoff copy has four device serial literals redacted and an
explicit historical-status notice. Its original remains unchanged in the source
worktree and commit. The notice corrects the historical Android 14 wording against
measured Android 15 and points to the subsequent NAT-012 restore/NAT-014 review.
No immutable original evidence was edited or re-recorded as a new measurement.
The original source branch remains independent; squash integration does not make
its tip an ancestor of main. Compare actual file contents and this manifest when
assessing later changes, rather than interpreting ancestry alone as missing code.

## Validation

Private run directory: `artifacts/nat-018/integration-001`.

- `recovery-tests`: main's four RECOVERY unit tests passed.
- `verifier-run`: main's independent verifier passed all 20 checks on the existing
  `artifacts/nat-006/build-002/recovery-nat006.img` and its stock restore package.
  Source/object inputs were copied into a new `verifier-inputs` directory so that
  the old report and FDT harness outputs were not replaced. The existing source
  was exercised on the host; no new phone image was assembled.
- `make-check`: `make check` passed all 214 tests.
- Staged-file scan found no known device serial. Whitespace checks pass for code
  and prose. Unified patch files retain their exact bytes; their leading context
  spaces/tabs and blank context lines cause expected `git diff --check` warnings
  when Git treats the patch itself as newly added text. Those bytes were retained
  rather than altering a provenance-bound patch.

The original NAT-006 task evidence still references its unchanged worktree copy.
This integration does not qualify native boot safety, watchdog return or display
format assumptions. NAT-009 is under separate review and NAT-017 still requires
a qualified early-log channel and a new canary decision. Existing working Android
and the restored stock RECOVERY are not modified by this merge.
