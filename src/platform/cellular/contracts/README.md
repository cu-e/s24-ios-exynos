# Samsung cellular transport contract

This directory contains a versioned input contract and an executable **host framing model**, not a native modem driver. It has no device, file, network, firmware or subscription I/O. `selected_protocol` remains null until the actual firmware/device-tree profile establishes it.

## Source and local inputs

The existing DEV-001 capture configures S5000AP, shared memory, SBD, RX/UL PKTPROC, secure CP boot and REINIT_VSS as modules. PCIe and DIT are disabled. Configuration establishes selected code paths, not successful operation. S5000AP is a generic driver-family identifier; it does not identify the exact modem silicon or establish FirmWire compatibility.

The pinned [CPIF parser](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/soc/samsung/cpif/modem_main.c) reads `mif,protocol`. The [link implementation](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/soc/samsung/cpif/link_device.c) dispatches separate SIPC and SIT helpers and performs CP secure-monitor operations. Loaded module names do not select a framing protocol. Exact BYH3 DT/queue/channel/SMC inputs have not been recovered.

| Candidate | Field facts used by the host model |
|---|---|
| [SIPC5](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/soc/samsung/cpif/include/sipc5.h) | Start/config byte, channel byte, little-endian length. Header 4 bytes, 5 with multi-frame control, or 6 with extended 32-bit length. Length includes header; padding flag selects 8-byte alignment on this ARM64 profile. |
| [SIT/Exynos IPC](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/soc/samsung/cpif/include/exynos_ipc.h) | Sync 0xABCD, sequence, fragment config, 16-bit length, channel and channel sequence. Wire header is **12 bytes** although declared packed fields occupy 10. Bytes 10–11 stay opaque. Total frame rounds to 8 bytes. |

The [header builder](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/soc/samsung/cpif/modem_io_device.c) adds the 12-byte wire size to payload length. Deriving it with `sizeof` on the packed field declaration would misplace the payload. Padding contents are not assumed to be zero.

The model is independently authored from these field facts; it does not copy Linux helper implementations. The donor Linux files retain GPL-2.0 notices. This does not make a wholesale Linux-to-APSL driver transplant acceptable. Preserve each donor's notices and perform file-level review before integrating code.

## What is tested

```sh
python3 -m unittest discover -s tests -p test_cellular_framing.py -v
```

Owned fixed byte strings cover all three recognized SIPC5 header variants, nonzero padding, concatenated frames, a 12-byte SIT header, every truncated prefix, invalid sync/length, reserved variant, oversized 32-bit length and invalid host budgets. The 1 MiB maximum is a host policy, not a measured firmware limit. Fragment control is returned raw; there is no reassembly, channel negotiation, ring ownership or RIL/APDU/IP interpretation.

No frame is transmitted. A parser pass is not a working CPIF driver, SIM registration, mobile-data path or eSIM implementation. See [the staged contract](../../../../docs/procedures/cell-001/README.md) and [radio research](../../../../research/notes/RES-003-radio-donors.md).
