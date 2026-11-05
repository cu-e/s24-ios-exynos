# VM-030 handoff

Owner: `codex-guest-exec-20261106-dl`. Worktree:
`worktrees/vm-030-20261106`; branch: `team/vm-030-20261106`.
Base main: `aac27cf`. Final source freeze:
`bc92b3c48cab58ba0252555384acc0536a918a14`.

The bounded source/log-contract outcome is ready for independent review. The
task remains in progress; only the original owner may close it after review,
integrator acceptance and fresh common checks. No compiler, QEMU, genuine guest
or phone operation was executed. No main code or reserved VM-002 file changed.

Read [README.md](README.md) for the exact source trace and admission schema,
[evidence-final.json](evidence-final.json) for 148 streamed artifact bindings,
full source and tool pins, actual commands/exits/times and limitations, and
[experiment-2.md](experiment-2.md) for the final registered offline experiment.
The unchanged [earlier evidence](evidence.json) and source/evidence commits
`8ea3ea6`/`847150a` remain preserved.

Measured scoped validation:

- Source preflight passes all 17 exact existing source/tool/archive bindings;
  canonical Scion/XNU manifest and composed member identities are checked.
- Forty-four source/synthetic controls pass in 0.508 seconds; the actual
  current-image VmHWM is 40,116 KiB, under a 256 MiB address-space cap.
- Source preflight and synthetic halt CLI artifact assessment exit 0. Legacy
  PID1 runtime assessment exits 2. No positive fixture establishes an actual
  guest stop.
- Registered VMSTOP-002 executes five actual negative CLI commands: timeout
  with exit zero becomes host cleanup, host-origin QMP is inconclusive, malformed
  QMP, an unreviewed source descriptor and legacy PID1 admission fail. All exit 2;
  maximum individual elapsed time is 0.117285 seconds, current-image VmHWM at
  most 19,648 KiB.
- The precursor 38-case run remains preserved but lacks its exact precursor
  source hash. The later 43-case run and four-case VMSTOP-001 results remain
  preserved with source freeze `8ea3ea6`; final acceptance uses the frozen
  44-case run and VMSTOP-002.
- Scoped Git diff checks pass. Main common checks are reserved for integrators.

Important finding: the existing VM-002 supervisor can label identity-bearing
serial output `observed` even when its deadline triggers forced cleanup. It has
no QMP cause or exhaustive signal/reaping record. Its current output therefore
cannot establish a genuine guest stop. The common runner owner and kernel
integrator were notified; VM-030 modifies no blocked VM-002 implementation.

VM-025 then disclosed a concrete legacy PID1 source ABI defect: its assembly
declares x1 input-only while selected XNU overwrites x1. Root assigned VM-034
for replacement. The final descriptor pins VM-025 handoff/evidence and sets
`pid1_runtime_admissible` false. The default PID1-panic assessment hard rejects
the old source; direct synthetic classifier controls merely exercise the future
panic/stop contract. Earlier positive synthetic PID1 artifact admission is
explicitly superseded. No measured failure of the historical optimized binary
is claimed. A reviewed replacement descriptor is required to change admission.

Next concrete step: independently inspect the scoped commits, trace, source
pins and retained negative logs. The kernel integrator may integrate after
acceptance under the shared integration lock. Future genuine runtime admission
needs a qualified kernel with source-to-image provenance, accepted VM-008
namespace, explicit root resource admission and the sole QEMU lease. It must
collect separate console/QMP/supervisor evidence and must not infer success from
identity or exit zero alone. No native-device or iOS compatibility claim follows.
