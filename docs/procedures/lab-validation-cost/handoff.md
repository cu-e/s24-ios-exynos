# LAB-003 handoff — 2026-11-06

Owner codex-lab-validation-20261106-dp atomically claimed expected LAB-003.
Worktree worktrees/lab-003-20261106, branch team/lab-003-20261106, base
4bea9b59d1d24c2f7f53f4028769b6e420be556e. Only reserved lab.py/new test/procedure
paths may change. REV-021 remains ready, unchanged.

Read task and supplied actual 24.7 s validation profile. Repeated root/path resolve
dominates 483 evidence checks/107459 within calls. Implementation is a
local per-validate filesystem view, with root resolved once and canonical-path/
file-existence reuse only until return. Capsule content/outcome/hash checks and
fresh standalone evidence calls remain intact. No cross-validation cache.

Prospective LABVAL-001 was registered and verified before each bounded child.
Frozen source/test commit 46c613041a7d43cdcd0ae1ce8bcb4b14b1019638 passes 53
focused tests (17 new +23 ledger +13 planning). A separate intentionally stale
cross-validation cache variant fails seven real mutation controls. No implementation
test/profile failure occurred. All owned children quiesced; no compiler/guest.

Actual identical MAIN snapshot profile passes: 506 evidence and 506 hash checks
unchanged; 19.751548 s ->8.596294 s, resolves 216357->101298 and lstat
1706502->1094423. Full state and all 187 generated view/index bytes match;
188-file manifests additionally include the same input registry. Snapshot SHA
3368cb5f39f2bd186517687b386666d616b0962e1d5827583b19fed8f2104d01.
Actual MAIN paths/artifacts are used for speed; output publication is confined
to owned fixture roots. Main source registry hash was unchanged during profiling.

Memory trade-off is explicit: current-image VmHWM 193156 KiB, maximum monitored
controller+child225632256 bytes, under256 MiB. Stable >=4 GiB admission and finite
cleanup hold. Inherited/cumulative rusage is labeled and not used as fresh HWM.
Root independently reviewed and accepted exact source/test scope and seven fresh
real-FS controls; capsule SHA15ffcb53f1b80e1f9c826e64422a0a2829a83d9996faa8cf288289fc64022cbf.
Root also accepted measured profile/output equality and requested no further
optimization in this patch.

Deliver final evidence/procedure commit and capsule to kernel integrator cm
(lab_worker). No MAIN publication/common checks by this executor. Integrator
bundles accepted source with reviewed VM008 namespace, publishes serially and
runs common checks. Keep LAB-003 in progress until explicit completion approval.
