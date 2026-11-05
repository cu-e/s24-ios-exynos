# E1S Wi-Fi platform-input adapter

This is a compiled, project-owned boundary for **input admission, callback-table compatibility and checked CPU-virtual→DMA-window translation**. It does not implement Exynos power/PCIe/SysMMU/MSI, allocate or pin memory, synchronize caches, load firmware, start Ath12kWifi or send network packets. Those real services are still required by NET-004; iOS16.5 station integration is NET-005.

The [public input contract](profile.json) deliberately leaves live endpoint, chip revision, native page/DMA/IRQ profile and firmware/board/regulatory identity unknown. Source identifies a **candidate** KIWI `17cb:1107`; this has not been measured on the owner's S24. A loaded Android module is not an endpoint measurement.

## Exact donor ABI

The adapter includes external `nw_abi.h` from Ath12kWifi `28de7b91d7a880682b777e0e3564245a99dbc3f5`; its hash is in profile.json. No donor implementation/header is vendored or relicensed. The build verifies origin, clean checkout, full revision and header digest. Native incorporation still needs per-file/component license review: the selected Ath12kWifi repository has no root LICENSE/COPYING and the selected interface/runtime files give no explicit grant. Do not assume the umbrella UniXNU license covers a separate repository.

On the tested 64-bit targets the current platform table is 136 bytes and events table 56 bytes. The older catalog pin `f6bf561f92cc42761bdd417fce1d53fe1db9477c` has 96/32-byte tables. The current adapter intentionally fails compilation against that old header. There is no runtime version/size negotiation in this donor table; compile assertions do not prove the linked module matches. Rebuild module and board from the same reviewed pin and validate the link manifest in NET-004.

The factory requires all current platform hooks, including clocks/busy delay and paired preemption hooks that the donor marks optional. This is a stricter Exynos integration policy, not a claim those hooks are mandatory for every donor board. PCI configuration/MSI callbacks are required; `nw_board.map_phys` remains optional, matching the reviewed reference. IRQ base is the donor's synthetic IRQ namespace; it is not a GIC SPI index or absolute interrupt ID. Samsung CNSS uses a 32-vector layout; the selected mainline WCN7850 donor requests **16** (MHI 3, CE 5, DP 8). Donor vector count and available controller capacity are separate inputs. Neither source table establishes actual S24 delivery.

## What the functions establish

`e1s_wifi_prepare` checks an explicit trusted profile, candidate identity, reviewed-input bitmask, CPU VM granule (4/16 KiB), DMA-window bounds/alignment, board fields and callback presence. It clears output on rejection and copies typed tables on success. It invokes **no callback**. `VALID` means structural input admission, not measured hardware, working callback implementations, hardware authorization or Wi-Fi support. All profile facts still need dated evidence outside C; a caller can fabricate a bitmask. Synthetic origin is retained in the returned binding.

`e1s_wifi_translate` validates the complete nonempty CPU range inside an explicitly supplied window, rejects CPU/bus arithmetic wrap and returns `bus_start + offset`. CPU virtual, physical and endpoint bus/IOVA addresses remain distinct. It performs no actual mapping, ownership check, pinning or synchronization. Only a native allocator may admit live allocations within the window; this helper alone cannot stop a client mapping another allocation. Caller storage, output and input objects must be valid/non-overlapping and remain stable throughout the call.

The pinned Samsung PCIe DMA hooks call `pcie_iommu_map` even for numerically equal addresses. The CNSS Exynos `init_smmu` stub returning success does not remove that root-controller obligation. The sheng donor checks only the starting address in `pDmaMap` and has an empty `pDmaSync`; neither is an Exynos mapping/coherency implementation. Use the checked full-range helper plus actual native allocation/cache/IOMMU services, not a copied no-op.

No allocation is released by this code. Native shutdown must stop submissions/worker access and establish MHI/device DMA quiescence before releasing arenas, MSI or BAR. A void `nw_wifi_stop` call or stopped process alone is not a measured recovery guarantee. Callback presence cannot make a blocking callback bounded.

## Reproduce

```sh
python3 tools/sources.py fetch ath12k-wifi ath12k-wifi-current
python3 src/platform/wifi/check.py --run unique-wifi-boundary
python3 -m unittest discover -s tests -p test_wifi_platform.py -v
```

The script uses installed NDK Clang 19 for compile-only AArch64 ELF/arm64 iOS16.5 Mach-O C/C++ objects, a separate installed host Clang 18 for ASan/UBSan, and `cc` for host layout/negative checks. No SDK or kernel driver is linked; no ARM object or donor runtime is executed. Unit tests skip explicitly if the externally fetched header/compiler is absent; a skip is not an acceptance result.

The owned fixture uses synthetic numbers and deliberately nonfunctional callback stubs. It verifies unknown/missing profile inputs, wrong candidate ID, missing hooks, MSI fields, two CPU granules and 16,384 valid/one-byte-overrun DMA-range pairs, with **zero callback invocations**. Additional tests use another nonidentity window, null/empty/wrapped ranges and an expected compile failure against the old ABI. These establish boundary checks, not hardware operation. See [the procedure](../../../docs/procedures/net-001/README.md) and [source audit](../../../research/notes/RES-005-wifi-donors.md).
