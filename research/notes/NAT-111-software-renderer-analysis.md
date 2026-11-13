# NAT-111 Analysis: Software Renderer Path Identified

Date: 2026-11-13  
Owner: claude-opus-nat111-analysis-20261113  
Evidence categories: source-review (iOS 16.5 binaries), native-device (NAT-111 libhakios hooks)

## Summary

NAT-111 (Stage C2, loader-diag-xnu-sc2-md1) confirmed SpringBoard[13] and backboardd[16] running successfully with 2 MiniIOMobileFramebuffer swaps at 234.930833s and 235.459277s. However, **no pixel differences** were detected in framebuffer (`fb_stats=[]`, `fb_pixel_diffs=[]`).

**Root cause:** CoreAnimation failed to find IOAccelerator services and fell back to software rendering. The software renderer path is working, but our current MiniIOMobileFramebuffer implementation does not handle CPU-rendered frames.

## Evidence

### NAT-111 libhakios hooks (native-device)

From `artifacts/nat-111/analysis/stage-c.json`, hakios_lines:

```
SpringBoard: no GPU draws, vibrant views are plain (the lock screen's clock is white)
no accelerated renderer; the software one will draw
render_update -> 0x1 (flags 0)
finish_update(0) -> 0
```

Key observations:
- SpringBoard PID 13 spawned at 195.803122s, alive in round 6
- backboardd PID 16 spawned at 195.214529s, alive in round 6
- 2 swaps: surface 1 at 234.930833s, surface 3 at 235.459277s
- 1 layers transition: 0x0 → 0x1 at 235.443590s
- `fb_pixel_diffs`: [] (empty)
- `fb_stats`: [] (empty)
- lsd[25] logged 448 CPU-monitor denials, 0:13.26 CPU TIME

### iOS 16.5 binaries (source-review)

SpringBoard binary from IPSW (`artifacts/ios-root/recipe/sysimage/rootfs/System/Library/CoreServices/SpringBoard.app/SpringBoard`, SHA-256 7926a1ba0b115cf45102b2c3d8e4eb7bc9c84bcf70b573d2a798690d9148059c) searches for IOAccelerator services:

```
IOAccelContext
IOAccelContext2
IOAccelDevice
IOAccelDevice2
IOAccelSharedUserClient
IOAccelSharedUserClient2
IOAccelSubmitter2
IOSurfaceAcceleratorClient
```

backboardd binary (`artifacts/ios-root/recipe/sysimage/rootfs/usr/libexec/backboardd`, SHA-256 686f26a6a7b749fd0ae30acca704022da8cb6f85b5c39a0e0e09e25ffd00d273) uses IOMobileFramebuffer and IOSurface:

```
/System/Library/PrivateFrameworks/IOMobileFramebuffer.framework/IOMobileFramebuffer
/System/Library/Frameworks/IOSurface.framework/IOSurface
_IOMobileFramebufferOpen
_IOMobileFramebufferSetDebugFlags
_IOSurfaceCreate
_IOSurfaceGetAllocSize
_IOSurfaceGetBaseAddress
_IOSurfaceGetBytesPerRow
_IOSurfaceGetHeight
_IOSurfaceGetWidth
_IOSurfaceLock
_IOSurfaceUnlock
```

### Project kernel (source-review)

Searched `src/xnu` for IOAccelerator implementations:

```sh
search_files(path="src/xnu", pattern="IOAccelerator|IOAccelDevice|IOAccelContext")
```

Result: **0 matches**. The kernel does not provide IOAccelDevice, IOAccelContext, IOAccelSharedUserClient, IOAccelSubmitter2, or IOSurfaceAcceleratorClient.

MiniIOMobileFramebuffer and MiniIOSurface exist, but no IOAccelerator backend.

## Chain of Events

1. SpringBoard starts at 195.803122s ✓
2. CoreAnimation initializes ✓
3. Looks for IOAccelerator services (IOAccelDevice, IOAccelContext, etc.) ✗
4. Services not found → falls back to software renderer ✓
5. Software renderer renders frames to IOSurface ✓
6. backboardd calls MiniIOMobileFramebuffer::swap (2 times) ✓
7. render_update returns 0x1 (likely "no hardware update needed") ✓
8. No GPU execution → no visible pixels → fb_diff=0 ✗

## What is Working

- SpringBoard lifecycle (spawn, alive for 54s of kernel runtime)
- backboardd lifecycle (spawn, alive, swap calls)
- IOSurface creation and locking (backboardd imports these symbols)
- MiniIOMobileFramebuffer swap mechanism (hook fires, no crash)
- Software renderer selection (deliberate fallback, not a crash)
- launchd console output suppression (etc/quiet partially effective, 668 lines vs 2086 in NAT-109)
- Process pruning (27 plists removed, 39 processes vs 71 in NAT-109)

## What is Not Working

- IOAccelerator service discovery (missing kernel implementation)
- Hardware-accelerated rendering path (never enters)
- CPU-rendered frame commit to visible framebuffer (render_update → 0x1, no pixel changes)
- Display output (fb_diff=0, no visible iOS screen)

