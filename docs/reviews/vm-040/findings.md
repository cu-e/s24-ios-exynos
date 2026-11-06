# REV-037 initial findings against frozen VM-040

**Changes required.** Two P2 source/host-control findings below block acceptance
of the initial collector source. The actual genuine-image allowlist is empty:
production plan/run refusal is correct, and no genuine image/guest/runtime result
is claimed. Findings concern the prepared future branch, exercised only with
explicit host dependency seams or authored FDT properties.

Owner `codex-review-kernel-collector-20261106-vm037`; scope only
`docs/reviews/vm-040`; worktree/branch `rev-vm040-20261106`.
Producer remains `codex-guest-collector-20261106-eh`, separate frozen worktree
`worktrees/vm-040-eh-20261106`. Exact reviewed commits:
`d81bc09ba3123a37b2cc5d19497a1fe4720b0eab`,
`b309cae21e75aecea68f6c4ef01fdec3c430cd08`,
`9efba942901bf6457c4807ca91f61f5697ae48a2`,
`a0b64b31cceb6e4b0d3138628d4fed386d2fe2bc`.
Original collector SHA256:
`82dc4f31e0a43431e49741bc26368ff81c3820a21985a97fef82c11f6f9e6589`.

## P2-1: expired/revoked lease is checked only after process creation

Original `collect()` lines649–654 check the lease before each of three memory
samples and sleep one second after **every** sample, including the last. It then
creates the run directory and calls `own_process()`. The process primitive calls
Popen at line485; `guard_extra` first runs in the post-spawn guard. A lease can
expire or change after sample3 and still authorize a process creation before
cleanup recognizes the stale grant. Cleanup succeeding does not satisfy the
before-spawn authorization contract.

`lease_repro.py` reaches that sequence with explicit host-only seams: prepare and
protocol operation are dependency-injected, ROOT/queue/plan live only inside this
review directory, and the lease clock advances deterministically. No actual image
or root guest lease is invented. The **real** lease validator, collect admission
loop, Popen, resource sampling and accepted cleanup implementation execute. Only
a tiny owned Python sleeper may start, with its watchdog tightened to2s.

The lease passes at virtual0,1,2s; expiry is2.5s; final sleep reaches3s. A real
owned Python session3472977 is created. The next lease check rejects with
`Root lease stale/not active`; actual SIGCONT/SIGTERM sends are recorded, exit-15,
zero owned survivors. All external review admission samples were actual >=4GiB
at least1s apart. Current-image VmHWM was22,163,456 bytes, under256MiB AS.

Frozen report `runs/lease-expiry-1/report.json` SHA256:
`e5619b123550415d72dc575839c6823419a239cbf8c2c6010e27445082b2311c`.
Actual child record SHA256:
`5c7397e1ae3f31112b6145b20fa611594ec37704b6f0dcf067fb0773c2368825`.

Required correction: revalidate Stop, exact lease and resource floor immediately
before Popen, preserve live checks after spawn, and avoid the unnecessary final
admission sleep. Independent regression must prove no child starts when the
lease/floor is invalid before launch. Root authorized the author to correct this
in a separate worktree; the original source/capsules remain unchanged.

## P2-2: paused FDT admission disagrees with actual shim consumers

Original `fdt_contract()` lines208–214 validates memory reg by node spelling only,
uses substring membership for compatible strings, and drops GIC span sizes with
`[::2]`. Concrete counterexamples are in `fdt_repro.py` and frozen
`runs/fdt-predicates-1/report.json` SHA256
`f45fd093b06e995d92cb29d56504ee1107204f4a92f52b07dcbdc88bdc82aeac`.

- The producer's actual published positive `authored-input.dtb` is accepted but
  has **no** `device_type` on `/memory@40000000`. Pinned `avfboot.c:330–339`
  searches root children for `device_type` exactly `memory` plus valid reg; when
  none exists, it calls `die("no memory node in the FDT")`. The published host
  peer therefore exercises a source-invalid positive memory descriptor.
- `xarm,pl011\0` and `xarm,gic-v3\0` still pass collector substring membership.
  Pinned `fdtx.c:185–199`/`fdt_find_compatible` match whole NUL-delimited compatible
  tokens. The shim's PL011/GIC searches at `avfboot.c:315–317,354–358` cannot
  select these prefixed identifiers. GIC mismatch is fatal.
- Reg tuples with the correct GIC addresses but both sizes zero pass. The shim
  reads both sizes and writes them into the Apple tree at lines1017–1021; the
  admission check must validate the source-supported mapped spans as well.

These are source-consumer predicate counterexamples, not execution of C/shim or
proof of guest failure. Primary source SHA256 identities for `avfboot.c` and
`fdtx.c` are preserved in the report. Required correction: exact memory type,
terminated compatible-list tokens and qualified GIC spans, plus a source-valid
peer fixture and focused bad-field controls. No broad FDT rewrite is requested.
Author/root were notified; source correction belongs to the original author.

## Bounded remaining review

`review_controls.py` independently passes76 checks and19 expected rejections,
with43 original source/evidence/artifact bindings. It rehashes the final actual
19-control producer capsule/outputs without rerunning its broad suite, and
checks the accepted helper/fixture/VM0221080-map/QEMU/shim pins. Source review
finds the planned complete source/object/raw receipt/dependency/link/root/PID1
and final-args hash chain remains explicitly future input, never actual image
qualification. The current fixture cannot admit an image via caller booleans.

Focused tests cover empty allowlist/no Popen, pre-requested Stop, changed files,
symlink/traversal, duplicate/nonfinite JSON, incomplete1080 lineage, missing full
combined args, conflicting args, malformed FDT, SMC mismatch, malformed QMP/
wrong IDs/forbidden quit/bool dump size, repeated markers/shutdowns, host cleanup,
wrong final args, and bad termination types/timing. Current-image VmHWM34,168,832
bytes; no child is needed by this supporting script.

The actual producer Python-peer record has `guest_started:false`, input Linux
FDT `Apple_serialized_tree:false`, host-qmp-quit/guest:false, and no survivors.
Even paired with an explicitly authored favorable console, that actual event
cannot become guest-origin shutdown. Authored positive observations remain
`consistent-observations-awaiting-review` with genuine kernel, PID1 runtime and
PSCI trace all false. Frozen legacy VM030 rejection is never waived.

Linux input FDT is admitted before cont; optional Apple-tree parsing requires a
later shim checkpoint and source-derived extent. No pre-CPU Apple tree is
invented. Actual image-qualified preparation/execution remains unmeasured.

## Next step and preserved preparation failure

Await the author's narrowly scoped corrections, then independently recheck exact
new source bytes against the preserved counterexamples and necessary bounded
positives. Do not close REV-037 or VM-040 before independent acceptance and fresh
integrator common checks. No compiler, QEMU, common test, producer/witness edit,
phone operation, or unrelated-process termination occurred.

Task registration initially used a /tmp spec and correctly failed with exit2:
`Paths must stay inside the project, including symlinks`. The unchanged spec was
moved to `MAIN/artifacts/rev-vm040-task-spec-20261106.json`; task add succeeded and
atomic claim-next returned exactly REV-037. No other claim or registry was used.
One source discovery read guessed nonexistent `avf/shim/fdt.c` (exit2); actual
`fdtx.c` was read from the immutable source tree. Neither failure mutated input.
