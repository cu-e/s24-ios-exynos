# VM-020 guest firehose preparation

Owner: `codex-guest-exec-20261106-cx`. Branch:
`team/vm-020-20261106`; worktree: `worktrees/vm-020-20261106`.

This source-only producer prepares a genuine firehose kernel header export and
three compile recipes for the new guest namespace. It does not execute a
compiler, create an archive, measure a layout, link a kernel, start QEMU or
operate a physical phone. VM-020 remains in progress pending acceptance.

Run from this worktree with a fresh output directory:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  tools/build/avf_guest_firehose.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --output /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/preparation-session4
```

The producer verifies the full libdispatch revision
`a641558f447659d90ad002ef0ee6f0212273fbfc`, nine selected source/configuration
files against SHA256 and canonical Git blob SHA1, and source-built compiler and
unifdef executable pins. Shared Git reads disable lazy fetch and optional
locks. No archive or object from historical E1S qualification is consumed.

The immutable VM008 1080-row manifest is pinned to
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
The complete `bsd/subr_log.o` recipe supplies the new guest target, definitions,
configuration and generated include namespace. Only the source, owned-output
placeholders and explicit firehose backend/header/source includes change.
The backend definitions and header export flags are checked against the pinned
kernel xcconfig; the exported-header selection is checked against the actual
Xcode project header phase. Fresh unifdef output must match its exact qualified
header digest. The selected guest board source states MAX_CPUS=8 and
MAX_CPU_CLUSTERS=1; these are textual source observations. The separate provider
layout probe asserts both limits and records actual sizes/offsets only when it
is eventually compiled and independently inspected.

The final current record is `preparation-session3`; sessions1/2 are superseded
and must not be executed. Each current recipe binds a run-local immutable probe
copy so later maintained fixture edits cannot silently change its source.

`compile-plan.json` is an integration proposal, not an accepted executor ABI.
VM009 currently executes the fixed guest object graph and shard selectors;
it has no arbitrary component-plan CLI. Adapt these exact argv/cwd/input
bindings to its reviewed process engine after VM008 acceptance and root
resource admission. Verify the compiler runtime dependency closure at that
execution gate. Do not run recipes with a shell or duplicate the supervisor.
The producer creates no compiler execution path.

Future acceptance needs fresh provider and interface objects, actual guest
layout records, symbols and dependencies from the admitted common executor.
Archive only the genuine `provider.o`; exclude both measurement objects.
Independently check the exported interface prototypes/relocations and compare
provider imports with actual guest consumers. Preserve failures and do not
claim complete ABI equivalence, kernel boot or native logging from these
bounded checks. Integrators alone publish to MAIN and run common checks.

The source licenses and attribution remain in the pinned upstream files and
in the copied Apache-2.0 probes. Probe provenance is
`fixtures/public/xnu-kernel-firehose-headers/{provider-layout,interface-contract}.c`;
the guest layout probe adds two CPU-limit assertions.
