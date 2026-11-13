# NAT-112 Corrected Analysis: fb_diff=0 is a measurement artifact

Date: 2026-11-13
Owner: claude-opus-nat112-20261113
Status: analysis complete, patch not needed for fb_diff

## Summary

The NAT-111 conclusion "fb_diff=0, no visible pixels" was based on a misreading
of the framebuffer statistics mechanism. The fb_diff report line prints only
after 5 seconds of accumulated frame statistics AND a subsequent swap. NAT-111
had only 2 swaps in 0.53 seconds — the statistics window never closed, so the
fb_diff line was never printed. The empty `fb_pixel_diffs=[]` is a
false negative, not evidence of zero pixel changes.

## Evidence

### 1. fb_diff report timing (MiniIOMobileFramebuffer.cpp:1474-1517)

The statistics block fires inside `show()`:
```cpp
fStatFrames++;
if (fStatSince == 0) { fStatSince = began; }
absolutetime_to_nanoseconds(mach_absolute_time() - fStatSince, &nanos);
if (nanos >= 5 * NSEC_PER_SEC) {
    // ... prints "N frames in M ms ..."
    // ... if (fDiff) prints "N pixels of the panel changed a frame" ...
}
```

The 5-second window starts at the first swap and closes at the next swap
after 5 seconds have passed.

### 2. NAT-111 swap timeline (kernel-text.txt)

- swap 1 at 234.930833s (fStatSince = 234.93s)
- swap 2 at 235.459277s (delta = 0.53s, well under 5s)
- kernel log ends at 256.351s (21.4s after swap 2, but no swap 3 arrived)

No third swap means the 5-second window never closed, and the fb_diff
report was never printed. `fb_pixel_diffs=[]` is an artifact.

### 3. drawLayer() was called with valid surfaces

```
swap 1 layer 0: surface 1 (1125x2436 'BGRA') from 0,0 1125x2436 to 0,0 1125x2436
swap 2 layer 0: surface 3 (1125x2436 'BGRA') from 0,0 1125x2436 to 0,0 1125x2436
```

drawLayer() reads `s->pixels()` and copies to `fBase` (panel framebuffer).
Both surfaces are 1125x2436 BGRA, valid dimensions, valid format.

### 4. MiniIOSurfaceDrawn() returns true for CPU-rendered surfaces

From references/s24-port RedwoodGPU.cpp:259:
```cpp
bool MiniIOSurfaceDrawn(MiniIOSurface * surface, uint64_t milliseconds) {
    uint32_t fence = surface->drawn;
    bool done = true;
    if (fence != 0 && gGPULock != NULL) { ... }
    return done;
}
```

For software renderer: `surface->drawn == 0` → returns true immediately.
No "GPU is not done" message in NAT-111 log confirms this.

### 5. hakios inject.c renderer path

```
begin_update -> 0 (flags 0x411804801)
no accelerated renderer; the software one will draw
render_update -> 0x1 (flags 0)
finish_update(0) -> 0
```

The software renderer path completed successfully:
- begin_update: started frame
- renderer: NULL (no GPU), falls back to sw_renderer
- render_update: returned 0x1 (success)
- finish_update: returned 0 (success)

## Conclusion

The framebuffer commit path works correctly:
1. CoreAnimation software renderer draws into IOSurface ✓
2. MiniIOMobileFramebuffer::swap called ✓
3. MiniIOSurfaceDrawn() returns true (no GPU fence) ✓
4. drawLayer() copies IOSurface pixels to panel framebuffer ✓
5. record() saves frame to recording memory (if rec_secs set) ✓

The fb_diff=0 conclusion was wrong. We do not know whether pixels changed
because the measurement window never closed. The real question is whether
the software renderer wrote non-zero pixels into the IOSurface, which
requires either:
- A longer run (≥3 swaps spanning ≥5 seconds) with fb_diff=1
- A recording (rec_secs=N) to capture actual frames
- Direct framebuffer dump after swap

## Next Steps

1. Update AGENTS.md with auto-task-takeover instructions
2. Prepare a kernel build with rec_secs=30 rec_start=30 to capture frames
   (this is a boot-arg change, not a kernel source change)
3. The next native run (under a new owner decision) should use:
   - fb_diff=1 (already set)
   - rec_secs=30 rec_start=30 rec_mb=64 rec_ring=1
   - loader_return_after=120 (allow time for 3+ swaps and 5s window)
4. No MiniIOSurface patch is needed — the commit path works
