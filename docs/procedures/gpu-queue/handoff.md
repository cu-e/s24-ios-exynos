# GPU-015 handoff

Owner: `claude-gpu-timeline-20261110-g15`. Branch `team/gpu-015-timeline-20261110`, based on GPU-013. Code commit `36e9f07e28facf36dc3fe821e47e77e78d70d779`.
Evidence category: host-test. Nothing ran on a GPU, on the phone or under QEMU.

The module and its rules are in `src/platform/gpu/native/queue/sgpu_timeline.h`.

| Check | Result |
| --- | --- |
| `check.py --run check-003` | 46 tests under ASan/UBSan and TSan; 130 mutants killed, 0 survivors, 2 documented as equivalent |
| ARM64 Mach-O object, host clang, freestanding | no undefined symbols; not the kernel flags and not an XNU build |

## What a real hardware layer must supply

- `sgpu_tl_hw.start` and `read_counter`, with a coherent counter read and refusal only for device-level reasons.
- A mapping from `hw_context` to a ring, because `sgpu_be_ops.submit` has no ring argument.
- A call to `sgpu_timeline_note_fault` from any `vm_unmap` or `tlb_flush` failure.
- Thread context for observe, tick, fault and quiesced, with a periodic tick.
- Ring depth and counter width from a validated chip profile.

## Open

- Whether hardware completes each ring in order, and whether counters are safe to read while a ring runs, are unmeasured.
- GPU-007, GPU-008 and GPU-012 stay open. GPU-007 depends on KRN-001, held by another owner.
