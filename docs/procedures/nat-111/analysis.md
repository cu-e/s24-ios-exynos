# NAT-111 Analysis: Software Renderer Path

## Finding

NAT-111 (Stage C2) confirmed SpringBoard[13] and backboardd[16] running successfully with 2 MiniIOMobileFramebuffer swaps at 234.930833s and 235.459277s. However, **no pixel differences** were detected in framebuffer (`fb_stats=[]`, `fb_pixel_diffs=[]`).

libhakios.sb.dylib hooks revealed the critical issue:

```
SpringBoard: no GPU draws, vibrant views are plain (the lock screen's clock is white)
no accelerated renderer; the software one will draw
render_update -> 0x1 (flags 0)
```

## Root Cause

CoreAnimation failed to find an **accelerated renderer** and fell back to **software rendering**. The chain works as:

1. SpringBoard starts ✓
2. CoreAnimation initializes ✓
3. Looks for IOAccelerator service ✗ (not found)
4. Falls back to software renderer ✓
5. Software renderer renders to IOSurface ✓
6. MiniIOMobileFramebuffer::swap called ✓
7. But: render_update returns 0x1 (likely "no-op" or "CPU render")
8. No GPU execution → no visible pixels → fb_diff=0

## Evidence

From `artifacts/nat-111/analysis/stage-c.json`:

- `hakios_lines` entry 36: `"no accelerated renderer; the software one will draw"`
- `hakios_lines` entry 37: `"render_update -> 0x1 (flags 0)"`
- `hakios_lines` entry 13: `"SpringBoard: no GPU draws, vibrant views are plain (the lock screen's clock is white)"`
- `fb_swaps`: 3 events (swap 1 surface 1, layers 0x0→0x1, swap 2 surface 3)
- `fb_pixel_diffs`: `[]` (empty)
- `fb_stats`: `[]` (empty)

## Missing Services

Top failed service lookups (from `stage-c.json`):

1. `com.apple.analyticsd` (9 lookups)
2. `com.apple.cloudd` (9 lookups)
3. `com.apple.wifi.manager` (8 lookups)
4. `com.apple.commcenter.xpc` (6 lookups)
5. `com.apple.commcenter.coretelephony.xpc` (6 lookups)

None of these are IOAccelerator/Metal services, but the absence of GPU-related services is notable.

## CPU Contention

lsd[25] consumed 0:13.26 CPU TIME over 45s with 448 CPU-monitor escape denials. SpringBoard accumulated 0:05.24→0:05.51 CPU TIME between rounds 3-5, but stopped swapping after 235.459277s.

## Next Investigation

IOS-006 (blocked, depends on IOS-005) must analyze:

1. **What IOAccelerator/Metal services does iOS 16.5 CoreAnimation require?**
   - Check shared cache for IOAccelerator/IOSurface/Metal client code
   - Trace backboardd's user-client connections

2. **What selectors does IOMobileFramebuffer need beyond swap?**
   - Analyze backboardd binary for IOMobileFramebuffer usage
   - Check if GPU descriptor/address registration is missing

3. **Does iOS 16.5 have a CPU renderer path, and what triggers it?**
   - Disassemble CoreAnimation's renderer selection
   - Check environment variables or boot-args that force CPU rendering

4. **Why does render_update return 0x1?**
   - Hook/trace IOMobileFramebuffer::render_update implementation
   - Check if 0x1 means "software render complete, no hardware update"

## Proposed Minimal Experiments

### Option A: Stub IOAccelerator Service
Create a minimal IOAccelerator IOUserClient that answers basic queries, allowing CoreAnimation to select hardware path (even if GPU operations fail).

### Option B: Trace Renderer Selection
Add libhakios hooks earlier in CoreAnimation initialization to log:
- Environment variables checked
- Service lookups before renderer selection
- Exact point where software renderer is chosen

### Option C: Force Hardware Path
Patch CoreAnimation to skip software renderer check and attempt hardware path, logging exact failure point.

## Conclusion

The swap calls are **not proof of GPU rendering**. SpringBoard is working correctly, but iOS 16.5 CoreAnimation cannot find the required GPU services and falls back to software rendering, which produces no visible framebuffer output in our current MiniIOMobileFramebuffer implementation.

The blocker is now clearly **GPU service discovery**, not SpringBoard lifecycle or basic framebuffer access.
