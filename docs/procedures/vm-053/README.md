# VM-053: SCFB display streaming, virtio-mmio multitouch and the s24vmm viewer (host-tested)

Host-only. Nothing here was run on the phone; the device run is VM-054 or a later task.

## What exists

- `src/vmm/machine.c` (`vmm_plan`): with `--scfb WxH`, s24vmm reserves `scfb_region_size(W, H)` bytes
  (a 64 KiB header page and an XR24 buffer, rounded up to 2 MiB) directly below the FDT, and
  `s24vmm.c` passes `scfb.addr/size/w/h` to avfboot in bootargs. avfboot (scion-avf a6f4bc3,
  `avf/shim/avfboot.c` lines 696-706) accepts the region only inside RAM, page aligned and big enough.
- `src/vmm/scfb.[ch]`: the host side of the Scion shared framebuffer: magic/size/format checks,
  `frame_seq`, `POLL` and `DAMAGE` flags, and the `drawing`/`host_reading` seqlock of xnu patches 1200
  and 1204. `display_main` in `s24vmm.c` serves frames on 127.0.0.1:PORT (default 5824) as S24F frames
  and turns S24T touch messages into virtio-input reports.
- `src/vmm/virtio.[ch]`: a virtio-mmio v2 transport with split virtqueues and a virtio-input
  multitouch device at 0x0a000000 (0x200 bytes, GIC SPI 16 = INTID 48, level high), with a name and
  ABS_INFO for ABS_X/Y and ABS_MT_POSITION_X/Y. Reports are MT-B (slot, tracking id, position,
  BTN_TOUCH, SYN_REPORT); the level interrupt goes through `KVM_IRQ_LINE`.
- `src/vmm-viewer`: the viewer app (`dev.egor.s24vmmviewer`). It connects to 127.0.0.1 only, decodes
  S24F frames with bounds checks (`Protocol.java`, at most 4096x4096) and sends touches as S24T. Its
  only permission is `android.permission.INTERNET`, which loopback sockets need.

## Checks

```
python3 -I src/vmm/check.py --run check-005          # s24vmm host tests, ASan/UBSan, TSan, NDK static build
python3 -I src/vmm-viewer/build.py --run viewer-002  # C/Java protocol test, two clean APK builds, signing
```

- `check.py`: `test_vmm` 220 checks (machine, FDT, SCFB plan below the FDT, virtio-mmio FDT node,
  walker, UART, RTC); `test_io` 92 checks (virtio-mmio registers and config space, split virtqueue,
  MT-B input encoding, the SCFB reader including damage and POLL, the S24F/S24T encoders) under
  ASan+UBSan; the threaded no-tearing seqlock test under TSan; a warning-free static NDK build.
- `build.py`: `test/wire.c` writes S24F frames with the VMM's own `s24f_encode_header`. The host JVM
  decodes them with the app's `Protocol` class and rebuilds the framebuffer: a full frame, then two
  damage rectangles, and a 64-bit sequence number. It also checks 12 malformed headers that must be
  rejected. Java writes S24T touches that the C `s24t_decode` reads back, including a slot-10
  message the C side must reject. The APK is then built twice from clean directories and the
  unsigned aligned APKs must be byte-identical. The signature uses a per-run development key, so
  the signed APK is not meant to be reproducible.
- SCFB layout: the header offsets in `scfb.h` were compiled as `_Static_assert`s with the NDK aarch64
  compiler against both upstream structs: `struct scfb_header` from xnu patch 1200 and the avfboot
  copy. All offsets and the 112-byte size match.

## Limits

- No device run: frame rate, latency and whether the guest publishes frames on the S24 are not
  measured. XNU under s24vmm does not boot to the framebuffer yet (VM-054, FP trap at
  `_cpu_data_init`).
- The viewer was compiled, not installed or run.
- One viewer at a time. A touch lift dropped by a full queue in the app leaves that slot down until
  the next touch on it.
