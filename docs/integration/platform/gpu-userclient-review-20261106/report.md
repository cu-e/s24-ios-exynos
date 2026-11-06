# GPU-012 bounded source intake

Frozen producer tip de6c14afef8e2de29f06cc16ede6023ef0824f5c; source plan
eb688252e2d8af9c8f941662672f5430a5ec9f0bba15c6b59a0e4c66dc0a9863.
No concrete P0/P1/P2 was found in the reviewed authentication, snapshot and
session-ownership source contract. This permits continued source preparation;
it does not accept GPU-012's unmeasured compilation criterion or admit a run.

The real selected IOUserClient.cpp:4269 open path rejects a task different from
current_task and at :4314 passes that same task as both owningTask and securityID.
SGPUUserClient.cpp:70 preserves that origin, requires administrator privilege
and a true project entitlement, retains the original task, and rechecks current
identity/credentials on each externalMethod at :198. This is a restrictive
project policy, not evidence that a shipping client possesses the entitlement.
The provider default at SGPUUserClient.hpp:30 is false; both readiness checks
and admission use its lock. There is no concrete hardware backend or service/
Metal registration in this draft.

Policy.cpp:13 bounds the trusted wrapper's synchronous inband shape, sizes and
address extents before copying. Policy.cpp:72 copies request bytes into distinct
private storage, then delegates wire validation to unchanged sgpu_dispatch.
That dispatcher initializes the reply region and publishes a bounded encoded
status; the wrapper reports only actual reply bytes. Caller-controlled callback
or task authority is not decoded from SGPU messages. The synthetic callback and
identity controls remain separate fixture code, and were not compiled or run.

SGPUUserClient.cpp:139 serializes the synchronous call, owns a temporary method
reference and separate typed storage, and releases neither a hardware backing
allocation nor a completion record. Close/death/stop at :159 and :205 retain
the provider/client/task session chain when hardware quiescence is unknown.
Policy.cpp:64 refuses session-hold release with an active call or unknown proof.
The documented lack of an asynchronous drain mechanism can retain resources
indefinitely; a usable future backend still needs real bounded admission,
resource accounting and retirement evidence. Boundary completion proves none
of those hardware properties. The absent backend prevents current admission.

Independent PLATGPU-001 passed 31 local source/body/argv comparisons. Ten public
declaration bodies plus the actual IOUserClient caller matched their complete
canonical Git object identities in the previously accepted composition. All
three target recipes retain their selected flags/order and change only the
declared source/output/dependency paths, original absolute include context and
explicit C mode. The comparison read 23 frozen files, took 0.188 seconds after
three stable 4 GiB admission samples, and observed current-image VmHWM 79124 KiB.
It spawned no compiler, sanitizer, loader, archive, guest or child process.

The historical plan remains explicitly unexecutable and uses the old afc5
namespace and two-job/two-GiB proposal. Before a future compile lease, derive a
fresh reviewed execution plan with the accepted process/budget policy, actual
runtime library/tool bindings, canonical output ownership, and selected full
namespace admission; preserve old records. Typed C++ override acceptance,
actual Mach-O allocator metadata/imports, host sanitizer controls, IOConnect
credential behavior and Xclipse execution remain unmeasured. A public source
declaration match is not a private SDK/ABI, FIPS, side-channel or native result.

The original eh owner retains task progress and eventual closure. No provider
completion or first-console dependency is inferred from this independent stage.
