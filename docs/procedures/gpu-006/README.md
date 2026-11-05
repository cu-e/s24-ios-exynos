# GPU-006 handoff

The [operation contract and host oracle](../../../src/graphics/contracts/README.md) meet this task's specification boundary. [Pinned source audit](../../../research/notes/RES-004-xclipse-interfaces.md) records the actual SGPU/libdrm/RADV dependencies and the conditional XNU page policy. No native GPU driver or working Metal frontend is delivered by this task.

Run the seven synthetic lifetime scenarios with:

```sh
python3 -m unittest discover -s tests -p test_gpu_contract.py -v
make check
```

GPU-011 first freezes and compiles a pointer-free versioned transport ABI with fake-backend tests, independently of the missing Apple SDK. GPU-007 then implements actual authenticated clients, page backing/cache/VM and bounded queues against the selected XNU build. Match a verified chip/firmware profile before any physical submission. Model backend observations cannot be wired to user-controlled completion requests.

Native firmware, power, IRQ and GPUVM bring-up need separately authorized hardware experiments and recovery. There must be no guessed MMIO writes or reset on the daily Android system. GPU-008 measures native pixels; GPU-009/010 separately qualify the selected OS frontend, IOSurface sharing, multiprocess rendering and panel presentation. Keep all native capability states untested until those measurements exist.
