# VM-036 reviewed source integration preparation

Owner: `codex-integrator-platform-20261106-cn`, INT-003.

PLATCOMPINT-001 prepares a separate, unpublished candidate containing the exact
five original VM-036 implementation/evidence commits through fd5ae558 and the
two independent review commits through fa310c5. Compare every replayed commit's
binary/full-index patch, constrain all changed paths to component or platform
review ownership, bind final source bytes and existing accepted capsules, and
save the actual Git commands and exits. Use guarded local Git; never copy a
worktree registry or modify shared artifact/source trees. No compiler, archive,
loader, guest or common test is part of preparation.

Current preparation precedes VM-039 publication. Its base is explicitly
provisional and may become stale. Preserve each packet, then rebuild on the
actual accepted HEAD and incorporate only the original DZ owner's separately
reviewed, once-only final process-policy adoption. Source review acceptance
does not adopt a policy or grant execution. Root's exact approval and continuous
shared integration lock remain prerequisites for publication/common.

Run `prepare.py` from this reporting worktree. Local preparation artifacts live
under `artifacts/platform-integration/components-stage1`, with the candidate in
the separate `worktrees/int-components-20261106` worktree. A later stage must use
a new output directory and preserve this packet. Do not run this procedure
again merely to repeat already accepted product/algorithm tests.
