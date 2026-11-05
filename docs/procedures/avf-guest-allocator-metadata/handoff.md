# VM-033 handoff

Owner: `codex-guest-exec-20261106-do`. Branch: `team/vm-033-20261106`.
Worktree: `/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-033-20261106`.
Source implementation commit: `544ba0875c0648b2cc963ff43bd21644f0005b17`.

The read-only preflight passes against the actual immutable VM-008 guest source,
compiler provenance, compile commands/dependencies and two real ARM64 objects.
Frozen manifest SHA256 is
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
`inputs.json` pins all exact reports, source/compiler helpers and headers.
`fixtures/public/avf-guest-allocator-metadata/evidence.json` records all four local
runs, commands, exits, SHA256s, timestamps and actual `/proc/self/status` HWM.
The initial final run passes at 71,696 KiB VmHWM. Supplemental preflight-5 also
requires actual kalloc.o relocations to all four boundary symbols and passes at
71,512 KiB VmHWM. Its exact report and SHA are recorded separately in
`fixtures/public/avf-guest-allocator-metadata/boundary-relocations-evidence.json`;
the original experiment capsule remains immutable. No compiler/linker/generator/guest ran.

OSData has the genuine 192-byte `__DATA_CONST,__kalloc_type` section with
`S_ATTR_LIVE_SUPPORT` (0x08000000), 8-byte alignment, and six ARM64 unsigned
64-bit pointer relocations. Three names resolve to `site.ExpansionData` and three
signatures to `12` in real `__cstring` storage. kalloc.o is the consumer: it has
four undefined section start/end symbols for fixed/variable records and emits no
allocation record of its own. The same production checks reject copies of the
real OSData object with a renamed metadata section, cleared live-support flag or
removed relocation table; the production compiler identity gate rejects the
actual distinct stock compiler. Historical genuine stock-compiler OSData failure
is hash-bound with its exact command and metadata-builtin diagnostics.

The first parser attempt failed because ARM64_RELOC_ADDEND encodes an addend,
not a section index. The original failure remains at local-runs/preflight-1.
The correction is checked against pinned public arm64/reloc.h and validates the
following PAGE21/PAGEOFF12 relocation pair. Later passing runs preserve checks
before and after string resolution and shared wrongcompiler-gate improvements.
Exploratory missing-path and regex failures are recorded in the evidence summary.

Primary kalloc.h requests `regular, live_support`, not unconditional retention.
Public loader.h describes blocks live when they reference live blocks; kalloc.c
consumes four section boundaries during startup. MakeInc.def enables LTO dead
stripping. Final linking must preserve reachable records, their referenced
name/signature storage, boundary symbols and record extents. A final linked
kernel, LTO reachability and boot-time consumption remain unmeasured. This is a
source/object preflight result and does not close VM-033 or establish a guest boot.

Next: independent reviewer inspects this scoped commit and exact evidence;
INT-002 accepts or requests corrections. The common VM009 runner may invoke the
preflight without a build lease. Any fresh compilation/linking waits for accepted
VM008 namespace and root resource admission. Only integrators publish MAIN or run
common checks under `state/.integration.lock`. Original owner alone may close the
task after required acceptance. No physical phone actions are authorized here.
