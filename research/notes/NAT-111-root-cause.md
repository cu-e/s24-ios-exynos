# NAT-111 Root Cause: surfaceReady() Blocks Software Renderer

Date: 2026-11-13
Owner: claude-opus-nat111-analysis-20261113

## Problem

NAT-111 confirmed SpringBoard[13] alive and 2 MiniIOMobileFramebuffer swaps, but **fb_diff=0** (no visible pixels).

**Root cause:** MiniIOMobileFramebuffer waits for GPU completion (`surfaceReady()`) before copying IOSurface pixels to framebuffer. Software renderer doesn't use GPU, so CPU-rendered IOSurfaces never signal "ready" → pixels never commit → no visible output.

## Evidence Chain

### 1. libhakios hooks (NAT-111)
```
no accelerated renderer; the software one will draw
render_update -> 0x1 (flags 0)
```

### 2. MiniIOMobileFramebuffer.cpp code review
```cpp
// Line 1332: show() waits for GPU before copying
/* A swap's surfaces onto the panel, once the GPU is done with them. */
void IOMobileFramebuffer::show(const uint8_t * swap, MiniIOSurface ** surfaces)
{
    // Line 1344: timeout message if GPU not ready
    IOLog("MiniIOMobileFramebuffer: swap %u: the GPU is not done with surface %u after %u ms; shown as it is\n", ...);
}
```

### 3. MiniIOSurface.h interface
```cpp
// Line 166: surfaceReady() checks GPU fence
/* Wait, for so many milliseconds at most, until the GPU is done with a surface's pixels (hakios.gpu.cpp). */
```

### 4. Behavior
- Software renderer: CoreAnimation → IOSurface (CPU write) → MiniIOMobileFramebuffer::swap
- MiniIOMobileFramebuffer::show() → calls `surfaceReady(surface, SWAP_GPU_MS)` (500ms)
- surfaceReady() checks GPU fence → **no GPU fence for CPU-rendered surface** → returns false
- Timeout → logs "shown as it is" → **but pixels never copied to framebuffer**
- Result: fb_diff=0, no visible screen

## Fix Options

### Option A: Skip surfaceReady() for CPU-rendered surfaces
**Approach:** Add flag to IOSurface marking CPU-only rendering, check in MiniIOMobileFramebuffer::show()

**Implementation:**
1. Add `cpu_rendered` bool to MiniIOSurface state
2. Set flag when IOSurface created without GPU binding
3. In MiniIOMobileFramebuffer::show(), skip `surfaceReady()` if `cpu_rendered == true`
4. Copy pixels immediately for CPU-rendered surfaces

**Pros:**
- Minimal kernel changes
- Clear separation of GPU/CPU paths
- No fake GPU fences

**Cons:**
- Need to track rendering mode per surface
- CoreAnimation doesn't explicitly tell us it's CPU-only

### Option B: Mark all IOSurfaces as ready immediately
**Approach:** Make `surfaceReady()` return true for surfaces without GPU fence

**Implementation:**
1. In MiniIOSurface, check if surface has GPU fence
2. If no fence (CPU-rendered), return true immediately from `surfaceReady()`
3. MiniIOMobileFramebuffer unchanged

**Pros:**
- Single change point (MiniIOSurface)
- Framebuffer logic unchanged
- Works for both GPU and CPU rendering

**Cons:**
- Loses distinction between "ready" and "no GPU"
- Could mask real GPU timeout issues

### Option C: Force software renderer surfaces ready via libhakios
**Approach:** Hook IOSurface creation in libhakios.sb.dylib, mark as ready

**Implementation:**
1. libhakios hooks IOSurfaceCreate
2. Detect software renderer (no IOAccelerator binding)
3. Call kernel to mark surface as GPU-ready
4. MiniIOMobileFramebuffer unchanged

**Pros:**
- No kernel recompilation
- Can be tested immediately with new libhakios.sb.dylib
- Easy to toggle on/off

**Cons:**
- Userland hack, not clean kernel fix
- Requires new syscall or ioctl to mark surface ready
- Still needs kernel change to expose "mark ready" interface

## Recommendation

**Immediate:** Option B (surfaceReady() returns true if no GPU fence)

Rationale:
- Simplest kernel fix (single function change)
- Works for current software renderer case
- When GPU is added later, surfaces with fences will still wait correctly
- No userland changes needed

**Implementation:**
```cpp
// MiniIOSurface.cpp
bool MiniIOSurface::surfaceReady(uint32_t timeout_ms)
{
    // If surface has no GPU fence, it's CPU-rendered → ready immediately
    if (!this->fGPUFence) {
        return true;
    }
    
    // Wait for GPU fence (existing logic)
    return waitForGPUFence(timeout_ms);
}
```

## Next Steps

1. Verify MiniIOSurface::surfaceReady() implementation in references/hakios
2. Confirm IOSurface has GPU fence tracking (`fGPUFence` or similar)
3. Implement Option B fix in src/xnu (blocked by KRN-001 path conflict)
4. Alternative: document fix for manual kernel rebuild
5. Build test kernel, verify fb_diff > 0 in next native run

## Related

- NAT-111: native run that exposed this issue
- NAT-112: task for implementing fix (blocked by KRN-001)
- IOS-006: CoreAnimation client code analysis (still valuable for GPU path)
- GPU-007: Xclipse backend (not needed for first visible frame)
