# CAM-003 host camera frame preparation

Owner `codex-team-camera-host-20261105-bi`, branch `team/cam-003-20261105`.
Scope: exact pinned E1S camera source review and a bounded, independently checked
uncompressed frame/plane admission and ownership component. This is preparation
for CAM-001, with no native camera driver or capture claim.

Use only source `s24-linux` revision
`417484173abc2c4fa93e738ea82ad9f2e84911b1`. Existing shared references are read-only
with `GIT_NO_LAZY_FETCH=1` and `GIT_OPTIONAL_LOCKS=0`. Missing exact-pin text may
be fetched into this worktree's own artifact cache, retaining source path, URL,
HTTP result, Git failure, hash and source license attribution.

Before executable checks, register a fresh main-ledger experiment. Keep actual
commands, exits, dated outputs and immutable failed evidence. Use one small
compiler job and no heavy builds. No phone/ADB, camera access, ISP execution,
DMA mapping, MMIO, firmware/calibration loading or private Apple ABI assumption.
The coordinator reviews, integrates and runs shared checks before completion.

## Exact source chain

Primary repository [dx4m/android-kernel-samsung-e1s](https://github.com/dx4m/android-kernel-samsung-e1s/tree/417484173abc2c4fa93e738ea82ad9f2e84911b1),
source catalog `s24-linux`, full revision above. Source texts and acquisition
records remain in this worktree's ignored `artifacts/camera-host/` cache. Every
final witness snapshots selected source files and verifies their recorded hashes.
CAMHOST-005 additionally compares every source's actual Git blob framing/hash
with the exact pinned tree, without lazy fetch or shared Git writes, and checks
that altered bytes fail that comparison independently of HTTP provenance.

| Pinned input | What it establishes |
|---|---|
| `arch/arm64/configs/e1s_defconfig`, camera `Makefile` | E1S declares `CONFIG_PABLO_V12_1_0=y`; both config and metadata includes resolve to `v12_0_0`. A generic v13 header would be the wrong input for this configured source. This does not establish live BYH3 config equivalence. |
| [E1S camera DTS](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/media/platform/exynos/camera/vendor/mcd/esx/s5e9945-e1s_camera.dtsi) | Includes module source descriptions named GN3,3K1,IMX564_FF,3LU, with preload/pinning setfile properties. Sensor/CSIS channel declarations and PHY settings are source candidates; none identifies an actually probed or fitted sensor. |
| `is-device-csi_v4.c` | Separates frame-start/end bookkeeping from `CSIS_NOTIFY_DMA_END`; completion may carry `VB2_BUF_STATE_ERROR`. A sensor-ID response or frame interrupt alone does not prove a complete usable DMA frame, and a CSIS frame does not prove ISP output. |
| [V4L2 format implementation](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/media/platform/exynos/camera/v4l2/format.c), `include/is-type.h`, `include/is-video.h` | Real `is_fmt` and `is_frame_cfg` declarations, source format records, width/size helpers and one final metadata plane. Only the explicit uncompressed8-bit five-format subset is implemented. |
| [v12 metadata declarations](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/media/platform/exynos/camera/include/v12_0_0/is-metadata-vendor.h), `ischain/is-v12_0_0/is-config.h` | Metadata capacity is `sizeof(camera2_shot_ext)`; `CAPTURE_NODE_MAX=18`. It is not an assumed32KiB constant. Compiled64-bit declarations give30,968 bytes, stream84, shot offset6840. |
| `v4l2/vb2.c` | Metadata is the final plane. Leader/output uses `camera2_shot_ext` and checks shot magic; capture uses `camera2_stream`. The host boundary keeps all metadata opaque and does not issue either native operation. |
| `ischain/is-v12_0_0/is-subdev-mcsp.c` | MCSC adjusts crop alignment/scaling, applies separate hardware formatting/SBWC parameters and port-dependent16-byte stride behavior. Generic V4L2 buffer-size validation does not implement these steps. |
| `hardware/api/is-hw-common-dma.c` | Hardware stride/format helpers and separate compressed payload paths exist. No SBWC, packed10-bit or compressed layout is inferred or implemented here. |

Samsung camera files retain their per-file GPL-2.0 notices. The Linux UAPI header
retains its own license notice. `oracle.py` extracts vendor declarations and
functions only into ignored artifacts, preserving the full metadata header and
recording exact helper hashes. Production `frame.c` is independently authored.
The oracle wrapper and fixed-width type shim are explicitly host test premises,
not evidence of running Linux, firmware or iOS.

The E1S DTS declares sensor-slot/channel pairs0/1,1/0,2/2,3/4,4/3 as enabled;
slot5/channel1 is disabled. These are slot/routing source declarations, not five
observed fitted cameras. Some node unit-address labels differ from their `reg`
values (for example sensor0's label versus MIPI-CSI1 region); a future native
driver must never derive MMIO from the node label. No address is accessed here.

## Frame arithmetic and crop boundary

For each relevant component, source pitch is
`max(width*bitsperpixel/8, bytesperline)`. The extracted source helper calculates:

| Admitted variant | Image memory-plane sizes | Final metadata plane |
|---|---|---|
| YUYV8 | `pitch0*height` | `sizeof(camera2_shot_ext)` |
| NV12/NV21 | `pitch0*height + pitch1*height/2` in one image plane | Same |
| NV12M/NV21M | `pitch0*height`, then `pitch1*height/2` | Same |

The same FourCC can occur in multiple donor format records; the oracle selects
the uncompressed8-bit record explicitly. Source YUYV has16 bits per pixel,
while each420 component pitch uses8 bits per pixel. Image memory planes are
distinct from color components and from the metadata plane. Strides below
minimum follow the source's upward clamp; additional padding remains reserved.

All source unsigned32-bit intermediate products must be representable. The owned
boundary uses wider arithmetic to reject source wraparound, checks final sizes,
validates plane extents by subtraction and excludes full reserved-interval
overlap. Completed image lengths must reach the calculated size and fit capacity;
metadata capacity must reach the actual selected declaration's size. Metadata
payload bytes remain opaque, including a permitted zero used count.

Source `struct is_crop` and node `cropRegion[4]` describe x,y,width,height.
This component adds a conservative view policy: nonzero rectangle inside the
full frame, whole horizontal chroma groups, and whole vertical groups for420.
It rejects unsafe rectangles and does not silently realign or scale them.
The source MCSC function separately uses `MCSC_OFFSET_ALIGN`, `MCSC_WIDTH_ALIGN`,
`MCSC_HEIGHT_ALIGN`, adjusts scaling ratios, warns for non-HF output width not
multiple16, aligns HF stride when no pitch is provided, and otherwise warns on
stride misalignment. Those hardware rules remain outside this generic frame
view; its acceptance is not admission to a native MCSC configuration.

## Ownership and Stop

The descriptor describes abstract offsets within one allocation. It is an owned
in-process ABI with exact byte length, not a vendor/firmware/Apple structure.
There is no pointer, DMA map, image read or metadata interpretation in `frame.c`.
The source's FREE/REQUEST/PROCESS/COMPLETE states inform the ownership problem;
the host queue defines its own states and does not claim Samsung lock or IRQ ABI.

One serialized owner starts a fresh epoch, submits a zero-payload reservation,
receives a non-wrapping ticket, then supplies a matching completion and bounded
used counts. Complete errors or deadline expiry retain the slot; Stop cannot
make an in-flight buffer reusable. A ready frame stopped before Take is retired;
a held frame stays held until Release. Explicit quiescence acknowledgement is a
trusted external condition, and cannot establish actual hardware quiescence.
Polling and monotonic clock inputs are external; no real autonomous timeout,
watchdog or return to Android has been demonstrated.

## Validation and retained failures

Use `check.py --run NEW_NAME --source-cache CACHE_PATH` only after planning an
experiment through the primary registry. The checker records command exits,
source/snapshot hashes and actual target sections. Its donor is generated from
real source functions and declarations; the5,120 comparison vectors are not a
second handwritten implementation of the owned formulas. Exact pinned FourCCs
are compiled and compared too. The ARM oracle layout arrays are read from actual
ELF/Mach-O sections and compared byte-for-byte with the executed host oracle.

The bounded tests cover all descriptor truncation prefixes with separately
allocated short inputs, unaligned inputs, unsupported formats/depth/compression,
source arithmetic overflow, crop bounds/alignment, metadata capacity, short and
overreported image lengths, plane overlap and extents near UINT64_MAX. Lifecycle
cases cover replay, late completions after epoch changes, producer error,
Stop while in-flight/ready/held, explicit retirement, exact-boundary timeout,
clock regression and counter exhaustion.20,000 mutated descriptors supplement
specific cases. Deliberate ASan heap overflow and UBSan signed overflow must
actually terminate with their expected diagnostics.

CAMHOST-001 / `host-session1` retained a failing target probe: freestanding C++
had no `<type_traits>`. The host fixture had already passed42,915 assertions.
CAMHOST-002 / `host-session2` retained a stricter-than-needed no-imports failure:
the actual target objects referenced compiler-generated memory primitives and
the Apple target's default stack guards. The host fixture passed42,922 checks;
both target metadata layout arrays matched. The final target probe preserves
compiler-default protection and records actual memory/stack-guard imports as
kernel-runtime requirements. Native symbol resolution, guard initialization and
failure behavior remain unqualified; no complete native link or hardening claim
follows. Host sanitizers remain enabled. A draft flag to suppress target guards
was removed before executing the final experiment after coordinator review.
CAMHOST-003 records this plan amendment as inconclusive, with no target test
executed under the draft profile. CAMHOST-004 performs the corrected final run.
CAMHOST-005 / `host-session4` then passed109 runner checks,42,922 fixture
assertions,5,120 genuine donor comparisons and20,000 descriptor mutations,
including exact Git blob checks and altered-source negatives. Its peak compiler
RSS is recorded in `evidence-summary.json`, below the256MiB budget. Both deliberate
sanitizer faults exited nonzero with their required diagnostic. The final source
and implementation snapshots are immutable in that run's evidence capsule.

The read-only provider check uses accepted immutable kernel manifests
`artifacts/xnu-kernel-symbol-gaps/production-session1/compiled-objects.json` and
`symbol-providers.json`. Actual Mach-O imports are matched to current provider
objects and source/object digests, then verified with `llvm-nm --defined-only`.
The recorded provider locations are `osfmk/bcopy.o` for memcpy,
`osfmk/bzero.o` for memset and `libkern/stack_protector.o` for guard/failure
symbols. This records available compiled symbols only: no camera native link,
guard initialization, failure handling or running-kernel behavior is established.

Two exploratory urllib source fetches closed without a response; the second has
an acquisition failure record. Exact-pin curl transport succeeded without shared
Git mutation. Early oracle generation also exposed an incorrect enum assumption
for the real `IS_MAX_PLANES` macro and a missing `stdbool` shim include; partial
oracle directories remain intact. No failed source/cache/run is overwritten.

## Review handoff and native gates

The final evidence summary supplies actual outcome, command/hash witnesses and
resource maxima. Task acceptance is limited to source-qualified host admission
and ownership. Retain the claim in progress for coordinator review and shared
checks; this does not complete CAM-001.

Native work still needs fitted board/sensor and BYH3 config qualification,
power/I2C/MIPI/CSIS setup, trusted firmware/setfiles/calibration provenance,
IOMMU and cache ownership, real DMA/error/quiescence evidence, ISP processing and
target-specific user-space integration. No ID read, source declaration, source
oracle, host sanitizer or compile-only ARM object satisfies those gates.
