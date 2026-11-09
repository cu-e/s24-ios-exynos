# GPU-013: portable Xclipse backend core

Evidence category: host-test. Nothing here ran on a GPU, on the phone or under QEMU.

## What exists

`src/platform/gpu/native/backend/sgpu_backend.{h,c}` is the object-lifetime and validation layer
behind the `sgpu_abi.c` dispatcher. It implements alloc, free, contexts, CPU and GPU mappings,
cache transitions, submit, fences, wait, stop, hardware-fault quarantine and client close.

Every hardware effect goes through `struct sgpu_be_ops`. The core has no register programming,
firmware, power, ring or interrupt code and no invented hardware constants. No implementation of
that ops table for real hardware exists yet. The only implementation is the fake in the host test.

## What it refuses

Without `config.profile_verified` the core answers `QUERY` with zeroed profile fields and returns
`SGPU_UNSUPPORTED` for everything else, including `STOP`. Nothing in this tree sets that flag for
real hardware. Setting it requires a validated firmware and chip profile, which GPU-007 is
responsible for and which does not exist.

## Rules, and the oracle they follow

The behaviour follows the GPU-006 lifetime oracle in `src/graphics/contracts/ownership.py`.

| Rule | Result |
| --- | --- |
| Logical size rounds to the 4K GPU page; charged backing rounds to the CPU VM page | Budget failures return `SGPU_LIMIT` |
| Each client has its own byte budget and object quotas; `QUERY` reports the client budget | Over budget or quota returns `SGPU_LIMIT` |
| Handles carry type, generation and slot and are checked against the owner | Foreign, stale or mistyped handles return `SGPU_BAD_FIELD` |
| A slot retires when its generation is exhausted | A handle value is never reissued |
| `FREE` and context destroy need no mappings or pending work | Otherwise `SGPU_LIMIT` |
| One CPU mapping per BO, and none created or removed while work is in flight | Otherwise `SGPU_LIMIT` |
| GPU VA ranges cannot overlap across all of a client's contexts | Otherwise `SGPU_BAD_FIELD` |
| `SUBMIT` validates everything before the single hardware call | A rejected submit changes no state, burns no sequence and evicts no fence |
| Write hazards need explicit dependencies on the last writer and active readers | Otherwise `SGPU_BAD_FIELD` |
| Pending dependencies are passed to `ops.submit` | The hardware path must not start the work before they retire |
| A dependency that fails while its dependents are in flight fails them too, transitively | They report `RETIRED_ERROR` with that reason even if hardware retires them cleanly |
| Retirement comes only from the trusted `sgpu_backend_retire` path | There is no client-asserted completion; unknown sequences change nothing |
| `WAIT` is finite and a timeout changes no state | Returns `SGPU_TIMEOUT` |
| A fault stops new work and retains all backing | Released only after retirement or `sgpu_backend_quiesced` |
| `FREE`, `GPU_UNMAP` and context destroy wait for quiescence during a fault | Otherwise `SGPU_STOPPED` |
| Client close keeps resources that hardware still references | Reaped on retirement, or on quiescence after a fault |
| A failed unmap, or a failed TLB flush on map or unmap, retains the range and quarantines the device | Fails closed; a reap stops at its own failure |

### Where the core goes beyond the oracle

The oracle models whole buffers and has no contexts or dependencies, so these rules are this
core's own decisions and have only the host tests behind them:

- A use may not exceed the access of its mapping in that context, and an IB needs a covering
  mapping with read access.
- Client close during an unresolved fault retains everything until quiescence, and explicit
  teardown is refused for the same period.
- Quotas divide each table across all 16 client slots: 64 BOs, 4 contexts, 16 CPU mappings, 256 GPU
  mappings and 32 fences per client.
- A client evicts only its own retired fences or a closed client's, and only replaces its own at
  its quota.
- A BO with a writable CPU mapping cannot hold an IB. `src/platform/gpu/abi/README.md` requires
  that userspace cannot change an IB after validation.
- Only a whole-buffer `CACHE` clears a dirty flag. A partial one reaches the cache and changes no
  state.

## Known limits

- After a whole-buffer `CACHE TO_GPU` clears `cpu_dirty`, a client can still write through a live
  CPU mapping of a data BO. That is a data race on its own pinned buffer and the core cannot
  observe it.
- IB contents are not validated. Nothing stops a job writing to an IB through a writable GPU
  mapping in its own context, so a future content validator must also require read-only IB mappings.
- Per-client table shares are small for a real graphics stack. They give a hard guarantee between
  live clients for table slots only, and may need raising with the tables once real workloads are
  measured.
- The byte budget gives no such guarantee on its own. `init` requires only
  `client_budget_bytes <= budget_bytes`, so clients can exhaust the device budget unless the trusted
  configuration sets `client_budget_bytes * 16 <= budget_bytes`. Nothing in this tree chooses that
  value for real hardware.
- A closed client's zombies are outside the quota guarantee, because they stay until the hardware
  stops using them.
- A slot whose generation is exhausted stays dead until the backend is initialised again.
- Retirement order is trusted. If a hardware path retired work before something it waits for, hazard
  tracking would be wrong, though lifetime references would not.
- Validation scans fixed tables under one lock. The worst case for a submit is about 300K table
  checks. That has not been measured on a device and may need indexing.
- The waiter-blocks-eviction path has no direct test. It needs a retirement landing while a waiter
  is still asleep, which the single-threaded fake cannot arrange.
- Bounds such as 1024 BOs and 512 fences are project choices, not measured limits of any GPU.

## How to check it

```sh
python3 src/platform/gpu/native/backend/check.py --run NAME
python3 fixtures/public/gpu-backend/compile_arm64.py --run NAME
```

`check.py` builds the dispatcher tests under ASan/UBSan and TSan, then applies single-line mutations
to the core and fails if any mutant passes. `compile_arm64.py` reuses the argv recorded for a real
kernel object, changing only the source, output, depfile and one include directory.

Neither script may run while a heavy lease is active: the budget supervisor treats any
unregistered compiler whose working directory is inside the project as a violation.
