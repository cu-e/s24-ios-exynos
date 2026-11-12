# IOS-013: can the iOS graphics stack present a first frame without a full GPU driver?

Date: 2026-11-12. Owner: `claude-nat065-20261112-ramdisk`. Evidence kind: **source-review** (static reading of the 20F66 dyld shared cache, of the donor's source and documentation, and of our own kernel source). Nothing here ran on the S24, and no iOS UI has ever been shown by this project. Reproduce the numbers with `docs/procedures/ios-013/trace_iomfb.py` (sanitized output: `docs/procedures/ios-013/iomfb_selectors.json`).

## Question

What does backboardd's frame path need from the kernel for one frame to reach the panel, which of it do our stand-ins provide, what does the donor claim it did without a GPU, and what is the cheapest observation on the S24 that tests it?

## The path of one frame (from the cache and the donor source; names are Apple's own symbols)

```
backboardd (CoreAnimation render server, QuartzCore: CA::WindowServer::Server)
  -> display object (CA::WindowServer::AppleCLCDDisplay)
      -> IOMobileFramebuffer user client   (IOConnectCall*Method, numbered selectors)
      -> IOSurface buffers                 (kernel IOSurfaceRoot user client)
  -> renderer: accelerated (Metal, else OpenGL ES context) -- or CA::WindowServer::Server::sw_renderer()
panel scan-out (kernel side, not iOS)
```

## Established (source-review)

1. **A software path exists in the Apple binary.** QuartzCore's own C strings contain `Software render` / `software render` and the switches `CA_DISABLE_RENDER`, `CA_FORCE_GENERIC_SHADERS`, `CA_FORCE_LOCAL_SERVER` (full list in the JSON). The presence of strings is not proof that the path draws a correct frame in our environment.
2. **The donor's hook addresses match our cache.** `references/hakios/userland/src/inject.c` (hakios `87bf4851`) replaces vtable slots of `AppleCLCDDisplay` (`0x1d5b44520`), `EAGLServer` (`0x1d5b45c58`) and `GLESContext` (`0x1d5b3b540`) and checks each against an expected 20F66 address before writing. Reading those slots in our shared cache gives the expected values (`0x1882f0908`, `0x1882e0c90`, `0x1882ddda4`, `0x1882c8568`, ...). This confirms the **same build** (20F66, iPhone10,3 cache), not that the hooks work.
3. **Selector census of the userland side, IOMobileFramebuffer.** In the IOMobileFramebuffer image, following branch islands to IOKit's `IOConnectCallMethod/ScalarMethod/StructMethod` entry points, the script finds **65 call sites with 63 distinct constant selectors** (3-8, 10-20, 22-31, 33-35, 41-44, 47-57, 66-69, 72-75, 77-86). Our kernel stand-in `MiniIOMobileFramebuffer.cpp` has an explicit `case` for **16** of them (3, 4, 5, 6, 7, 8, 12, 20, 28, 52, 72, 73, 74, 77, 79, 81); four more are named in its enum but fall through (25, 29, 57, 82); the other **43** are not named. The default branch of this stand-in answers **success with zeros** in the outputs and logs the selector once, so an unimplemented IOMFB call does not fail by itself: it can only stall a client that waits for a non-zero answer.
4. **Selector census of the userland side, IOSurface.** The same scan over the IOSurface image finds **48 call sites with 43 distinct selectors** through `IOConnectCallMethod` and `IOConnectCallAsyncMethod`. Here the nearest-export attribution is exact enough to read: it yields `IOSurfaceClientSetYCbCrMatrix` = 5, `...Lookup` = 4, `...SetValue` = 9, `...CreateMachPortWithOptions` = 35, `...SetOwnershipIdentity` = 44 and so on, i.e. the names agree with the stand-in's `kSurfaceMethod*` enum for every selector the enum has (a cross-check that the scan method is right). `MiniIOSurface.cpp` handles **18** (0, 4, 5, 9, 10, 11, 12, 13, 19, 20, 21, 24, 27, 33, 34, 35, 43, 44), names four without handling them (6 WrapClientImage, 7 WrapClientMemory, 22 SetTiled, 32 GetGraphicsCommPageAddress) and does not know **21** (17 SetSurfaceNotify, 18 RemoveSurfaceNotify, 25 GetTileFormat, 26 CopyDataValueBytes, 30/46-49/52 ClearDataProperties variants, 31 SetCompressedTileDataRegionMemoryUsedOfPlane, 36-38/45 accelerator custom filter, 39-42 SharedEvent, 50/51 Set/GetDataProperty). **Unlike the IOMFB stand-in, its default branch returns `kIOReturnUnsupported`** (logged once). Which of these 25 calls backboardd or QuartzCore actually make on the path to one frame is unknown until something runs; the header of the stand-in already says notifications, child surfaces, wrapping and purgeability are "not here".
   Limits of both censuses: only calls with a constant selector and a direct (or island-resolved) branch are seen; the per-export column is the nearest preceding export, so static helpers are attributed to it (for IOMobileFramebuffer almost everything lands on `IOMobileFramebufferOpen`, which tells us nothing); the meaning of selectors our stand-ins do not name is unknown to us (Apple does not publish it); IOSurface traps (`IOConnectTrap*`) are not counted.
5. **Donor statements (their documentation, not our evidence).** HakiOS says its window server draws through Metal on an Adreno GPU on a POCO X5 Pro and that, without a GPU, CoreAnimation's own software renderer draws (`inject.c`: "without a renderer the server draws with `CA::WindowServer::Server::sw_renderer()`"; OpenGL ES through Mesa only with `gl=1`/`gpu=1`). `ios-lemonadep` and `y2sios` make comparable claims (see `docs/strategy/2026-11-12-ios-critical-path.md`). All are claims about other phones and other kernels.

## Not established

* Whether `sw_renderer` produces correct pixels into an IOSurface on **our** kernel stand-ins (MiniIOSurface + MiniIOMobileFramebuffer) with Apple's real backboardd, i.e. that the 43 unnamed IOMFB selectors (answered with zeros) and the 25 IOSurface selectors the stand-in refuses (`kIOReturnUnsupported`) do not stall or abort the server.
* The scan-out fork: whether the panel follows CPU writes to the loader's framebuffer (phys `0xfa200000`, 1080x2340, stride 4320) -- NAT-069/NAT-070 in the strategy document. A frame in an IOSurface is not a frame on the panel.
* Everything about dyld, launchd and the 22 unimplemented syscalls of IOS-012 comes first: backboardd cannot start before milestone 3.

## Answer, in the vocabulary of the goal

* A first frame **without a GPU driver** is plausible on the evidence of the binary (software renderer in QuartzCore) and of the donor's claims; it is **not proven** and no promise of software rendering is made.
* The earliest blocker for it is not graphics: it is the RAM delivery of the root volume (NAT-073/074/075/076) and the dyld/launchd steps behind it. Graphics work can only be observed after a user process runs with a compatible dyld.

## Cheapest observation, and what to prepare on the host

1. **No new phone run for graphics before a dynamic Mach-O runs.** Nothing here justifies spending a native run.
2. **On the host (no phone):** drive Apple's own `IOMobileFramebuffer`/`IOSurface` client code against the stand-ins' selector handlers with the *selector census as the test vector*: the 63 + 43 selectors with the argument shapes the stand-ins log (`scalars in/out, structure in/out`) are the contract to compare. This needs a user-space harness for the kernel switch (code extraction of the stand-in's switch is own code) and is worth writing only if NAT-069/070 show the panel follows the framebuffer; otherwise display bring-up (UI-003) changes what the stand-in must do and the harness is wasted.
3. **First observation on the S24** (after milestone 2): one dynamically linked test program (not backboardd) that calls `IOMobileFramebufferGetMainDisplay`/`IOMobileFramebufferOpen`/swap begin+end against the real kernel and logs return codes and the stand-in's per-selector log lines over the existing USB log chain; the pass criterion is "every selector the stand-ins log at runtime is in the census, the IOSurface ones that return `kIOReturnUnsupported` are listed, and each reply shape matches". Then backboardd under launchd with the donor's `DYLD_INSERT_LIBRARIES` hook (milestones 4-5).
4. **Readiness criterion for milestone 4:** a user process presents a solid-colour IOSurface through the stand-in and the colour is on the panel (needs the NAT-070 answer). **For milestone 5:** backboardd stays up under launchd and its `sw_renderer` path logs a frame (donor's `finish_update` hook line) with no `CA_DISABLE_*` workaround except those justified in a note.

## Conclusion

Reuse first: the donor already contains the injection library, the kernel stand-ins and the claim that the software path is enough. What is missing here is evidence on this phone, and the next piece that produces such evidence is the root delivery, not a renderer.
