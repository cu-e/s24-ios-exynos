# GPU-014: Vulkan driver inventory on the S24

Evidence class: android-userland, measured 2026-11-10 through `cmd gpu vkjson` as the shell user.
No su, no install, no rendering. Device: SM-S921B/e1s, S921BXXS9BYH3, SoC `s5e9945`.

## Established

| Item | Measured value |
|---|---|
| Device name | Samsung Xclipse 940 |
| Vulkan API | 1.3.279 |
| Vendor ID / device ID | 0x144d / 0x2600200 |
| Driver version, raw | 100675593 (VK_MAKE_VERSION decoding gives 24.3.9) |
| GLES string from SurfaceFlinger | ANGLE (Samsung Xclipse 940) on Vulkan 1.3.279, OpenGL ES 3.2, driver 24.1.265, git 24f47ea4b93e |
| Queue families | family 0: 4 queues, flags 31; family 1: 2 queues, flags 30 |
| Timestamp period | 39.0625 ns, 64 valid bits |
| Memory heaps | 5599395840 bytes (flags 3); 67108864 bytes (flags 1) |
| Memory types | 16 |
| Device extensions | 153 |

| Extension | Present |
|---|---|
| `VK_KHR_acceleration_structure` | yes |
| `VK_KHR_ray_query` | yes |
| `VK_KHR_ray_tracing_pipeline` | yes |
| `VK_EXT_mesh_shader` | no |
| `VK_KHR_fragment_shading_rate` | yes |
| `VK_EXT_device_fault` | yes |
| `VK_KHR_timeline_semaphore` | yes |
| `VK_KHR_synchronization2` | yes |
| `VK_KHR_swapchain` | yes |
| `VK_EXT_external_memory_dma_buf` | yes |

The device ID matches the `chip_revision=0x02600200` value RES-004 read from the pinned S5E9945 DTS.
This confirms that value on this phone, through the driver's own report.

## Not established

- Whether any frame renders. Nothing was submitted to the GPU, so GPU-003 is **not** satisfied: its
  frame results, temperature and Stop test all require running the probe APK.
- The decoded raw driver version and the GLES string differ in the minor number (24.3.9 against 24.1.265).
  The cause is unknown, and the driver may not use VK_MAKE_VERSION.
- Anything about the kernel `sgpu` interface. This is the vendor's user-space driver answering.
  It says nothing about native bring-up under XNU.

## Next check

GPU-003 needs the owner to authorize the `android-app` scope, because it installs the probe APK.
