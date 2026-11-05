# Camera frame-plane host admission

This project-owned freestanding C component checks an owned frame descriptor
and one reserved frame's lifecycle. It performs no memory mapping, I/O, capture,
ISP work or pixel/metadata dereference. `profile.json` distinguishes source facts
from unqualified native requirements. This does not implement CAM-001.

The pinned E1S defconfig selects Pablo v12.1 with v12.0 metadata/config headers.
The independent test oracle extracts actual format size functions and complete
selected metadata declarations. It supplies fixed-width Linux types and genuine
pinned V4L2 declarations, not an operating system. Generated GPL vendor code stays
in ignored artifacts; none is copied into or linked with production `frame.c`.

The admitted subset is explicit uncompressed8-bit YUYV, NV12, NV21, NV12M and
NV21M. Other formats/bit depths/compression are rejected. YUYV has one image
memory plane; contiguous NV12/21 has one containing Y then chroma; NV12M/21M has
two independent image memory planes. Every variant has a final metadata plane.
The selected declaration gives30,968 metadata bytes,84 stream bytes and shot
offset6840 under the verified64-bit layouts. Metadata stays opaque: a zero
reported metadata payload is allowed and no camera2 contents are authenticated.

Strides follow the actual source `max(width*bpp/8,bytesperline)` calculation.
Size calculations retain the safe domain of source u32 intermediate products;
the adapter rejects overflow instead of reproducing donor wraparound. For420,
chroma height is half the even full height. Source byte pitches below minimum
are clamped upward. Allocated plane intervals must fit a single caller-declared
extent, have required capacity, and not overlap, including metadata and padding.
Completed image payloads must meet the source-required byte size. Capacities are
abstract offsets; success does not establish accessible memory or valid DMA.

The crop is a visible rectangle in the full stored frame. Bounds and nonzero
extents are checked with subtraction, and this owned policy requires whole
chroma groups. It does not rebase planes or calculate a new capture layout.
The real MCSC path additionally adjusts alignment/scaling and uses port-dependent
stride rules; this component does not qualify hardware MCSC programming.

`cam_plan` validates the complete in-process descriptor and capacities;
`cam_admit` also checks completed image payload lengths. It is an owned host
struct, not a wire protocol, vendor ABI or Apple interface. Exact input size is
checked before copying, including unaligned inputs. Callers provide accessible
buffers and independent state/output storage and check every result. Layout
outputs are zeroed on validation failure; take outputs are written on success.

Zero-initialize a queue once and serialize calls. Start needs a fresh increasing
epoch within that queue's lifetime; restart/peer identity binding is external.
Submit reserves one descriptor whose payload counts are all zero and
returns a non-wrapping ticket. Complete matches epoch/ticket and an exact-sized
three-count payload before making a frame ready. Take borrows the reservation
until release. Producer failure, malformed completion, Stop and deadline expiry
retain the slot in RETIRED; explicit trusted quiescence acknowledgement is needed
before reuse. Stop with a consumer-held frame retains that hold until release.
Neither Stop nor a quiescence API call demonstrates hardware DMA has stopped.

Clock values and quiescence acknowledgements are trusted external premises.
Deadlines have checked arithmetic and exact-boundary expiration, but polling
requires a real caller; no timer, autonomous watchdog, thread synchronization,
recovery mechanism or Android return guarantee is implemented here.

Run a registered fresh experiment with an existing exact-pin cache:

```sh
python3 src/platform/camera/host/check.py --run NEW_NAME --source-cache CACHE_PATH
```

The checker snapshots implementation and sources, verifies acquisition hashes,
builds/runs genuine donor comparisons under ASan/UBSan with deliberate fault
controls, and inspects ARM64 ELF/Mach-O objects. It uses one small compiler job
at a time and records peak RSS against256MiB. No ARM object is executed and no
Apple SDK is used. See the procedure handoff for actual outcomes and source links.
Target probes preserve compiler defaults, including stack protection. Actual
compiler-emitted `memcpy`, `memset`, `__stack_chk_fail` and `__stack_chk_guard`
imports are inspected and declared as future kernel-runtime requirements.
Native provider resolution and guard initialization/failure behavior remain
unqualified. This establishes neither a standalone native link nor hardening.
