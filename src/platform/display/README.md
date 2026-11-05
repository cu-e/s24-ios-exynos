# Display and input boundary

UI-001 supplies owned freestanding C layout arithmetic, coordinate transforms, a proposed event decoder and a logical contact-state model. It performs **no framebuffer read/write, presentation, GPU wait, IOHID dispatch, SPI/GPIO or phone I/O**. The [source audit](../../../research/notes/RES-007-display-input.md) and [profile](profile.json) separate source facts from unknown native inputs. [UI-006](../../../patches/display-input/README.md) separately corrects a real E1S donor coordinate bug.

```sh
python3 -m unittest discover -s tests -p test_display_contract.py -v
python3 src/platform/display/check.py --run unique-display-contract
```

Follow the [experiment procedure](../../../docs/procedures/ui-001/README.md) before explicit runs. Current host evidence passes 4,096 synthetic sanitizer cases and four compile-only ARM C/C++ objects. Seven unit-test groups include 2,048 Python arbitrary-precision layout cases. No Apple SDK, XNU link or ARM/runtime qualification follows from those checks.

## Layout and coordinates

Only linear, single-plane BGRA8/RGBA8 are admitted; format IDs are project values. Flags must be zero. Dimensions 1..16,384 are an explicit host policy, not panel/OS limits. Checked arithmetic computes `offset + (height - 1) * stride + width * 4` against declared capacity, without assuming unused final-row padding is mapped. Subrects must be nonempty and fully within dimensions; output is a byte interval that can include inter-row padding. No pointer is dereferenced, but the caller must independently prove the allocation, mapping, ownership, access rights and cache policy. Integer admission is not memory pinning or DMA safety.

Raw axis maxima are explicit inclusive values, 1..65,535; out-of-range coordinates are rejected rather than wrapped. Normalize by floor division to 0..65,535, mirror X/Y using flip bits 0/1, then rotate clockwise by 0/90/180/270 degrees. Pixel conversion uses separate output dimensions and maps the last normalized point to width-1/height-1. Physical E1S 1080x2340, donor logical iPhone X 1125x2436 and raw STM 4096-count axes are different spaces. These helpers assume a full-frame mapping; crop/letterboxing or calibration requires its own verified transform. Native orientation is unknown.

## Proposed input version 1

This is **not** Apple's HID ABI and **not** the donor's 24-byte redwood/hakios record. A future adapter must translate explicitly and handle partial reads before decoding. All fields below are little-endian; native struct layout is never used on wire.

| Offset | Field |
|---|---|
| 0 | Four bytes `E1HI` |
| 4 | u16 version = 1 |
| 6 | u16 total bytes = 40; exact record length |
| 8 | u32 epoch, nonzero and allocated by the trusted receiver |
| 12 | u32 sequence, nonzero; no wrap within a session |
| 16 | u64 monotonic nanoseconds, nonzero; not raw mach_absolute_time ticks |
| 24 | u16 kind: 1 down, 2 move, 3 up, 4 cancel-all |
| 26 | u16 contact slot, 0..9 |
| 28 | u32 normalized X, 0..65,535 |
| 32 | u32 normalized Y, 0..65,535 |
| 36 | u32 reserved = 0 |

Cancel-all requires slot/X/Y zero. Parsing clears output on error and rejects unknown size/version/fields. The state model requires an initial cancellation, exact next sequence for contact events, nondecreasing time and valid down/move/up transitions. Missing/replayed sequence, invalid transitions or clock rollback require resynchronization and retain active contacts as unresolved. A trusted cancellation with a newer sequence can clear them; a foreign epoch cannot replace the receiver's session. Sequence exhaustion requires a newly established session.

This model has no queue, authentication, injection permissions, clock service or HID sink. Native integration must stage validation on a copy, dispatch successfully, then commit state; failed/partial dispatch needs explicit recovery. A cancel record alone does not prove releases reached backboardd. Stop rejects new input and **retains active state**; the real adapter must successfully cancel outstanding contacts before shutdown, or report unresolved state. Reinitializing state cannot erase a consumer's held fingers. Do not use this model's fields as client-authorized reset or hardware readiness signals.

## Presentation ownership specification

These obligations are specified, not implemented by the arithmetic helpers:

| Stage | Required ownership and evidence |
|---|---|
| Admit | Authenticated surface/import handle, actual capacity/format/planes/offset/crop, producer fence, destination mapping and budget |
| Wait producer | Hold source and GPU references. On timeout, do not read or display unfinished pixels and do not declare GPU retirement |
| CPU-copy path | Read only completed producer memory with correct cache visibility. Hold source until all copy workers finish; copy completion alone is not visible panel completion |
| Direct scanout | Hold pinned source/import/DPU IOVA references until verified frame retirement; a producer fence only starts this lifetime |
| Present | Keep logical frame, software copy and actual TE/vblank/frame-done timestamps distinct. A timer callback is not hardware VSYNC |
| Retire/Stop/fault | Cancel queued work, join workers, retain active scanout/GPU references until actual quiescence; no unconditional free/reuse based on timeout or client Stop |

Native board driver UI-003, STM transport UI-004 and selected iOS16.5 surface/framebuffer/HID integration UI-005 remain missing. UI-002 qualifies actual pixels, input, Apple processes and lifecycle under the native gate. GPU-009/010 additionally require actual Metal/CoreAnimation and presentation integration; CPU framebuffer code cannot substitute for that acceptance. All C storage/state is trusted, valid, stable and nonaliasing unless explicitly supported (ui_pixel_point allows in-place conversion); caller synchronization is required.
