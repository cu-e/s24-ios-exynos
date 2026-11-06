# GPU-012 authenticated transport ingress

This is a source draft of a genuine selected XNU IOUserClient boundary for the
existing owned SGPU byte dispatcher. No compiler, sanitizer, IOConnect, guest or
physical-device execution has qualified this draft. It is independent roadmap
preparation and is not a first-console prerequisite.

The product contains real `IOUserClient` and abstract `IOService` subclasses
using the VM-008 public guest headers. It contains no substitute Apple classes,
SDK headers, fake GPU backend, registration personality or Metal registration.
The abstract provider has no concrete implementation; its default readiness is
false. An authenticated open against an unready provider returns
`kIOReturnNotReady`, with no client or capability reply published.

The original kernel-supplied task must equal both `securityID` and `current_task`;
the selected `IOUserClient.cpp` open path supplies the task as `securityID`.
Admission requires administrator privilege and a true project-owned
`org.s24.research.gpu.transport` entitlement. The retained original task and
current credentials/entitlement are rechecked on every entry. Transferring a
connection to another task grants no access. This is a restrictive project
policy, not an assertion that an existing iOS client carries this entitlement.

Selector zero accepts only synchronous, inband structured input/output. It
rejects unsupported argument versions/selectors, scalar counts, async ports or
references, descriptors, variable output and reserved fields. It bounds input
to 32–4096 bytes and output capacity to 120–4096, with overflow/alias rejection.
It does not reinterpret user addresses or implement a second SGPU validator.
The selected XNU MIG path supplies the trusted kernel inband buffers; invalid
kernel pointers are outside this helper's contract.

One provider lock serializes readiness, admission, synchronous dispatch, stop,
close and death. The kernel allocates typed private `Storage` with an immutable
bounded input snapshot, separate output and separate reply count. The existing
`sgpu_dispatch` performs wire validation and calls a fixed provider-owned thunk;
no external selector accepts callback, backend, task or completion authority.
Only actual reply bytes are published. SGPU error statuses stay in encoded
replies; outer authentication/shape/lifecycle failures use explicit IOReturn
mapping with a zero structured-output count.

The provider retains each admitted client as a hardware-session reference. A
method error, BAD_REPLY, synchronous return, stop, close or death does not prove
GPU quiescence. Unknown close quiescence retains the client/provider/task chain;
only a trusted future provider's proven drain can release that session hold.
The base owns no GPU memory, command buffers or completion records and never
frees those resources. An asynchronous drain/release mechanism remains a future
reviewed backend gate; retained unknown sessions can deliberately leak until
that gate exists. Backend methods must be finite and must not reenter the
provider gate. The portable policy retains an active-call reference across a
concurrent close even when modeled outside the serialized kernel adapter.

The portable policy is ordinary C++ data/functions. Its separately located host
fixture uses synthetic identities and callbacks solely to test the production
policy and snapshot function. Planned controls cover authentication/readiness,
23 argument-shape/size/alias cases, busy/close/death-equivalent lifecycle,
original input mutation after snapshot, malformed protocol and backend replies,
error/status separation, storage alias and unknown quiescence retention. The
fixture supplies no fake Apple class or vtable and never manufactures a GPU
allocation or completed fence. These controls are authored but unexecuted.

The current source-only entry point is
`src/platform/gpu/native/userclient/current_plan.py`, with the pinned policy in
`fixtures/public/gpu-userclient/current-policy.json`. It reuses the accepted
AF193 shared helper to validate the be02 manifest, 25f complete namespace,
3343 qualification, real 1080 keys and actual 104 IOKit context. Three commands
derive from genuine IOUserClient.cpo/IOStringFuncs.o recipes, replacing only
source/object/dependency operands and retaining exact flags/order and genuine
read-only cwd. The original kernel C++/portable fixture/dispatcher bytes match
the preserved physical `de6c14afef8e2de29f06cc16ede6023ef0824f5c` freeze.

`prepare.py`, `source-plan.json`, `evidence.json` and `handoff.md` preserve the
historical GPUINGRESS-001 afc5/two-job proposal. They are not current execution
instructions. Current evidence and the final plan binding are in
`current-evidence.json` and `current-source-plan.json`; see
[current-experiment.md](current-experiment.md) and
[future-execution-contract.md](future-execution-contract.md).

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  src/platform/gpu/native/userclient/current_plan.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --output /home/egor/dev/pet/s24-ios-exynos/worktrees/gpu-012-current-20261106/artifacts/gpu-userclient/new-plan \
  --actual-output /home/egor/dev/pet/s24-ios-exynos/worktrees/gpu-012-current-20261106/artifacts/gpu-userclient/new-actual \
  --experiment REGISTERED_PLANNED_SOURCE_EXPERIMENT
```

The plan includes host ASan/UBSan controls and a future pure-Python Mach-O
inspection of actual overrides, C symbols, allocator metadata and unresolved
kernel imports. The inspection supplies no stubs and establishes no link or
runtime result. Current `--control` cases reject stale budget, changed helper,
mixed old/current profile and added flags. They alter only in-memory copies.
The actual output stays absent. Host compiler versions, runtime dependencies
and sanitizer behavior remain unmeasured. Current AF193's 2GiB RLIMIT_AS
conflicts with ASan shadow memory; the future RSS-only sanitizer contract needs
separate review and authority. VM044/045 adoption is prospective and requires
one explicit final helper/profile repin before actual execution.

Real compilation and sanitizer execution require an explicit root lease and
reviewed shared budget, stable memory admission, finite commands and owned RSS
monitoring. Independent review must precede admission. Current actual results
and retained failures belong in `current-evidence.json`; compilation, host runtime,
guest, native Xclipse and phone acceptance must stay separate. Main publication
and common checks are exclusively the permanent integrator's responsibility.
