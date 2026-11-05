# Reproduce focused GPU interface research

Start from research/sources.json and RES-004/GPU-006. Verify each full SHA, origin, cleanliness and selected-file digest with tools/sources.py. Expand only explicit sparse text paths. Exclude firmware arrays even when their extension is `.h`; do not execute donor installation, GPU probing, power/reset or flashing scripts.

Read SGPU UAPI together with ioctl dispatch, BO/VM/CS and power code. Read RADV winsys together with `ac_drm`, libdrm wrap and local patches; a public Vulkan API header alone cannot describe the kernel contract. Compare the exact DTS/chip profile with saved device facts and retain firmware mismatch as unknown. Review per-file notices before code reuse.

Inspect E1S build defines, proc_reg.h, vm_param.h, arm_init.c and loader boot_args together when reasoning about pages. CPU hardware granule, advertised VM allocation page and GPU PTE page can differ. A source branch is not a compiled or runtime measurement.

Use read-only primary-source browsing and Reddit tools. Save complete third-party material only in ignored research/snapshots; publish bounded derived findings and hashes. Distinguish unavailable queries from empty results, adjacent devices from this S24, author reports from local runs and GPU drawing from actual panel presentation.

```sh
python3 tools/sources.py verify s24-linux radv-xclipse unixnu s24-port ios-lemonadep
python3 -m unittest discover -s tests -p test_gpu_contract.py -v
make check
```

The host oracle has no device I/O or GPU simulation. Mock retirement/quiescence inputs test resource accounting; they do not measure an IRQ, implement a watchdog or grant native device scope. Actual Android/native qualification remains in GPU-003/005 and GPU-007 through GPU-010, with their existing dependencies.
