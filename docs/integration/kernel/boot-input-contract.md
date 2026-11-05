# Reviewed boot inputs and preserved histories

This intake combines four distinct results. It grants no compiler or guest
lease. The integration gate requires a fresh MAIN base, exact source patches,
frozen evidence and concrete approval before publication and one common check.

- VM013 produced 104 genuine IOKit ARM64 objects, including the 17 generated
  IIG products, with 751 unique actual dependencies. Together with the accepted
  VM018 thirteen objects and VM015 seventy-seven objects, these are 194 actual
  objects from the original 1080-row guest graph. Object compilation does not
  establish final provider closure, a linked kernel, private ABI or runtime.
- VM034 and REV026 qualify the exact compiled/static PID1 image
  `fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3`.
  VM025 and REV027 independently check prospective admission against that exact
  image and its historical source/build witnesses. The legacy PID1 remains
  inadmissible because its inline syscall assembly failed to declare the x1
  return clobber. Physical historical worktrees stay frozen; admission does not
  relabel their measurements or execute a different helper under an old hash.
- VM024 and REV028 qualify the exact 32768-byte raw mockfs root image
  `b26710980746c0fbc48f4d40f9b43533784617c7332ba54055e44da2d0f12b59`:
  the 16512-byte compiled PID1 followed by 16256 zero bytes. Provenance is
  preserved. This is trusted-input packaging and structural verification,
  without cryptographic signature authentication or a hostile-writer sandbox.
- VM027 captured and decoded 12540 real bytes emitted by the unchanged shim,
  SHA256 `afa048b454b658399636030abe71bc706665fb722564459b93e75609f7d6d491`.
  Its exact one-CPU spin plan had no RAMDisk. QMP pause, memory capture and host
  quit establish that capture; they establish neither XNU execution nor
  guest-initiated shutdown. Future kernel/root placement requires its own
  source-bound plan and telemetry.

Kernel exec, signing/default-stack behavior, PID1 syscalls, kernel serial,
panic/PSCI and bounded host stop remain unmeasured. A genuine linked image and
its runtime acceptance are later steps. First QEMU boot is an intermediate
milestone in the full graphics, input, services and platform roadmap.

The optional gate `historical_paths` names the exact transient IOKit
`inspect.py` file, which was later renamed to avoid shadowing the Python
standard library. All eight original commits retain identical patches. The
explicit list is disjoint from final paths, receives every path protection,
and its union with final paths must exactly equal the complete commit history.
REV030's malformed-field finding is preserved; the additive correction requires
a JSON array of strings. Historical source and corrected source have separate
immutable worktrees and evidence. No history is squashed or silently waived.

Existing VM008 namespace qualification and its historical verifier remain
governed by [vm008-contract.md](vm008-contract.md). The original 132135 object
runner remains physically available for prior measurements; the accepted 5c7b9c
optimization preserves their namespace bytes, input keys and compiler argv.
Never change a running job's tools, inputs or limits. Missing Firehose headers
from the later libkern attempt require a source-justified immutable namespace
version and a new planned retry, preserving the original failure.

Current two-job/2 GiB experiments retain their policy. The user's next-boundary
policy permits at most six compilers globally and 6 GiB for new project
processes, with stable 4 GiB available-memory admission. New plans must record
duration, peak RSS and active swap before a measured eight-compiler trial.
Shared publication/common checks remain sequential under the same flock, with
an explicitly allocated resource slot. Phone restrictions remain unchanged.
