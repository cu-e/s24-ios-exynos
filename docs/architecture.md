# Research architecture

The reference target is SM-S921B/e1s/Exynos 2400. The owner's phone was confirmed to match through ADB on 2026-11-05; see the [device baseline](../research/notes/DEV-001-profile.md).

## Three execution environments

1. **Host:** pinned sources → build → static image/ADT validation → synthetic tests. No phone required.
2. **Android userland:** a separate probe APK → stock Vulkan/Samsung driver → short Xclipse tests. Android stays running; the process has its own stop mechanism.
3. **Native:** loader → XNU → RAM root → e1s drivers. Android/adbd are unavailable; an independent control plane and verified recovery are required.

Results transfer between environments as hypotheses for further checks, not as proof of compatibility.

## Graphics

Candidate path: project-owned Metal/AIR fixtures → metal2vulkan → Vulkan → stock driver or app-local Xclipse RADV. Start with one frame and pixel comparison, then bounded runs and performance measurements.

A future XNU path needs a different backend: memory management, queues, firmware, IRQs, power and IOMMU support from the new kernel. An Android RADV library does not provide those services by itself.

## Data isolation

The app stores results in its own directory; experimental images and source trees stay on the host. Do not allocate partitions, use Android USERDATA as an iOS root or assume it can be decrypted from XNU. The first potential native root is RAM-only.

App Stop, runner timeout and hardware watchdog are separate mechanisms. Assess autonomy only after each has been tested independently.
