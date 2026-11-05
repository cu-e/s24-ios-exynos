# VM-027 handoff

Owner `codex-guest-exec-20261106-di`, task in_progress. Separate worktree
`worktrees/vm-027-20261106`, branch `team/vm-027-20261106`, base
`aac27cfbc0d71b34eda33ddf366c72427507ae0b`.

Implementation freeze `b4a01245383434066b9c631083c140780948e91c` contains
the owned bounded Apple DT parser, selected Scion/kernel console preflight,
independent byte-level controls and22 streamed immutable source bindings.
The README records the exact serialized format, node/property widths, consumer
traces and matching console/GIC/PCI paths. An actual source constraint is made
explicit: the shim emits `virtual-timer-intid` but the selected kernel fixes
PPI27 instead of reading that property. No upstream file or shared input changed.

VM027DT-001 was registered before execution. Source-only controls pass33 cases
and22 source hashes; actual exec-image VmHWM20,774,912 bytes under a256MiB
address-space cap. Three exact finite commands are recorded in evidence.json:
control script exit0, public CLI on owned example exit0, public CLI on historical
QEMU input FDT expected exit2. All original artifacts remain in
`worktrees/vm-027-20261106/artifacts/avf-guest-device-tree/controls-1`.
The run preceded the implementation commit; its exact code/control/pin hashes
bind the unchanged frozen implementation bytes. No compiler or guest executed.

Overall evidence remains **inconclusive**. The example is authored interface
test data, never actual runtime output. Read-only searches of VM005 and KRN031
artifacts found no raw Apple-tree dump. Historical VM005 console proves that its
real shim emitted a tree at0x4300c000 of length0x30fc, with runtime synthetic
assertions; its address0x48200000 is the input QEMU FDT. That FDT is a different
serialization and cannot meet the actual shim-data acceptance criterion.

Next action: root/integrator reviews this scoped source preparation, then may
schedule one bounded capture through the qualified source-built shim under an
explicit single-QEMU lease. Reuse existing qualified synthetic spin payloads if
appropriate, bind all source/tool/payload/options before execution, capture the
actual `boot_args.deviceTreeLength` bytes, and preserve failures. No guest lease
has been granted for this worker. A raw tree dump does not establish XNU boot,
PID1 or hardware compatibility. Compiler work additionally stays behind VM008
acceptance and root admission. No physical phone action is authorized.

Independent review, integrator acceptance and fresh MAIN common checks are
still required. Only the original owner may complete VM027 after explicit
acceptance; no taskdone, main publication or common checks occurred here.

## Prospective actual-capture phase

Original VM027 owner resumed for a bounded actual-tree capture using the existing
qualified VM005 spin payload, unchanged VM002 Image and source-built QEMU. The
prospective experiment VM027DT-002 is registered. Source commits0268123/f0ca634
prepare QMP capture and post-capture parser controls. No guest or compiler ran.

Root reviewed draft plan1 SHA256
`88fe8c05b46b87db380d954f63ba8fbe66ad02124cda4fb06d8f6450e9f13425`;
that plan and its source runner SHA256
`5d5268ddd996fb93a8940f65ce44b967d7eb632b65b3d38b5a56484da00e2685`
remain preserved in local artifacts and Git commit0268123. Root requested two
guard fixes: continuously enforce the4GiB memory floor after spawning QEMU, and
unwind SIGTERM through Python finally instead of leaving a separate guest SID.
Commit5d03516 implements these; four targeted no-guest controls pass. The prior
22 no-guest capture controls also remain preserved, without rerunning matrices.

Updated plan2 is
`artifacts/avf-guest-device-tree/capture-plan-2.json`, SHA256
`d7bf134f61520b9c56dbc6a9b31ee81f940e0a49895c0484087dd45fdec877b4`,
runner SHA256
`8320c105c6862f832491b3937089b405c1357a8954c7b1f6d7b12cbd94a29455`.
It requires a continuously matching root qemu lease ID, task VM-027 and original
owner, with one256MiB guest,512MiB aggregate RSS,3x4GiB admission one second apart,
55-second internal deadline and60-second outer timeout. Dump extent comes from
the actual shim console and must fit guest RAM0x40000000..0x50000000 and<=1MiB;
QMP stop/query-status/pmemsave/quit use only the canonical owned new capture path.
No root lease has been granted yet; do not execute until explicit root approval.
