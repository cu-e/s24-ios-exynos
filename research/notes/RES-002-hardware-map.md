# E1S hardware comparison

Reviewed source: Samsung BSP f85e53cfa5497ead5d78821efbac84e51f37a4e1, the S8 reference used by the exact S24 port. The owner's S9 firmware remains a different input. Local source text was read with `git show`; hashes and extracted matches are in [comparison.json](../../fixtures/public/hardware-map/comparison.json). Original files remain local under artifacts/hardware-map/ with original notices.

| Area | Source result | Local Android observation / unresolved native input |
|---|---|---|
| CPU | s5e9945-cpu.dtsi: cpu@0 through cpu@900, ten MPIDRs, four clusters | Ten cores and 4+3+2+1 policies observed; native PSCI, startup and coherency untested |
| GIC | s5e9945.dts: GICD 0x10200000/0x10000, GICR 0x10240000/0x140000 | No live GIC or IRQ-routing probe |
| Timer | s5e9945.dts: 25,600,000 Hz | Source value; actual XNU counter/IRQ operation unknown |
| RAM | s5e9945-rmem.dtsi has many firmware/debug/DMA reservations | Android MemTotal is not a free physical map; live DT properties unavailable; do not use fallback loader RAM ranges without validation |
| UFS | s5e9945-ufs.dtsi includes HCI 0x17100000; S24 patch defines polled read-only MCQ support | Partition sizes observed; no native read or controller handoff measured |
| GPU | s5e9945-sgpu_common.dtsi: sgpu@22200000 | Xclipse 940, sgpu and DRM node topology observed; native GPUVM/firmware/power/IRQ unknown |
| Touch | Generated e1s_eur_openx_w01_r17.dts: spi_9, stm,stm_ts_spi, 4096 coordinates, firmware variants fts2ba61y_e1s and fts2ba61c_e1 | sec_touchscreen reports 0..4095 and ten slots; exact board/controller revision must be matched |
| Display | Retail generated board/display sources include 1080x2340 modes; the separate base .17.dtsi includes ERD 1440x3088 panels | Actual Android display is 1080x2340; the ERD include alone is misleading |
| Wi-Fi | E1S overlay identifies Qualcomm CNSS KIWI V2 on Exynos PCIe0 | kiwi_v2/cnss2 loaded; no endpoint PCI ID obtained; do not select Broadcom |
| Modem | CPIF Kconfig and SIPC5 sources available | S5000AP/shared-memory configured; not external S5100/S5400 PCIe; no native control/data acceptance |

## Address and version interpretation

Touch controller's coordinate extent 4096 and reported maximum 4095 agree as a count versus maximum index. A GIC SPI index and an absolute INTID are different: SPI 10 corresponds to INTID 42; adapters must document which their API expects. A source constant or passing token-presence test does not validate routing on hardware.

The first attempted touch lookup in s5e9945.e1s_eur_openx.17.dtsi returned no firmware match. The generated retail e1s_eur_openx_w01_r17.dts contains the injected input/panel definitions. This is a source-selection distinction, not missing touch hardware.

The extracted checks confirm source relationships, not all driver correctness. Full DT include preprocessing, exact firmware matching, reserved-memory reconciliation, native DMA and read/write side effects remain task-level prerequisites. No MMIO, su, partition read, install or reboot was issued.
