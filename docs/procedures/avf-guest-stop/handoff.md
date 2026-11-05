# VM-030 handoff

Owner: `codex-guest-exec-20261106-dl`. Worktree:
`worktrees/vm-030-20261106`; branch: `team/vm-030-20261106`.
Base main: `aac27cf`. Source freeze:
`8ea3ea619f5e8b98c72c0410afce1ce40c1dd6ad`.

The bounded source/log-contract outcome is ready for independent review. The
task remains in progress; only the original owner may close it after review,
integrator acceptance and fresh common checks. No compiler, QEMU, genuine guest
or phone operation was executed. No main code or reserved VM-002 file changed.

Read [README.md](README.md) for the exact source trace and admission schema,
[evidence.json](evidence.json) for 76 streamed artifact bindings, full source and
tool pins, actual commands/exits/times and limitations, and
[experiment.md](experiment.md) for the registered four-case offline experiment.

Measured scoped validation:

- Source preflight passes all 15 exact existing source/tool/archive bindings;
  canonical Scion/XNU manifest and composed member identities are checked.
- Forty-three source/synthetic controls pass in 0.48 seconds; the actual
  current-image VmHWM is 40,292 KiB, under a 256 MiB address-space cap.
- Source preflight and synthetic CLI artifact assessment exit 0. A changed
  console digest exits 2. The positive fixture is synthetic and establishes
  no actual guest stop.
- Registered VMSTOP-001 executes four actual negative CLI commands: timeout
  with exit zero becomes host cleanup, host-origin QMP is inconclusive, malformed
  QMP and an unreviewed source descriptor fail. All exit 2; maximum individual
  elapsed time is 0.119854 seconds, current-image VmHWM at most 19,624 KiB.
- The precursor 38-case run remains preserved but lacks its exact precursor
  source hash; final acceptance uses the frozen 43-case run and experiment.
- Scoped Git diff checks pass. Main common checks are reserved for integrators.

Important finding: the existing VM-002 supervisor can label identity-bearing
serial output `observed` even when its deadline triggers forced cleanup. It has
no QMP cause or exhaustive signal/reaping record. Its current output therefore
cannot establish a genuine guest stop. The common runner owner and kernel
integrator were notified; VM-030 modifies no blocked VM-002 implementation.

Next concrete step: independently inspect the scoped commits, trace, source
pins and retained negative logs. The kernel integrator may integrate after
acceptance under the shared integration lock. Future genuine runtime admission
needs a qualified kernel with source-to-image provenance, accepted VM-008
namespace, explicit root resource admission and the sole QEMU lease. It must
collect separate console/QMP/supervisor evidence and must not infer success from
identity or exit zero alone. No native-device or iOS compatibility claim follows.
