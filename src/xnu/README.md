# Project-owned XNU/e1s components

Add small independent adapters here. Full upstream trees belong in references/, with local changes in patches/e1s/. No project build path is pinned before RES-001/BLD-001.

Separate a pure parser/protocol layer for host tests from the MMIO, IRQ, DMA and power backend. Attach DTS/firmware provenance to hardware values. A compile-time E1S configuration does not establish ten-core operation on the device.
