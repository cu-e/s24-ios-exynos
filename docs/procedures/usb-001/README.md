# USB-001 host preparation

Owner: `codex-team-usb-20261105-ai`. Worktree: `worktrees/usb-001-20261105`.

Implement an allocation-free read-only block request/reply adapter with a
project-owned, explicitly versioned wire format. The laptop side supplies a
trusted read callback; the future native phone side consumes bounded replies.
The callback interface contains no write operation. The current code performs
no USB, DMA, MMIO, partition, phone, or operating-system power operation.

Acceptance covers exact pinned E1S source requirements and actual host parser,
geometry, lifecycle, sanitizer and target-compilation checks. It does not cover
DWC3 endpoint enumeration, PHY programming, working XNU USB or a recovery path.
All native hardware and iOS integration gates must remain explicit.

Run fresh experiments only after registering them in the primary checkout's
single registry. Use `src/platform/usb/check.py --run NEW_NAME` after this
implementation is present. Preserve failed outputs and actual commands/exits.
The coordinator runs shared repository checks after integrating the branch.

## Exact source inputs and attribution

The primary input is [dx4m/android-kernel-samsung-e1s at
f85e53cfa5497ead5d78821efbac84e51f37a4e1](https://github.com/dx4m/android-kernel-samsung-e1s/tree/f85e53cfa5497ead5d78821efbac84e51f37a4e1),
registered as `s24-bsp-reference`. Compare with the separately pinned
`s24-linux` revision `417484173abc2c4fa93e738ea82ad9f2e84911b1`.
The runner extracts nine exact files from both existing local Git objects,
checks both HEAD revisions and records text hashes in `source-review.json`.
These are vendor source inputs; they do not establish equivalence with the
owner's newer `S921BXXS9BYH3` firmware or live register state.

| File under the primary source | Findings and consequence |
|---|---|
| [s5e9945-usb.dtsi](https://github.com/dx4m/android-kernel-samsung-e1s/blob/f85e53cfa5497ead5d78821efbac84e51f37a4e1/arch/arm64/boot/dts/exynos/s5e9945-usb.dtsi) | Vendor wrapper `samsung,exynos-dwusb`, child `synopsys,dwc3`; controller `0x17900000/0x10000`, sysreg HSI0 `0x17820000/0x10000`; raw SPI index403, level high. Parent clocks `aclk,sclk,bus`, child `ref`, domain `pd_hsi0`; OTG role switch, force Gen1. |
| Same PHY node | `samsung,exynos-usbdrd-phy`; six register windows: `0x178a0000/0x200`, `0x178b0000/0x200`, `0x178c0000/0x200`, `0x178d0000/0x800`, `0x178e0000/0x800`, `0x17900000/0x10000`. Version `0x600`, combo `0x801`, RAM mode1; PMU offsets `0x61c,0x620`; clocks `ext_xtal,aclk`. |
| `include/dt-bindings/interrupt-controller/s5e9945.h` | DWC3 SPI index403; PHY remote wake/connect/REWA indices401/399/405. These are source SPI indices, not measured interrupt routing. |
| `arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi` | Enables UDC/DWC3/PHY, permits SuperSpeed, selects `gpc7-1`; supplies `s5_l2_reg,s4_l4_reg,l7_reg,l11_reg` for USB0.75/1.2/1.8/3.3V. No negotiated speed or GPIO operation is measured. |
| `arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r17.dts` | Declares both `hsi2c_34` repeater nodes enabled: `tusb2e11-repeater@3E` at 7-bit address `0x3e` (lines2755–2762), and `ptn3222-repeater@4F` at `0x4f` (lines3418–3425). This does not identify the fitted component or active selection on BYH3. A TUSB2E11 GPIO template occurs inside `#if 0`; it does not establish the active GPIO. |
| [dwc3-exynos.c](https://github.com/dx4m/android-kernel-samsung-e1s/blob/f85e53cfa5497ead5d78821efbac84e51f37a4e1/drivers/usb/dwc3/dwc3-exynos.c) | Parent and DWC3 core request 36-bit coherent DMA masks. `core.c` also contains a conditional 64-bit capability path; neither proves actual controller width, valid IOVA mappings or cache coherency. |
| `drivers/usb/dwc3/dwc3-exynos-otg.c`, `drivers/phy/samsung/phy-exynos-usbdrd.c` | Vendor role/PHY sequencing must be studied before a native driver can claim enumeration. No Linux implementation is copied into project-owned adapter code. |
| `Documentation/devicetree/bindings/usb/samsung,exynos-dwc3.yaml` | The generic older Exynos binding does not describe vendor compatible `samsung,exynos-dwusb`; using it alone would miss S5E9945 dependencies. |

The DWC3 Exynos wrapper, OTG driver and core differ between the two pins.
The other six extracted files match byte-for-byte. Preserve the vendor files'
own licenses (source registry GPL-2.0/per-file terms, generic binding dual
license); the adapter is independently written and imports no vendor symbols.

## Native requirements and next implementation boundary

`src/platform/usb/profile.json` is a machine-readable source-fact profile.
All hardware qualification flags remain false. The next native driver needs:

1. A proven kernel entry/MMU/interrupt/timebase and independent recovery/log path.
   USB failure cannot safely be the sole mechanism that returns to Android.
2. Explicit ownership and sequencing of HSI0 power/clocks/sysreg/PMU, Type-C
   role and VBUS, regulators, PHY RAM/tuning, and the actually fitted external
   I2C repeater. Both declared source candidates must remain represented until
   board/firmware selection is independently qualified.
3. Verified controller version and interrupt routing, bounded event rings/TRBs,
   enumeration and descriptors, endpoint stalls/reset and cancellation policy.
4. Pinned controller-visible buffers with measured address width, explicit
   CPU/physical/bus/IOVA translation, cache ownership/barriers and confirmed
   DMA completion before unmap/free. `s24_usb_dma_slice` checks arithmetic only.
5. A matching S24R1 peer, bounded receive-frame assembly and fresh session binding;
   it must serialize adapter calls and keep block traffic from starving control
   and logs. Add deadlines and independently verified watchdog/recovery handling.
6. A target-specific read-only block-device adapter before any native root mount.
   ARM/Mach-O object compilation establishes no Apple service ABI or working iOS.

There is no native USB controller driver, streaming endpoint receiver, Apple USB
service integration, hardware DMA or automatic return to Android in this task.
No phone was accessed. The implemented host boundary can be reviewed and tested
without authorizing any hardware experiment.

## Validation and failure history

Experiments are registered in the primary ledger before execution. Each run
has actual commands, exits, compiler versions, source snapshots, source pins,
file hashes, target headers and immutable output under
`worktrees/usb-001-20261105/artifacts/usb-readonly/`.

| Experiment/run | Actual result |
|---|---|
| USBHOST-001 / `host-session1` | Failed fixture expectation: a negative reply-opcode test rewrote an already-equal low byte. The adapter correctly accepted the unchanged reply. The failure capsule and original outputs remain intact; `failure-record.json` wraps their hashes. |
| USBHOST-002 / `host-session2` | Corrected mutation to opcode high byte; 63,470 assertions,20,000 deterministic mutations passed under host ASan/UBSan. |
| USBHOST-003 / `host-session3` | Added fresh-session-after-late-reply, near-UINT64_MAX geometry and full64-bit DMA-window edges; 63,482 assertions passed. All four target objects have no undefined imports. |
| USBHOST-004 / `host-session4` | Both source pins independently checked, including retail repeater;18 runner checks and63,482 fixture assertions passed. |
| USBHOST-005 / `host-session5` | Passed20 runner checks and63,482 fixture assertions; deliberate ASan heap-overflow and UBSan signed-overflow controls each exited1 with the expected diagnostic, confirming the runtime detects both faults. |
| USBHOST-006 / `host-session6` | REV-001 followup passed28 runner checks and63,482 fixture assertions: both enabled repeater nodes match the structured profile at both pins, and each omitted profile node or altered source compatible is rejected. Hashes and actual extracted sets are in `repeater-review-evidence.json`. |

REV-001 identified that the earlier profile covered only TUSB2E11. The corrected
`USB2_repeaters.enabled_source_nodes` includes PTN3222 as well. Source checks now
extract the two enabled children beneath `hsi2c_34`, rather than merely finding
TUSB2E11 tokens anywhere in the file. They compare the full structured set,
including node name, compatible, address and enabled status. For each pin and
each candidate, an intentionally incomplete profile must fail; an independently
altered source compatible must also fail. This is a narrow pinned-source
extractor, not full DTS preprocessing, a compiled live DTB or component probing.
Literal `#if 0` templates are excluded, and unexpected directives inside the
selected controller are rejected rather than interpreted as board selection.

The host compiler is existing `/home/egor/.local/bin/clang`, NDK27 Clang18.
Its native sanitizer archives live under the resource directory's
`lib/x86_64-unknown-linux-gnu/`, rather than the Android runtime directory.
The runner saves the actual linker plan and resource directory. The separate
NDK28 target compiler builds C/C++ objects for `aarch64-none-elf` and
`arm64-apple-ios16.5` without an Apple SDK; none are executed.

The fixture validates an independent40-byte wire vector, valid512/65536-byte
reads, all truncated header prefixes, excess/unaligned input, unsupported
opcodes, reserved/version/session/id/range violations, arithmetic overflow,
short buffers, replay, backend failure/short/overreported reads, synchronous
disconnect, late completion and reconnect. A real local image is opened with
`O_RDONLY`, read with `pread`, and its hash is unchanged. Trusted callbacks must
honor the provided buffer extent; the adapter cannot protect against a malicious
callback or concurrent mutation of caller-owned state.

## Review handoff

Review `readonly.h` and `readonly.c` with the lifecycle contract in the source
README. The bounded protocol and exact-source requirements satisfy USB-001's
host acceptance boundary. Keep the claim `in_progress` until the coordinator
reviews/integrates the owned commit and records shared repository checks.
The final `evidence-summary.json` gives the witness paths and immutable hashes;
no shared registry snapshots are included in this commit.
