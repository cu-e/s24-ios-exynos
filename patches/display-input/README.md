# E1S STM coordinate correction

Apply 0001-e1s-stm-coordinate-nibbles.patch **after** the full embedded HakiOS and E1S series from s24-port `c8860decc62c6d6180e609036d027a2997972420`. The source preparation tool enforces that pin and checks/applies the patch in an isolated generated XNU tree. Original references and historical preparation artifacts remain unchanged.

The two changed lines implement the field ordering in Samsung s24-linux `417484173abc2c4fa93e738ea82ad9f2e84911b1`, drivers/input/sec_input/stm_spi/stm_dev.h (stm_ts_event_coordinate) and stm_core.c (stm_ts_coord_parsing). Byte 3 has X's low four coordinate bits in bits 7..4 and Y's in bits 3..0. The original E1S decoder uses the opposite nibble.

Author: S24 iOS / Exynos project, 2026-11-05. This is a minimal source correction, not a copied Samsung implementation. Embedded HakiOS carries APSL-2.0; Samsung source retains its file notices. No explicit license grant for all E1S additions was found in the selected root/patch, so this note does not relicense them or resolve redistribution rights. Full generated third-party files remain ignored.

The actual extracted original decoder fails 960 of 1,024 synthetic asymmetric-coordinate/mirror vectors. The corrected decoder must pass all 1,024. This establishes the source-layout correction; SPI transfer integrity, IRQ/power, firmware revision and actual coordinates remain unverified on the phone. See docs/procedures/ui-006/README.md and the linked evidence.
