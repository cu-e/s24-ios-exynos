# RES-004: Xclipse interfaces and the remaining native graphics path

Reviewed 2026-11-05. Evidence category: **source-review**, plus the separately recorded GPU-006 synthetic host oracle. No phone command, APK install, MMIO/ioctl probe, firmware operation or native boot was performed for this follow-up. All native GPU capabilities remain untested.

## Pinned inputs and interpretation

| Source | Revision and selected role |
|---|---|
| [Samsung SGPU kernel](https://github.com/dx4m/android-kernel-samsung-e1s/tree/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/gpu/drm/samsung/gpu/sgpu) | `417484173abc2c4fa93e738ea82ad9f2e84911b1`: UAPI, ioctl dispatch, BO, GPUVM, submission, power and S5E9945 DTS. Not verified as the owner's exact S9BYH3 source/firmware. |
| [RADV Xclipse](https://github.com/JimVulkan/radv-xclipse/tree/fe9b8943aaeec11ed9fccbfcc382da07379afbe5) | `fe9b8943aaeec11ed9fccbfcc382da07379afbe5`: winsys, BO, CS, identification, `ac_drm`, libdrm wrap/patches. Android/Linux donor, not an XNU backend. |
| [S24 loader](https://github.com/RNDMBG/iOS-On-S24/blob/c8860decc62c6d6180e609036d027a2997972420/shim/e1s-xnu/loader.c) | `c8860decc62c6d6180e609036d027a2997972420`: boot memory-window selection and boot_args. |
| Apple XNU + prepared E1S patches | XNU `c54f35ca767986246321eb901baf8f5ff7923f6a`, prepared by the existing pinned build procedure: E1S/proc_reg/vm_param/arm_init page policy, not a compiled kernel. |
| [UniXNU graphics guide](https://github.com/UniXNU/UniXNU/blob/c740efb5b23e94453bb179f7801eb592baafacf6/docs/porting/gpu.md) | `c740efb5b23e94453bb179f7801eb592baafacf6`: architecture and Adreno frontend/backend reference, different GPU. |
| [OnePlus findings](https://github.com/popovluka/ios-lemonadep/blob/d952f7d97ea075de9f6686cbbafbd55db6517e65/lemonadep/hackios/FINDINGS-2026-11-01-03.md) | `d952f7d97ea075de9f6686cbbafbd55db6517e65`: author distinguishes GPU draw, app Metal, backboardd GLES and missing final Metal presentation. No local reproduction. |

[Public source manifest](../../fixtures/public/gpu-research/source-manifest.json) identifies exact selected text-file bytes; [coverage](../gpu-coverage.json) records web/Reddit limits. Reviewed source sections establish interface facts, not a security audit of the entire drivers. Firmware arrays, binary drivers, Apple SDKs and proprietary userland were not fetched for this work. Kernel internals retain their Linux/vendor notices; UAPI headers have their own permissive notices. RADV/Mesa and dependencies retain per-file notices. The new oracle independently expresses ownership rules; it does not transplant kernel implementations or relicense donors.

## Actual boundary to replace

The kernel registers AMDGPU-style BO allocation, context, VM, BO-list, mmap, metadata, wait, submission, VA, userptr and SGPU-specific operations in `amdgpu_kms.c`. The driver reports DRM version 3.42; two headers named AMDGPU/SGPU are not interchangeable merely because some operation numbers match. The SGPU header additionally defines Samsung allocation/metadata and cache synchronization through GEM_OP. Generic DRM syncobj, PRIME/dma-buf and Linux file-descriptor semantics sit outside that one vendor header.

RADV's `radv_amdgpu_winsys.c`, BO and CS implementations call `ac_drm`/libdrm for device initialization, BO and VA operations, contexts, chunk submission and timelines. The pinned wrap selects **libdrm 2.4.133**, archive SHA256 `fc68f9d0ba2ea63c9432a299e14fea09fad7a8a66e8039fcd7802ca59f77b4f5`, with two local patches. That archive was **not downloaded, built or qualified** in this review. Its wrap digest alone is not a completed dependency review.

An Android Bionic driver cannot be dropped into XNU. A glibc Linux build still requires a Linux kernel interface. Choose either a Darwin winsys or an adapted `ac_drm` transport; implement native BO backing/pinning, GPUVM/TLB, contexts, validated command submission, timeline completion, cache visibility, power/IRQ/fault handling and sharing underneath it. Exynos SGPU VM and image-loader S2MPU requirements must be resolved from the matching board; an Adreno SMMU implementation is not a substitute.

## Concrete source hazards

1. **Identification:** the RADV donor says PCI ID `0x73a0` is shared among Xclipse generations. It distinguishes models using Android SoC information and chip revision; the pinned S5E9945 DTS has `chip_revision=0x02600200`. Its family/profile mixes GFX10.3 identification with newer shader-core features. [Samsung identifies Xclipse 940 as RDNA 3](https://semiconductor.samsung.com/processor/mobile-processor/exynos-2400/), but marketing architecture does not authorize desktop command-stream defaults. Reproduce the reviewed per-chip profile, then qualify actual behavior; do not force generation overrides blindly.
2. **Power-sensitive queries:** the libdrm MMR-cache patch warns that raw register access during SGPU power transitions is unsafe. It caches GB_ADDR_CONFIG once per process/ASIC. This is an upstream rationale, not a demonstrated fix on this phone. Do not execute READ_MMR as harmless inventory. Native query design needs power ownership and a reviewed safe information source.
3. **Unbounded internal wait:** BO VM-update code calls timeline wait with `INT64_MAX`. A finite outer UI timer cannot establish that this call stopped or its references retired. Audit all native/winsys wait paths and propagate deadlines/errors without freeing in-use memory.
4. **Memory guard scope:** the donor's 8 GiB rejection guard applies to allocations of at least 2 MiB on its newer shader-core profile. It reads a hardcoded `16e00000.sgpu` sysfs path and falls back to a process-local counter. The selected E1S DTS node is `22200000.sgpu`; whether an alternate live sysfs path exists is unknown. Therefore device-wide protection on this S24 is **not established**, and small allocations are not covered by that rejection branch. The author's roughly 9–10 GiB lockup statement is not a measured threshold for the owner's phone. Native accounting must include all clients, imports and constrained pools with headroom.
5. **Completion:** the `0x73a0` path avoids user-fence chunks and uses timeline signal completion, with context reset-state queries. A CPU-visible word, command submission return or elapsed timeout is not sufficient retirement evidence. Two queued readers retain the same BO until both finish.
6. **Cache and chip workarounds:** BO mapping selects special memory-type/permission defaults; persistent concurrent CPU/GPU access is marked untested in source. The donor avoids CP-DMA prefetch on Xclipse 940 after author-observed freezes, while pacing comments concern 920. Neither workaround nor shared PCI ID establishes cross-generation equivalence. The live Android configuration enables forced write-combine and reclaim; a DTS `dma-coherent` declaration does not resolve every CPU/import/cache transition on XNU.

## Page-size reconciliation

The SGPU GPU page is **4 KiB**. DEV-001 measured Android CPU pages of 4 KiB; that is not a native XNU measurement. In the prepared E1S source:

- E1S.h does not define `__ARM_16K_PG__`; without another build define, `proc_reg.h` selects 4 KiB hardware granules.
- `arm_init.c` selects advertised PAGE_SHIFT_CONST=PAGE_MAX_SHIFT=14 when boot_args.memSize is greater than 1 GiB, otherwise ARM_PGSHIFT. `vm_param.h` distinguishes runtime advertised pages from hardware granules.
- The loader's successful DT-selected RAM window is capped at 512 MiB; fallback uses supplied memory size. It writes that selected window into boot_args. The small DT branch implies 4 KiB advertised pages under the current source defaults, whereas a later larger window can change VM allocation granularity without changing the GPU page size.

This is conditional source reasoning, not a built or booted result. Record exact build flags, actual memory window, CPU hardware/VM pages and userspace query before enabling native DMA. The [contract](../../src/graphics/contracts/README.md) tests 4 KiB GPU mappings against both 4 and 16 KiB CPU allocation policies, charges full backing and rejects exposing extra CPU padding through GPU mappings. Do not share one 16 KiB backing page among unrelated owners.

## Online and Reddit follow-up

[RADV release notes](https://github.com/JimVulkan/radv-xclipse/releases) describe Android Xclipse builds and application-specific fixes; they are upstream reports, not a native iOS implementation. The reviewed code remains at its explicit SHA rather than silently updating to whichever release is latest.

The notes also warn that a hung GPU can remain stuck after its app closes. This supports keeping process cancellation distinct from device recovery; the author's suggested reboot procedure is not executed or adopted as an autonomous daily-phone experiment here.

The [S24+ report](https://www.reddit.com/r/EmulationOnAndroid/comments/1x7j03x/) describes RADV v1.6 through GameNative on Exynos 2400/Xclipse 940: short game runs, remaining visual errors/freezes and thermal limits. Four returned comments include maintainer acknowledgement. This is relevant same-SoC Android evidence, not the owner's S24 or native Metal acceptance. Its DXVK/Proton/FEX path translates in the opposite direction from iOS Metal and does not replace an XNU backend. A separate `RADV` search in r/Exynos timed out; it was not an empty result. No exhaustive community or comment coverage is claimed.

[Flutter issue 187905](https://github.com/flutter/flutter/issues/187905) reports render freezes and memory pressure on **Galaxy S25 FE**, also Exynos 2400/Xclipse 940. Later comments explicitly nuance the initial CMA hypothesis: low CmaFree can occur during normal operation. Use this as a reason to measure allocation failures, fragmentation and constrained pools, not as proof that CmaFree=0 alone is fatal or that this S24 reproduces the issue. Local saved configuration enables CMA/SGPU/write-combine/reclaim, but does not measure pool occupancy or establish the failure mechanism. No reproduction or stress test was run.

[DroidDeck issue 290](https://github.com/Droid-Deck/DroidDeck/issues/290) discusses Bionic versus glibc RADV builds. That illustrates one userspace build boundary; even a working Linux glibc build would not establish Darwin compatibility.

## Delivery and next gates

GPU-006 delivers a versioned operation/lifetime specification and seven adversarial host scenarios. It is deliberately not counted as a native GPU implementation. GPU-011 specifies and compiles the pointer-free transport ABI with a fake backend, independently of the missing Apple SDK. GPU-007 must integrate actual XNU backing/VM/queues; firmware authentication, power sequencing, IRQ retirement and exact profile mapping remain unknown. These need separately authorized native tests after kernel and recovery prerequisites.

GPU-008 requires observed native clear/copy/triangle pixels plus finite error paths. GPU-009 must qualify the selected iOS16.5 Metal/API registration and IOSurface compatibility. GPU-010 must measure real multiprocess CoreAnimation, producer/consumer fences and DECON/DSIM presentation. A translated AIR compute shader, Adreno screenshot, working framebuffer or one app rendering to an offscreen surface satisfies none of that full chain by itself. Keep compression, 120 Hz and ray tracing after basic correctness, cleanup and thermal qualification.
