# GPU-012 executable admission source handoff

Original owner `codex-gpu-userclient-20261106-eh`, still in progress. New WT
`worktrees/gpu-012-admission-20261106`, branch
`team/gpu-012-admission-20261106`, based on accepted MAIN
`8261ce7edcfb32d5804e52f36005d76b4a27791d`. Later platform publication b000b0af
does not authorize adopting pending VM044 or the new VM045 namespace without
accepted consumer VM046. No new claim or shared-engine edit occurred.

New implementation commits:
`a82637367c4771880ff253a1451ecc54252d527d`,
`3dde251bbb2559b4f96b66ca81d60f721dbb78e6`.
The seven preceding cherry-picks copy the already frozen GPU source/plan
packet; original physical WTs remain clean at
`1f13443ed1f3a70dbf4a90199b809dfc51ae232c` and
`de6c14afef8e2de29f06cc16ede6023ef0824f5c`. Original VM032 remains unchanged.

`admission.py` SHA256
`99b6cc21ca41a6b8153e26474466f29ef0443101f274cda1f20815e21c1ea756`;
`launcher.py` SHA256
`b20a76972b5edf9a7834b19e7f07025c504afa9ff318a8126e349083f2bd530c`;
`admission-policy.json` SHA256
`df865b09a3aa883d5f6ea7ad4ca0c8485bf505c098e24fb0b511d091227f1add`.
Policy remains `execution_enabled: false`, `final_binding: null`.
Both phases refuse before actual output, budget reservation or child execution.
The launcher hashes the executor before evaluation; approval arguments cannot
select an alternate helper or bypass the missing final binding.

Machine binding `fixtures/public/gpu-userclient/admission-source-binding.json`,
SHA256 `9e2592d2a697d9fe6d8ba0e7c032958c93ccf4d34ecd3c1620c232d114b8cb2f`.
Evidence `docs/procedures/gpu-userclient/admission-evidence.json`, SHA256
`603831c2bb8de6f56a2ac614f3148fd90b53dbb14cd51630e899c0f96fbcff2f`.
Both final source phase plans are in
`artifacts/gpu-userclient/admission-controls-2/`:

- `native-plan.json`, SHA256
  `4e7e2b495fab6617859f62c9482a10db67126e5379e7273f439285c785d14e74`.
- `host-sanitizer-plan.json`, SHA256
  `cebe83ca6f39b5d7156704c6213d9624476ab3fb03660b3a933939ca0a50922d`.

Native contains exactly three genuine adapter/policy/C dispatcher compiles,
with only source/-o/-MF replacements and unchanged flags/order/genuine cwd.
Host sanitizers are an explicitly separate three-command portable C compile,
C++ fixture link and run proposal. Seven original kernel/portable/ABI files are
unchanged; added native source files are refused. No concrete provider, Apple
type/header, wire validator, GPU/Metal registration or hardware result was
fabricated. Actual outputs remain absent.

GPUINGRESS-003 passes 35 source controls in 9.975944s, with 125 artifact/source
hashes verified. Initial 32-control run/commit remain preserved. Actual launcher
CLI refuses each missing interface and changed executor; metadata controls
reject changed argv/plan hashes and invalid/inherited timers. Source mirror
rejects an additional unreviewed native file, and hardware/native-ABI flags
remain false.

Python-only process controls exercise normal completion, child timeout, whole
phase timeout, repeated SIGTERM and SIGINT through the unchanged accepted
AF193 child engine and supervisor. Two recorded fixture groups ignore TERM;
all controls complete shared cleanup with zero live survivors and no watchdog
recovery. Parent current-image VmHWM 34920KiB; maximum shared sampled controller
plus descendants RSS 44892160 bytes. Signals are sent only after fixture
readiness; repeated cancellation does not interrupt finally cleanup. No compiler,
sanitizer, portable C++ fixture, loader-tool main, archive/link, QEMU, phone or
root allocation ran.

Source-control engine is the unchanged physical
`worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py`, SHA256
`af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`;
supervisor SHA256
`faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99`.
Python controls use `admit=False`, no root allocation and no ProjectBudget
reservation. They establish no RSS-only API equivalence or actual compiler
admission. Real AF193 lacks `run_child_rss_only` and that requirement refuses.

See [admission-contract.md](admission-contract.md) for exact prospective
delegation to shared project approval/reservation, one serial 256MiB caller,
complete source-plan/caller/launcher/namespace/runtime pins, global six/6GiB,
stable admission, Landlock, finite deadlines and verified release. Final accepted
VM044/046 helper/profile and a scoped complete namespace/runtime validator are
not pinned. Host sanitizers additionally require a separately reviewed accepted
RSS-only API with all shared guarantees and no RLIMIT_AS shadow conflict.
No shared API is authored here. Repin the final accepted helper/profile once
after publication, not every intermediate implementation.

Cancellation during Popen initialization, controller SIGKILL/session escape,
future actual allocation, allocated execution/error-release retention paths and
sanitizer/runtime ELF qualification remain unmeasured. Exact final interface
review and separate root grant are required before any tool execution. Typed
target overrides/symbols/allocator/imports, portable-policy runtime, IOConnect,
actual Xclipse backend, completion/retirement/quiescence and native hardware
remain separate gates. Source/control results do not close GPU-012. This is
independent roadmap work, not a first-console prerequisite or phone permission.
