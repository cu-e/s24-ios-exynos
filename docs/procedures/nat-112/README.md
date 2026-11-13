# NAT-112: Fix Software Renderer Commit Path

## Summary

NAT-111 proved SpringBoard works but fb_diff=0 (no visible pixels) because MiniIOMobileFramebuffer::show() waits for GPU fence via `surfaceReady()`. Software renderer doesn't use GPU → no fence → pixels never copied to framebuffer.

## Fix

**File:** `references/hakios/xnu/files/iokit/Kernel/MiniIOSurface.cpp` (or project equivalent)

**Function:** `MiniIOSurface::surfaceReady(uint32_t timeout_ms)`

**Change:** Return true immediately if surface has no GPU fence (CPU-rendered)

### Implementation (pseudo-code)
```cpp
bool MiniIOSurface::surfaceReady(uint32_t timeout_ms)
{
    // CPU-rendered surfaces have no GPU fence → ready immediately
    if (!fGPUFence || fGPUFence == 0) {
        return true;
    }
    
    // Wait for GPU fence (existing logic for hardware-rendered surfaces)
    return waitForGPUFence(timeout_ms);
}
```

## Blocked

NAT-112 cannot be claimed due to path conflict with KRN-001 (src/xnu/ reserved).

KRN-001 blocked waiting for:
- Owner to run KRN-043 export tool
- D22AP /product tree for payload/ADT validation

## Workaround

Document fix for manual kernel rebuild by owner or when KRN-001 releases src/xnu.

## Expected Result

After fix + rebuild + native run:
- fb_diff > 0
- fb_pixel_diffs: [list of changed regions]
- Visible SpringBoard lock screen (white clock)
- libhakios hooks confirm frame commit

## Related

- NAT-111: native run that exposed this
- research/notes/NAT-111-root-cause.md: detailed analysis
- KRN-001: blocking src/xnu access
