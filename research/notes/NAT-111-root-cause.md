# NAT-111 Root Cause Analysis (corrected 2026-11-13)

Date: 2026-11-13
Owner: claude-opus-nat112-20261113
Status: Corrected — earlier fence hypothesis disproved by NAT-112 analysis

## Correction Notice

An earlier version of this document (by claude-opus-nat111-analysis-20261113) claimed
that `surfaceReady()`/`MiniIOSurfaceDrawn()` was the root cause of missing pixels, with
fb_diff=0 as evidence. Both claims were wrong:

1. `MiniIOSurfaceDrawn()` returns `true` immediately when `surface->drawn == 0`
   (the software renderer case). No GPU fence block. This is confirmed in
   `references/s24-port/xnu/hackios/files/iokit/Kernel/RedwoodGPU.cpp`:
       bool MiniIOSurfaceDrawn(MiniIOSurface * surface, uint64_t milliseconds) {
           uint32_t fence = surface->drawn;
           bool done = true;
           if (fence != 0 && gGPULock != NULL) { ... }
           return done;
       }
   For CPU-rendered surfaces: fence == 0 → returns true immediately.

2. `fb_diff=0` was never measured — the string "N pixels of the panel changed a frame"
   prints only after 5 seconds of accumulated stats AND a next swap. NAT-111 had 2
   swaps in 0.53 s; the window never closed. `fb_pixel_diffs=[]` is a false negative
   (measurement artifact, not evidence of zero pixel changes).

The kernel patch in `patches/e1s-graphics/0001-software-renderer-fence-stub.patch` was
drafted based on this incorrect analysis and is not needed.

## What NAT-111 established

- SpringBoard[13] stayed alive until kernel return (~195 s after boot)
- backboardd[16] executed two MiniIOMobileFramebuffer::swap calls (234.93 s, 235.46 s)
- drawLayer() was called with valid surface 1 (1125×2436 'BGRA') for both swaps
- MiniIOSurfaceDrawn() returns true for CPU-rendered surfaces (surface->drawn == 0)
- Software renderer path completed: begin_update → render_update(0x1) → finish_update(0)
- No "GPU is not done with surface" timeout in NAT-111 log
- Text console disabled: `fGraphics = true` (PE_initialize_console(NULL, kPEGraphicsMode))

## What is NOT established

- Whether the software renderer wrote non-zero pixels into the IOSurface
- Whether drawLayer() read non-zero pixels and copied them to the panel framebuffer
- Whether the physical display was updated (no visual observation, no recording)

## fb_diff=0 is NOT established

The fb_diff statistics mechanism (MiniIOMobileFramebuffer.cpp:~1474):

    fStatFrames++;
    if (fStatSince == 0) { fStatSince = began; }
    absolutetime_to_nanoseconds(mach_absolute_time() - fStatSince, &nanos);
    if (nanos >= 5 * NSEC_PER_SEC) {
        // prints "N frames in M ms ..."
        // if (fDiff > 0): prints "N pixels of the panel changed a frame"
    }

NAT-111: swap 1 at 234.93 s, swap 2 at 235.46 s (Δ = 0.53 s). The 5-second window
started at swap 1 and needed swap 3 to close. Swap 3 never came. The statistics block
never executed. `fb_pixel_diffs=[]` means the line was never printed, not that zero
pixels changed.

## Open question

Whether the software renderer writes non-zero pixels into the IOSurface. The commit
path (surface → drawLayer() → fBase) is confirmed working. The pixel content is unknown.

## How NAT-113 resolves it

NAT-113 adds `rec_secs=30 rec_mb=64 rec_ring=1` to capture actual frames.
The recording format (RWREC003) stores width×height×3 bytes per frame with timestamps.
One frame with any non-zero pixel confirms the render path produces output.
All-zero pixels confirm the render path is broken (focus on IOSurface lock/write/unlock).

## Related

- NAT-112: analysis task that corrected this document (done, pass)
- NAT-113: next native run with framebuffer recording
- docs/procedures/nat-113/decision-draft.md: proposed experiment
- research/notes/NAT-112-corrected-analysis.md: authoritative corrected analysis
