# VM-028 handoff

Owner: `codex-guest-exec-20261106-dj`. Task remains in progress pending independent
review and integrator acceptance. Worktree `worktrees/vm-028-20261106`, branch
`team/vm-028-20261106`, base `aac27cf`.

Delivered a read-only source preflight and conservative console classifier,
12 exact source bindings with 37 line facts, five matches to the immutable
VM-008 object graph, diagnostic boot-argument controls and source-route notes.
The DEVELOPMENT kprintf gate requires `-enable_kprintf_spam`; the shim's default
args alone do not enable those messages. The shim defaults `console_quiet=1`.

No compiler, link, QEMU, phone, MMIO, SDK, proprietary binary or shared-source
mutation occurred. No genuine kernel console, PID1, natural Stop or native
result is measured. Existing VM-005 console is synthetic-payload evidence and
is only a rejection control. VM-009 worker confirmed its logs are compiler
logs and that launch/image identity gates belong with the kernel integrator.

Validation commands, actual exits, streaming input/tool/output hashes, time
and sampled `/proc` VmHWM appear in `evidence.json` and its retained artifact
directories `artifacts/avf-guest-console/evidence-e959092` and
`artifacts/avf-guest-console/evidence-c1520be` in this worktree. All11 controls
pass; source preflight exits0, actual VM-005 synthetic-console rejection exits2,
and isolated missing DEVELOPMENT flag exits1 with its expected diagnostic.
Maximum sampled child VmHWM is73,232KiB under a256MiB per-process address-space
limit. This is sampled evidence; a short child may exit between observations.
Implementation commit `e95909294487b4ad7f05a13804fdf5da1066dc51` is followed
by `c1520be` adding an isolated flag control and clearer bit-mask prose. The
original broad missing-argument negative is preserved; it omitted multiple
required options, so the follow-up specifically isolates the DEVELOPMENT flag.

Source-binding preparation initially rejected a non-unique `uart0`
needle; the completed fixture records both actual matching lines. Read-only
source exploration also returned missing guessed arm64/pe_init.c,
arm64/board_config.h, bsd/kern/tty_cons.c and build/config/vers.c paths; actual
ARM pe_init, pexpert/pexpert board header and config/MasterVersion were used.
Those exploration errors are not compilation failures and are not hidden by
the passing controls. The first unmeasured light test run passed11 controls;
the evidence run repeats them specifically to capture resource/time/log hashes.

Next: independent reviewer reruns scoped controls/preflight; kernel integrator
assesses source/object lineage and merges only scoped files under its own
integration lock/common checks. Future admitted guest execution must bind
actual kernel/image/payload, invocation, final printed combined args and raw
console before interpreting stage observations. Source pass alone authorizes
none of those later actions. Original owner records completion only after
review and integrator acceptance.
