# NET-001: E1S Wi-Fi platform-input boundary

Review the pinned Samsung CNSS/Exynos PCIe sources and separately pinned old/current Ath12kWifi headers. Build only the project-owned profile/callback admission and DMA-window helper. There are no power, PCI configuration, register, firmware or network operations in this boundary.

```sh
python3 tools/sources.py fetch ath12k-wifi ath12k-wifi-current
python3 src/platform/wifi/check.py --run unique-wifi-boundary
python3 -m unittest discover -s tests -p test_wifi_platform.py -v
make check
```

Use a new run directory. Register an experiment with this file as its procedure before the explicit sanitizer/cross-target build. The build verifies source revisions, cleanliness and header hashes; it compiles the owned C boundary against the current external header, verifies the old header fails the ABI checks, executes a synthetic host fixture under ASan/UBSan and compiles C/C++ objects for AArch64 ELF and arm64 Mach-O. No ARM object or donor runtime is executed. Reports and source copies stay in ignored artifacts/wifi-platform/; public reports contain hashes and test results only.

`VALID` from the helper means structurally admissible inputs, not observed hardware or authorization. The public live endpoint/firmware/DMA/IRQ profile remains unknown. Real Exynos power/PCIe/SysMMU/cache/MSI services and selected iOS16.5 station integration remain separate implementation/qualification tasks. No default BAR, physical address, firmware, network password or device identity is invented.

WIFIABI-001's host command passed, but later source review distinguished the vendor CNSS 32-vector table from the selected mainline donor's 16-vector layout. That experiment is recorded as inconclusive for input compatibility. The corrected profile separates donor vector count from available controller capacity and is tested in a new registered run; the original report/source hashes remain unchanged.

WIFIABI-002 / wifi-boundary-session2 passes that corrected policy: host C/C++ layout checks, expected rejection of the old ABI, ASan/UBSan, 16,384 valid/overrun DMA-range pairs and four inspected AArch64 ELF/Mach-O C/C++ objects. The synthetic fixture invokes zero callbacks. See the [retained report](../../../fixtures/public/wifi-research/wifi-boundary-session2.json); it does not qualify actual MSI delivery, DMA coherency, firmware or iOS networking.
