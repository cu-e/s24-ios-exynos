# REV-009 handoff

2026-11-05. Owner `codex-team-review-avf-20261105-bf`.
Branch/worktree `team/rev-avf-handoff-20261105`, `worktrees/rev-avf-handoff-20261105`, based integrated code 5d643c7. Own only `docs/reviews/vm-005`. Code 221923b2a7ee28bd2bb4c5f56a73a777a9d29476; final metadata bcc6437b3a4e3f774370901fccb6223600260e5c was read from main and checked against its exact committed bytes without updating this review worktree.

Bounded result: no actionable P0/P1/P2 finding. Actual conditional synthetic CPU entry and natural PSCI exit independently reproduced; correct-cookie suffix collision rejected in guest. Original four-case CPU and two metadata-control evidence audited. This is not XNU/PID1/iOS/Android AVF-on-phone/native qualification.

REVAVF-001 was planned in MAIN before verification. Actual command, exit 0:

```sh
GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 python3 docs/reviews/vm-005/verify.py
```

Actual evidence relative to MAIN: `worktrees/rev-avf-handoff-20261105/artifacts/rev-avf/20261105-session1/evidence.json`. It retains 26 commands/exits, full artifact/source/tool hashes, exact executed verifier bytes, parsed Mach-O/225-property real DTB, and two independent QEMU consoles/session samples. Exact source/build identities and all 142 artifact-index entries plus the index hash matched. Source references and original runtime artifacts remained read-only.

Independent guest results: positive natural exit 0, 0.0678s; cookie-suffix rejection natural exit 0, 0.0655s. One vCPU/256MiB RAM per guest, sequential; 5s deadline plus finite owned cleanup, sampled total peak 63,721,472 bytes, no surviving owned process. No compiler, broad build or QEMU rebuild. No phone/ADB/root/physical MMIO/flash/reboot. Original spin control's timeout outcome is correctly distinct from its QEMU exit 0; no extra spin replay was needed.

The runner rejects an existing output directory. Choose a fresh canonical `S24_REVAVF_RUN` for any justified reproduction. Review whitespace check: `git diff --check`, exit 0. Next: coordinator inspect bounded report/evidence, integrate review-only commit and assess acceptance alongside main common checks. Keep REV-009 in progress until explicit coordinator acceptance; do not complete VM-005 under the implementation owner's identity. VM-002 full XNU/PID1 requirements are unchanged.
