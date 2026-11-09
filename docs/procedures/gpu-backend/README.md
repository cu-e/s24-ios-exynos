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
| Handles carry type, generation and slot and are checked against the owner | Foreign, stale or mistyped handles return `SGPU_BAD_FIELD` |
| A slot retires when its generation is exhausted | A handle value is never reissued |
| `FREE` and context destroy need no mappings or pending work | Otherwise `SGPU_LIMIT` |
| One CPU mapping per BO, and none created or removed while work is in flight | Otherwise `SGPU_LIMIT` |
| GPU VA ranges cannot overlap across all of a client's contexts | Otherwise `SGPU_BAD_FIELD` |
| `SUBMIT` validates everything before the single hardware call | A rejected submit changes no state, burns no sequence and evicts no fence |
| Write hazards need explicit dependencies on the last writer and active readers | Otherwise `SGPU_BAD_FIELD` |
| Retirement comes only from the trusted `sgpu_backend_retire` path | There is no client-asserted completion; unknown sequences change nothing |
| `WAIT` is finite and a timeout changes no state | Returns `SGPU_TIMEOUT` |
| A fault stops new work and retains all backing | Released only after retirement or `sgpu_backend_quiesced` |
| Client close keeps resources that hardware still references | Reaped on retirement, or on quiescence after a fault |
| A failed unmap or TLB flush retains the range and quarantines the device | Fails closed |

### Where the core goes beyond the oracle

The oracle models whole buffers and has no contexts or dependencies, so these rules are this
core's own decisions and have only the host tests behind them:

- A use may not exceed the access of its mapping in that context, and an IB needs a covering
  mapping with read access.
- Client close during an unresolved fault retains everything until quiescence.

## Known limits

- After `CACHE TO_GPU` clears `cpu_dirty`, a client can still write through a live CPU mapping.
  That is a data race on its own pinned buffer and the core cannot observe it.
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
