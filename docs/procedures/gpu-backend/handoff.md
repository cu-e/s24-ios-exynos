# GPU-013 handoff

Owner: `claude-gpu-backend-20261110-g13`. Branch `team/gpu-013-backend-core-20261110`. Code commit `f4ed03567d1b9862c039702c909ce671dd0c66bd`.
Evidence category: host-test. Nothing here ran on a GPU, on the phone or under QEMU.

## What changed

The backend core, its tests and its mutation list live in `src/platform/gpu/native/backend/`. The
ARM64 compile script is `fixtures/public/gpu-backend/compile_arm64.py`. Rules and known limits are in
`README.md` next to this file.

## Results

| Command | Exit | Result |
| --- | --- | --- |
| `python3 src/platform/gpu/native/backend/check.py --run check-006` | 0 | 37 tests under ASan/UBSan and TSan; 138 mutants killed, 0 survivors, 2 documented as equivalent |
| `python3 fixtures/public/gpu-backend/compile_arm64.py --run arm64-003` | 0 | ARM64 Mach-O objects; undefined symbols are the stack guard and `sgpu_get/put32/64` only |

## Review

A same-session subagent reviewed the core from source only and found 7 defects and 2 contract gaps
that the mutation suite could not detect. A second pass by the same subagent over the fix diff found
no new lifetime or memory-safety defect and 2 low-severity issues. Those were fixed in `f4ed035`,
which was not reviewed again. Neither pass was independent of this session.

## Open

- No `sgpu_be_ops` implementation exists for real hardware, and `profile_verified` is never set for it.
- GPU-007, GPU-008 and GPU-012 stay open. This work does not establish GPU execution.
- Next step for whoever continues: implement the ops table once GPU-007 produces a validated profile.
  GPU-007 depends on KRN-001, which is held by another owner.

The light-compile lease was self-issued by this Claude session acting as coordinator under the owner
directive of 2026-11-10, not by the Codex root coordinator. It was released with no survivors.
