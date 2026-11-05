# RES-005: E1S KIWI, native Wi-Fi donors and version gates

Reviewed 2026-11-05. This is selected **source-review**; NET-001 separately records compiled host boundary tests. No phone command, Wi-Fi scan/join, power/MMIO/PCI write, firmware transfer, network credential or native boot was used in this follow-up. Native Wi-Fi remains untested.

## Conditional donor choice

There is a substantially closer candidate than writing a new wireless stack: [Ath12kWifi current source](https://github.com/UniXNU/Ath12kWifi/tree/28de7b91d7a880682b777e0e3564245a99dbc3f5) adapts ath12k/mac80211/cfg80211 to XNU, with an explicit board boundary and a supplicant/control path. It is a **conditional candidate**, not a drop-in S24 driver. Use it only after endpoint/chip revision, firmware/board/regulatory data, actual Exynos DMA/interrupts and the selected OS are matched.

The [official Linux Wireless ath12k page](https://wireless.docs.kernel.org/en/latest/en/users/drivers/ath12k.html) lists WCN7850 hw2.0 support. The pinned Linux [PCI implementation](https://github.com/gregkh/linux/blob/458c6079fc1d41d564c37679c8ace02cd83ee817/drivers/net/wireless/ath/ath12k/wifi7/pci.c) maps `1107` to WCN7850 and rejects an unsupported SoC hardware-major version. A PCI ID alone does not select a valid hardware profile. DEV-001 obtained module names but no live endpoint ID; that input remains null in [profile.json](../../src/platform/wifi/profile.json).

## Pins and documentation mismatch

| Source | Exact revision / role |
|---|---|
| Samsung E1S Linux | `417484173abc2c4fa93e738ea82ad9f2e84911b1`: CNSS, Exynos PCIe and retail Wi-Fi overlay; not verified exact S9BYH3 firmware source |
| UniXNU documentation/catalog | `c740efb5b23e94453bb179f7801eb592baafacf6`: network guide, component pins and reported sheng behavior |
| Catalog Ath12kWifi | `f6bf561f92cc42761bdd417fce1d53fe1db9477c` (2026-10-25): older callback tables and custom station runtime |
| Current Ath12kWifi | `28de7b91d7a880682b777e0e3564245a99dbc3f5` (2026-11-04): separately fetched live HEAD, current mainline/control runtime |
| Catalog sheng board | `516a780473a2ac59c8b438e132bb60204dda9e22`: retained board reference |
| Current sheng board | `460179565a018c741b93e0b1efa07c55d4de497a`: separately fetched current WifiProbe/WifiNet and firmware-manifest metadata |
| Linux donor dependency | `458c6079fc1d41d564c37679c8ace02cd83ee817` (v7.0.14): selected ath12k PCI/hardware files; other runtime dependencies not built |
| iOS16 Qualcomm comparisons | iOSPlus10 `146e889430bab755329dde7104cc0fa002f44bfb`; ios-lemonadep `d952f7d97ea075de9f6686cbbafbd55db6517e65`: QCA6490/ath11k and OS station examples, different endpoint/board |

The catalog still pins the old component while its driver guide describes the newer implementation. The old [header](https://github.com/UniXNU/Ath12kWifi/blob/f6bf561f92cc42761bdd417fce1d53fe1db9477c/include/nw_abi.h) has 12 platform pointers and four event pointers (96/32 bytes on these 64-bit builds). The [current header](https://github.com/UniXNU/Ath12kWifi/blob/28de7b91d7a880682b777e0e3564245a99dbc3f5/include/nw_abi.h) adds clocks/busy-delay/preemption and RX batching/fragment ownership/link events (136/56 bytes). It also extends status and packet APIs. No table-size/version handshake exists. Do not compile board code against one header and link another module merely because the exported names match. NET-001 verifies the old header fails its current ABI assertions; NET-004 must rebuild and audit the complete linked pair.

The current [source lock](https://github.com/UniXNU/Ath12kWifi/blob/28de7b91d7a880682b777e0e3564245a99dbc3f5/tools/source-lock.json) pins Linux v7.0.14, FreeBSD headers and wpa_supplicant 2.12 with archive digest. Only selected Linux PCI/hardware text was fetched here; the FreeBSD/supplicant/generated runtime was not fetched, built or tested. Current [nw_mainline.c](https://github.com/UniXNU/Ath12kWifi/blob/28de7b91d7a880682b777e0e3564245a99dbc3f5/src/nw_mainline.c) and [cfg80211 control](https://github.com/UniXNU/Ath12kWifi/blob/28de7b91d7a880682b777e0e3564245a99dbc3f5/src/nw_cfg80211_control.c) are the useful station/control boundaries; the legacy custom SME files are not the selected production path. Reviewed upstream host scripts invoke preparation and use Darwin linker flags; they were read, not executed as a Linux-host shortcut.

## Exynos services that cannot come from sheng

| Layer | Pinned source evidence | Still required on this S24 |
|---|---|---|
| Endpoint | CNSS KIWI defines `17cb:1107`; mainline WCN7850 requires supported hardware revision | Live vendor/device/subsystem/revision and chip HW profile; no inference from module alone |
| Rails/PHY/link | E1S overlay selects CNSS KIWI, RC0, Gen2, board GPIO/rails, cold-boot-calibration flag and SysMMU | Exact BYH3 board/reset/clock/rail and PHY configuration; actual link/BAR/capability reads under native scope |
| Reserved memory | Source reusable pool is 72 MiB, aligned 4 MiB, with allocation range rather than one fixed base | Live reservations, native CPU/physical/IOVA mappings and available budget; do not inherit sheng's 128 MiB arena |
| DMA | [Exynos root driver](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/pci/controller/dwc/pcie-exynos-rc.c) installs DMA hooks that call PCIe IOMMU map/unmap | Implement actual SysMMU/stream ownership, pinning, cache policy and direction-aware visibility; CPU VA is not an endpoint bus address |
| MSI/wake | [CNSS Exynos](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/net/wireless/cnss2/pci_exynos.c) assigns 32 vectors: MHI 3, CE 10, wake 1, DP 18 | Actual controller MSI receiver, GIC route/ack, vector dispatch, GPIO wake and bounded worker behavior |
| Firmware/control | CNSS selects KIWI paths, firmware variants and board/QMI data; donor uses MHI→QRTR/QMI→ath12k | Matching explicitly supplied files, identity/digests, board/regdb and calibration/API compatibility; FW_READY is not scan/join |
| OS frontend | Current donor exposes a board/network interface and native control broker | Selected iPhone X iOS16.5 Apple80211/wifid/configd/launchd integration and correct async result ownership |

Important traps:

- `cnss_pci_init_smmu` is an empty success stub in the Exynos CNSS file, while the root driver still programs PCIe SysMMU through DMA hooks. It is not evidence that XNU may bypass the IOMMU.
- Commented `use-msi` in one overlay does not establish absent interrupts; trace CNSS, root-controller setup and actual routing together. The donor's `irq_base` is a software namespace; do not substitute a GIC SPI index or sheng SPI 141.
- Samsung's 32-vector CNSS table is not the selected donor's allocation: mainline WCN7850 uses 16 vectors (MHI 3 at 0, CE 5 at 3, DP 8 at 8). Map that donor layout into the actual Exynos receiver and record available capacity separately. The initial host profile conflated these counts; its command passed boundary tests but WIFIABI-001 is retained as inconclusive pending the corrected input policy.
- The current [sheng WifiProbe](https://github.com/UniXNU/UniXNU-sheng/blob/460179565a018c741b93e0b1efa07c55d4de497a/package/WifiProbe.cpp) checks only the start pointer in `pDmaMap`, ignores its length, and has empty `pDmaSync`. That is not proof of whole-range safety or Exynos cache coherency. Its `pHalt` sleeps forever; callback presence alone cannot provide bounded stop.
- `nw_wifi_stop` tears down several runtime subsystems, but its void return is not observed S24 DMA quiescence. Native teardown must prove device/worker ownership retired before releasing arenas/MSI/BAR, including fault paths.
- Firmware-manifest hashes in sheng identify that author's installed files, not compatible E1S board data. No firmware blobs or extract/download scripts were executed. The board's derived-MAC policy must not be silently inherited; actual S24 address/privacy integration remains unqualified.
- The E1S overlay also includes Bluetooth and shared enable/power context. Real rail/reset ownership and Wi-Fi/Bluetooth coexistence must be coordinated; an Android-running radio power cycle is not read-only inventory or a substitute for native qualification.

## iOS frontend and security scope

[Current WifiNet](https://github.com/UniXNU/UniXNU-sheng/blob/460179565a018c741b93e0b1efa07c55d4de497a/package/WifiNet.cpp) contains separate legacy 592-byte and OS27 656-byte association structures, plus a 540-byte OS27 result layout. Those sizes are source facts for that donor, not a verified iOS16.5 ABI. Native bytes being rendered in Settings or an `en0` service existing is not a completed scan/authentication/association/key/port/DHCP/DNS/HTTPS path.

The current donor's documented selected profiles are open/WPA2-PSK with PMF. Do not infer demonstrated WPA3/SAE, enterprise EAP, roaming, 6 GHz, privacy or sleep/wake acceptance from Wi-Fi 7 hardware support or general supplicant capabilities. NET-003 must qualify each claimed security/lifecycle profile. Keep the approved first OS; inspect explicit local iOS16.5 components for NET-005 rather than switching to the newer donor OS.

For iOS16 comparisons, the OnePlus10 README summary claims Wi-Fi among completed work, while detailed plan and later feature notes have different dates and explicitly unrun changes. The archived Oct24 post states Wi-Fi was not working at that time. This is a dated status distinction, not proof of current total absence or full support. ios-lemonadep describes iOS16/ath11k/QCA6490 integration and is a useful older-OS frontend reference; neither source is an E1S transport or tested iOS16.5 ABI. Do not adopt donor USERDATA firmware placement or partition operations.

## Licensing and coverage

The selected Ath12kWifi tree has no root LICENSE/COPYING and no explicit grant was found in the selected ABI/runtime headers. This is a provenance gap before implementation incorporation, not a claim about all authors' rights. Linux/FreeBSD/supplicant files retain individual notices; sheng's root BSD-2-Clause-Patent does not automatically cover a different repository. This work includes no donor implementation: the owned boundary compiles against an external pinned header, and public provenance contains hashes. Perform component/file review before linking or distributing a native derivative.

[Coverage metadata](../wifi-coverage.json) preserves the successful r/hackios `Wi-Fi` title search, selected OnePlus10/S7 bodies and returned comments, GitHub/web fetch limitations and exact private snapshot hashes. Ten title results are not ten complete implementation reviews. The S7 author explicitly lists Wi-Fi as missing; its Exynos/Mali graphics result is not a radio donor. Keyword search, archived comments and web indexing are bounded; no exhaustive or negative internet-wide claim is made. Newer source pins were added separately rather than changing historical ones.

## Concrete next work

NET-001 delivers only the [compiled input/DMA boundary](../../src/platform/wifi/README.md), with unknown live fields, ABI rejection and host negative tests. NET-004 now gates NET-002: implement and actually link real Exynos callbacks plus one matched donor runtime against pinned XNU, before separately authorized native link/DMA/IRQ/firmware/scan/WPA2/Internet tests. NET-005 gates NET-003: compile the selected iOS16.5 station frontend and asynchronous ownership rules, then qualify native Settings, reconnect/security, power and sustained traffic. KRN-001, recovery and device authorization remain prerequisites; these new host results do not bypass them.
