# VM-032 handoff

Owner: `codex-guest-exec-20261106-dn`. Primary ledger:
`/home/egor/dev/pet/s24-ios-exynos/state/lab.json`. Worktree:
`worktrees/vm-032-20261106`, branch `team/vm-032-20261106` from `aac27cf`.
Only the three acquired task boundaries are changed. No KRN-004, VM-008 input,
shared compiler/tool source, registry copy or generated planning view is edited.

The source audit covers all 104 genuine iokit recipes and 17 IIG pairs. Exact
findings, reproducible commands, source/tool/output hashes and limitations are
in `README.md`, `evidence.json`, the public source-audit fixture and existing
owned artifact reports. No lexical declaration/provider gap was found; no source
patch is justified. All actual guest implementation, type, layout, dispatch,
marshalling and selected-version interoperability gates remain explicit.

The historical 16 failed native interface compiles remain failed and are not
relabelled as guest failures. The 98 actual public `_Impl` candidates include
nine definitions supplied by IODataQueueDispatchSourceShared.h. Source-only
coverage does not establish a full SDK or selected Apple ABI. VM-008's existing
OSObject.iig representative remains bounded prior evidence.

Initial audit-1 missed the longer OSObject dispatch macro spelling. It passed
as an inventory while showing OSObject in `interfaces_without_dispatch_bridge`.
The pattern was corrected for audit-2, then audit-3 added pinned canonical
source/header provenance. All three reports remain unchanged. Initial shell
exploration also retained failed path/glob searches and one nullable-owner
read-only registry query; none changed source or registry state. The final
replay plan distinguishes these development checks from its planned run.

Next: independent review of the scoped code, fixture, reports and evidence;
then permanent kernel integrator acceptance and its fresh main common checks.
The original owner alone can close VM-032 after acceptance. Compilation of the
16 unqualified interfaces belongs to the admitted iokit object executor after
VM-008 acceptance and root lease/admission; use existing immutable recipes and
new owned object/dependency roots. Preserve the first actual diagnostic before
proposing a narrow source patch. No compiler or guest should be launched from
this source-audit handoff.
