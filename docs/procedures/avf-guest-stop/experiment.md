# VMSTOP-001: offline stop observation admission

Task VM-030, owner `codex-guest-exec-20261106-dl`, 2026-11-06.

Hypothesis: the source-bound offline assessor rejects a timeout with successful
identity text and exit zero, a host-origin QMP shutdown, malformed QMP event data,
and an unreviewed source-preflight descriptor. It must preserve the individual
negative command outputs and classify host cleanup separately from a guest stop.

This experiment uses authored synthetic serial/QMP/supervisor records derived
from the already executed scoped validation controls. It executes only Python
against local files; no compiler, QEMU, guest or phone is started. Earlier
`controls-1`, `controls-2`, source preflight and CLI smoke checks are preceding
implementation tests, not observations from this registered experiment.

1. Copy the known synthetic control record into a new owned artifact directory.
2. Construct four independently altered records and hash every referenced file.
3. Invoke `avf_guest_stop.py assess` once per record with a fresh output path.
4. Require exit 2 for all four; timeout must produce `host-cleanup`, host-origin
   QMP must produce `inconclusive`, malformed QMP and changed descriptor must fail.
5. Preserve commands, exits, wall time, stdout/stderr, input/output hashes and
   the Python process's current-image VmHWM. No compiler or guest lease is used.

Deadline: 30 seconds; each Python process is constrained to 256 MiB address space.
Acceptance is a source/log-contract check. It does not qualify a complete XNU
image, source-to-image linkage, genuine PSCI execution or physical S24 behavior.
