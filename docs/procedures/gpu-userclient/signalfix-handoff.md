# GPU-012 launcher restoration correction

Original owner `codex-gpu-userclient-20261106-eh`, still in progress. New WT
`worktrees/gpu-012-signalfix-20261106`, branch
`team/gpu-012-signalfix-20261106`, parent
`372535dfe53b10b6350e7f9c2702062aac5b61c9`. Physical parent WT, `1f13443`,
`de6c14a` and VM032 witnesses remain unchanged. No new claim or helper adoption.

Source correction commit `212c28f262689f66d5370f74cc41408a4cbcc963`.
Only the `guarded` finally AST changes in the launcher. SIGALRM/SIGTERM/SIGINT
are blocked before timer and handler restoration; the exact mask returned by
that temporary block is restored last. Pending signals then reach the caller's
restored handlers. No pending signal is consumed or unconditionally unblocked.

INT003's actual retained P2 counterexample is
`worktrees/int-platform-20261106/docs/integration/platform/gpu-admission-review-20261106/runs/source2/evidence.json`,
SHA256 `75abfded0161bc78cf3ca2521eca476801993995c88f389b97c6c5b4b2073d1c`.
It sends actual first SIGINT immediately before restoring ALRM: b20a7697
escapes with Cancelled and leaves all three custom handlers installed. That
failure and the original 35/process controls are preserved, not overwritten
or repeated. Independent exact-source correction acceptance is pending.

New launcher SHA256
`ea82de7bb04578166bfec433bcbdaf1ed01194b3e02be8b3ca274f9b04ab1afc`.
Executor remains `99b6cc21ca41a6b8153e26474466f29ef0443101f274cda1f20815e21c1ea756`;
policy remains `df865b09a3aa883d5f6ea7ad4ca0c8485bf505c098e24fb0b511d091227f1add`,
with execution disabled and final binding null. Seven kernel/portable/ABI inputs,
all old process fixtures, physical AF193 and supervisor hashes remain unchanged.

Machine binding `fixtures/public/gpu-userclient/signalfix-source-binding.json`,
SHA256 `13f2dbb2e882711a7fee961a40717fc30494ac43ac0ca211ba6dfd8e33a9fc69`.
Evidence `docs/procedures/gpu-userclient/signalfix-evidence.json`, SHA256
`7c652f3e150f6e16b847b50b40e33913263abe2d1b92397876b81607242c3656`.
Focused report and AST scope proof are in
`artifacts/gpu-userclient/restoration-1/`. Re-pinned source-only phase plans:

- Native SHA256
  `e402deeaff536b317f8284b918481131732f3cd235701a9a2974a29029256345`.
- Host-sanitizer SHA256
  `3c7e659de68dfb321ca20fac993804752f179d9781f76e8e4982a2e082a5632e`.

GPUINGRESS-004 passes 71 focused checks in 0.0625695 seconds; current-image
VmHWM 30176KiB. Eight real-signal cases cover normal nonempty mask, first INT
at handler restoration, repeated ALRM/TERM/INT there, first TERM before timer
reset, callback first/repeated cancellation, caller-blocked/preexisting pending
INT and caller default KeyboardInterrupt semantics. All handlers/timer/mask are
restored. Caller-owned pending INT remains pending until the caller unmasks it;
default KeyboardInterrupt propagates after full restoration. Both disabled
phase exceptions also restore state, and future actual outputs stay absent.
All 23 recorded artifact/source hashes verify.

This proof invokes no child/process engine, compiler, sanitizer, loader tool,
archive/link, QEMU, root allocation or phone. The original process matrix is
reused without another run. Standards permit pending signals to coalesce;
proof covers pending ownership/delivery, not one callback per send.

Final accepted VM044/046 helper/profile still requires one explicit later
repin. Accepted scoped input/runtime validator and RSS-only API are still
missing. Popen-initialization cancellation, controller SIGKILL/session escape,
actual root budget, target compilation, host sanitizer/policy runtime,
IOConnect, Xclipse backend and all native/hardware gates remain unqualified.
Do not execute these plans or close GPU-012 from this source correction.
