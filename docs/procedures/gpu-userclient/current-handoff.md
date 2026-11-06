# GPU-012 current-profile source handoff

Original owner `codex-gpu-userclient-20261106-eh`, still in progress. No new claim.
Correction WT `worktrees/gpu-012-current-20261106`, branch
`team/gpu-012-current-20261106`, base accepted MAIN
`27352788619e594314a1a85a12f07e82fc279184`. Source commit
`a5dabb995db63255d4444400d75afab55ba9b39d`. This is source/code/plan readiness
for independent INT003/root review, not actual execution approval.

The physical original WT `worktrees/gpu-012-20261106` remains clean through
`de6c14afef8e2de29f06cc16ede6023ef0824f5c`. Its five source/evidence commits were
cherry-picked here as `e90a621`, `5335bfe`, `908e19f`, `b9339cd`, `2512096`.
All four C++/header files, distinct portable fixture and both original SGPU ABI
files have exactly the original bytes. The original afc5/two-job proposal and
GPUINGRESS-001 evidence are preserved as historical. VM032 remains unchanged.

Current final plan:
`artifacts/gpu-userclient/current-source-2/plan/plan.json`, SHA256
`a782839e46888e17e43acf17bd362971adea805eb1f36e091aa482417a0ee689`.
Machine binding `fixtures/public/gpu-userclient/current-source-plan.json`, SHA256
`c9a87aff87fd633f2e699b5ce4da8f8b09c45af383bf8997f76f4f05f6b3d6ea`.
Evidence `docs/procedures/gpu-userclient/current-evidence.json`, SHA256
`892974b2a9a9684c1f48f8f6f483b1a42ccd3ef1ec195ea5951bf8df13f09773`.
The source planner SHA256 is
`a0e78ec5a926283a6c9420d7e07eca0312b1a34415d0c83e868e2150e28017f1`;
current policy SHA256 is
`5a62d789a61749139c6629846bf9c4c754efef442be3ac7a8514df794f0fac61`.

The planner imports only exact physical AF193 definitions from
`worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py`, SHA256
`af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.
It reuses the accepted profile/transition/namespace primitives and validates
all real 1080 keys, 6722 namespace files and 104 IOKit rows. Current manifest
SHA256 `be02fbfc38a73831d3570e69b24277917e69efc09cd696cc853521c393edc298`,
namespace `25f22291e314445a01a4030e7db74f8cebd9a935b604eefc7b1ad9f5ee033461`,
qualification `3343a382452d05c382a15ea54e3835c3125c67c451cb586a1c3ed5a939b37174`.
Supervisor SHA256
`faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99`.
The plan carries all input paths/hashes and exact genuine recipes.

Exactly three native command proposals derive adapter/policy from genuine
IOUserClient.cpo and C dispatcher from genuine IOStringFuncs.o. They retain
original read-only cwd and every flag/order, replacing only source, -o and -MF
operands. No fake rows, SDK/header stubs, alternate dispatcher or provider were
introduced. These IOKit recipes use -nostdinc and no -idirafter: VM045's measured
APFS failure is not a measured GPU failure.

GPUINGRESS-002 source plan passes; four metadata controls reject stale two-job
budget, changed helper, mixed old/current profile and appended standard flag.
Current-image peak VmHWM 129280KiB. All 19 evidence artifact/source hashes
verify. Initial registration before the procedure existed failed with exit2;
registration then succeeded before tests. Initial pre-ancestry-check plan is
retained, with final corrected plan in source-2. No compiler, portable policy,
sanitizer, loader-tool main, archive, linker, QEMU or allocation ran. Future
actual directory `artifacts/gpu-userclient/actual-current-1` remains absent.

Read [future-execution-contract.md](future-execution-contract.md) for the bounded
actual experiment proposal: independent `gpu-userclient` component, exact
future caller/source-plan/root slot bindings, one serial compiler, 256MiB owned
RSS, global six/6GiB, stable memory admission, finite child/whole deadlines,
Landlock and verified owned-session cleanup. Future exact executor, launcher
and root allocation remain unreviewed/unbound; do not execute these argv directly.

AF193 applies 2GiB RLIMIT_AS, conflicting with normal 64-bit ASan shadow space,
and does not accept arbitrary environment. The proposed host sanitizer phase
therefore requires a future independently reviewed RSS-only child contract
with the same budget/deadline/cleanup/Landlock/exact pins, plus qualified host
ELF/runtime namespace and real negative sanitizer controls. Any shared API
change waits for VM044 ownership release, a separate reviewed task and root
allocation. VM044/VM045 final adoption is prospective: explicitly repin the
final accepted helper/profile once in a new freeze before actual execution;
no silent upgrade, old-product reuse or receipt mutation.

Typed target ABI/overrides, actual symbols/allocator metadata/imports, host
policy and sanitizer runtime, IOConnect, guest/native ABI, genuine Xclipse
backend and all hardware completion/retirement/quiescence remain unmeasured.
Default abstract provider remains NotReady. Task closure waits for accepted
actual compile and independent/integrator checks. This roadmap stage is not a
first-console dependency and gives no physical-device authorization.