## Top Missing Services

From `stage-c.json` top_failed_lookups (XPC service discovery attempts):

1. `com.apple.analyticsd` (9 lookups)
2. `com.apple.cloudd` (9 lookups)
3. `com.apple.wifi.manager` (8 lookups)
4. `com.apple.commcenter.xpc` (6 lookups)
5. `com.apple.commcenter.coretelephony.xpc` (6 lookups)

None of these are IOAccelerator services. IOAccelerator services are discovered through IOKit matching, not XPC.

## iOS 16.5 Renderer Selection (Hypothesis)

Based on libhakios output and upstream ios-apollo sweetgl=0 reference:

1. CoreAnimation checks for IOAccelerator services via IOServiceMatching
2. If IOAccelDevice or IOAccelContext match: select hardware renderer (Metal/GPU)
3. If no match: select software renderer (CPU rasterization)
4. Software renderer writes to IOSurface
5. backboardd submits IOSurface to IOMobileFramebuffer via swap
6. **Unknown:** Does swap with CPU-rendered IOSurface require different parameters or commit path?

## Minimal Next Experiments

### Option A: Stub IOAccelerator Service

Create minimal IOAccelerator IOUserClient stubs that answer basic queries:

- IOAccelDevice: GetConfig, GetSampleInfo
- IOAccelContext: Create, SetPurgeableState
- IOAccelSharedUserClient: ClientOpen, ClientClose
- IOAccelSubmitter2: SubmitDataBuffers

Goal: allow CoreAnimation to select hardware path, log exact failure point when GPU operations are attempted.

Acceptance: CoreAnimation selects hardware renderer ("accelerated renderer selected" in libhakios hooks), logs specific missing selector or capability.

### Option B: Fix Software Renderer Commit Path

Investigate why render_update returns 0x1 and fb_diff=0:

1. Hook/trace IOMobileFramebuffer user-client selectors backboardd calls after software rendering
2. Check if swap with software-rendered IOSurface requires different completion path
3. Compare MiniIOMobileFramebuffer::swap implementation against real IOMobileFramebuffer behavior (selector numbers, parameters, return values)

Goal: make CPU-rendered frames visible in framebuffer.

Acceptance: fb_diff > 0 after software-rendered swap, visible pixel changes in framebuffer dump, SpringBoard lock screen clock appears white.

### Option C: Trace Renderer Selection Earlier

Add libhakios hooks earlier in CoreAnimation initialization:

- Log environment variables checked (e.g., CA_SOFTWARE_RENDERER, CA_FORCE_GPU)
- Log IOKit service queries (IOServiceMatching calls, match results)
- Log exact point where software renderer is chosen

Goal: understand complete renderer selection logic and what triggers software path.

Acceptance: hook output shows IOServiceMatching("IOAccelDevice") returning NULL, followed by software renderer selection message.

## Recommendations

**Immediate:** Option B (fix software renderer commit path).

Rationale:
- Software renderer is already working and producing frames
- SpringBoard lifecycle is stable (54s runtime, no crash)
- Fixing commit path gives us visible iOS screen immediately
- Less kernel code to write than full IOAccelerator stubs
- Validates MiniIOMobileFramebuffer/MiniIOSurface implementation

**Later:** Option A (IOAccelerator stubs) for hardware rendering.

Rationale:
- Hardware rendering will be needed for 60Hz SpringBoard, animations, blur effects
- But software rendering proves the entire iOS userland stack works
- Software rendering can show lock screen, allow touch input testing, validate display pipeline

**Diagnostic:** Option C (trace renderer selection) if Option B fails.

Rationale:
- If software renderer commit path cannot be fixed, we need to understand why
- Option C provides ground truth for what CoreAnimation expects

## Blocked Work

- GPU-007 (Xclipse kernel backend): not needed for first frame via software renderer
- GPU-008 (hardware clear/copy/triangle): not needed for first frame via software renderer
- GPU-009 (Metal frontend): not needed for first frame via software renderer
- IOS-006 (CoreAnimation client code analysis): still valuable, but software renderer path is confirmed
- UI-002 (framebuffer + touch + iOS userland): framebuffer commit is the immediate blocker

## Unblocked Work

- Analyze MiniIOMobileFramebuffer::swap implementation (selector numbers, parameter format)
- Check real IOMobileFramebuffer behavior when software renderer is used (ios-apollo sweetgl=0 reference)
- Trace backboardd user-client calls after software rendering (libhakios hook expansion)
- Test CPU-rendered IOSurface → framebuffer commit path in isolated kernel test

## Next Step

Create NAT-112 task: fix MiniIOMobileFramebuffer/MiniIOSurface to commit CPU-rendered frames to visible framebuffer. Build libhakios hooks to trace backboardd's exact IOMobileFramebuffer user-client calls (selector numbers, parameters, return values) after software rendering. Compare with NAT-111 hooks to identify missing commit path.

Success criteria: fb_diff > 0 in next native run, visible SpringBoard lock screen (white clock) in framebuffer dump.
