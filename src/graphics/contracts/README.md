# Proposed Xclipse Darwin interface, version 1

This is a project-owned **operation and lifetime contract**, with an executable host oracle in [ownership.py](ownership.py). It is not a Linux ioctl ABI, Apple IOUserClient ABI, native driver or hardware emulator. There is no device I/O. Wire layouts must be separately specified and compiled in GPU-011, with actual IOKit integration in GPU-007; version 1 here identifies requirements, not a stable binary interface.

Inputs are pinned Samsung SGPU and RADV source, summarized in [RES-004](../../../research/notes/RES-004-xclipse-interfaces.md). The reviewed kernel is not proven to match the owner's BYH3 firmware. `interface.json` records operations and unresolved inputs. Individual donor notices remain applicable; no Linux implementation is copied into this model.

## Pages and backing ownership

Samsung's `amdgpu_gart.h` defines GPU pages as 4096 bytes. CPU translation granule, XNU advertised VM page size, GPU PTE granule and shared-surface allocation alignment are separate quantities. Query and report all of them. Do not derive any from the phone's marketing name or Android `getpagesize()`.

The prepared E1S source does not define `__ARM_16K_PG__`, so `proc_reg.h` selects **4 KiB hardware translation granules** absent a build override. However `arm_init.c` advertises **16 KiB VM pages when boot_args.memSize exceeds 1 GiB**, otherwise ARM_PGSHIFT; `vm_param.h` uses that runtime value unless its 16 KiB compile-time path applies. The pinned loader caps a successfully DT-selected window at 512 MiB, but its fallback starts with supplied memory size. Therefore the current source implies a 4 KiB advertised size on that capped branch; it does **not** justify assuming every boot or future larger window uses 4 KiB. There is no compiled native kernel or runtime confirmation. GPU-007 must record build flags, actual boot memory window and runtime page query before enabling mappings.

The oracle tests CPU allocation granules of both 4096 and 16384 with GPU granules of 4096. For a 1-byte BO on a 16 KiB CPU policy, charge 16 KiB backing, expose at most one 4 KiB GPU range and retain all backing until every mapping and submission releases it. Never pack unrelated owners into the unused 12 KiB. A real allocator must zero full backing before CPU exposure, pin it, enforce isolation and account for pools/fragmentation; the oracle allocates no actual memory and tests only aggregate accounting. GPU-page mapping beyond rounded logical BO size is rejected even when extra CPU backing exists.

## Required operations

| Operation | Required behavior in the native implementation |
|---|---|
| Query/version | Explicit contract version, validated firmware/chip profile, CPU hardware/VM and GPU page sizes, supported features, limits, cache policy and reset epoch. Unsupported values fail closed. Do not expose raw MMR reads as inventory. |
| Client/context | Authenticated per-process ownership, opaque handles with generation/epoch, bounded queues and quotas; no user-provided physical address or kernel pointer. Validate engine, IB and dependency limits. |
| Allocate/free | Zeroed pinned backing, per-client plus device-wide budgets, separate constrained-pool accounting and reserved system headroom. Free requires no CPU/GPU mappings, imports or outstanding submissions. |
| CPU map/unmap | Checked offset/length and rights, actual CPU-page alignment, no cross-owner subpage exposure. Mapping existence does not grant concurrent CPU access during GPU work. |
| GPU VA map/unmap | 4 KiB PTE ranges inside BO and queried per-context VA window; checked arithmetic, no overlap; validated permissions and memory type. Complete page-table writes/TLB invalidation before dependent work. Retain backing through VM-update fences. |
| Cache visibility | Explicit CPU-write→GPU-read clean/release and GPU-write→CPU-read invalidate/acquire, including imported surfaces. Resolve architecture-specific cache/TLB barriers; a fence alone is not cache maintenance. |
| Submit | Copy/validate bounded IB descriptors, BO references and dependency lists atomically before enqueue; serialize writes or require valid dependencies; reject cycles/stale imports. Pin all referenced backing before doorbell. |
| Fence/wait | Opaque timeline/context epoch and error state; finite waits and process cancellation. Timeline signal/IRQ evidence must establish retirement. Timeout or Stop never establishes completion or returns backing to the allocator. |
| Stop/fault | Stop accepting work, retain in-flight references. Quarantine after fault; free only after observed retirement or proven DMA/queue quiescence. Reset request, process death and link loss are not proof. Recovery is a separate device experiment. |
| Sharing/presentation | Authenticated IOSurface export/import, format/stride/plane/modifier rights, reference transfer and producer/consumer fences across processes. Hold display references until scanout release. Metal, CoreAnimation and DECON/DSIM acceptance remain separate. |

An Android `.so` cannot supply this backend on XNU. The pinned RADV winsys uses libdrm BO/VA/context/CS and DRM syncobj/sync-file operations. An adaptation may replace the winsys or the `ac_drm` boundary; either needs an implemented native memory, queue, interrupt, firmware, power and fault backend. No physical MMIO address in a donor becomes an operational input without firmware/device-map validation.

## Host oracle and test boundary

```sh
python3 -m unittest discover -s tests -p test_gpu_contract.py -v
```

Seven scenario groups check 4/16 KiB accounting, foreign/stale handles, failed multi-BO validation, VA overlap/overflow/alignment, cache transitions, two-reader lifetime, write hazards, finite wait bounds, Stop, fault quarantine and explicit mock quiescence. Handles never recycle within a model instance. VA bounds and budget are explicit synthetic inputs, not board constants.

`backend_complete`, `backend_fault` and `backend_quiesced` inject trusted **mock** observations. They must never become userspace requests that let a client declare its own DMA finished. `wait` evaluates a supplied observation with a bounded timeout value; it does not sleep, emulate progress or implement a real deadline/watchdog. Python objects are not a security boundary and this model is single-threaded.

The oracle does not validate executable command streams, handle ordered dependency graphs, implement actual CPU mapping/cache maintenance, enforce access against CPU pointers, close processes, share IOSurfaces, load firmware, program IRQ/power or present frames. Those are explicit native requirements. Passing these tests establishes contract behavior only.
