# NAT-040 — S5E9945 USB2 device-mode bring-up plan for the loader (source review)

Evidence kind: **source-review**. Nothing here ran on the phone. The plan cites the vendor kernel `s24-linux` at the full pin
`417484173abc2c4fa93e738ea82ad9f2e84911b1` (the same pin as the USB-001 profile, `src/platform/usb/profile.json`). Whether the
running firmware S921BXXS9BYH3 equals that tree is not established (`live_firmware_equivalence_qualified = false`).

Files:

| file | role |
|---|---|
| `plan.json` | the plan: every step with its class, its register effect and a literal citation; the minimal subset; what is omitted; the absence claims; the ladder; the unknowns |
| `verify_plan.py` | reads each cited file at the pin with `git show`, finds the literal text (inside the named function when one is named), requires the exact occurrence count and the stated source order, runs the whole-tree absence searches, cross-checks the prose against the USB-001 profile, writes `artifacts/nat-040/verify-001/resolved.json` |
| `test_nat040.py` | host tests of the verifier: hermetic cases on a scratch git repo, plus the real plan, which must verify, and a list of deliberate corruptions that must each be rejected for the intended reason only |
| `evidence.json` | the task's evidence record |

`python3 docs/procedures/nat-040/verify_plan.py` and `python3 docs/procedures/nat-040/test_nat040.py` need the local checkout
`references/s24-linux` at the pin (the test skips, it does not pass, without it).

## What the verifier proves, and what it does not

It proves that every citation exists verbatim at the pinned revision, that the stated order of steps is the order in the source,
and that the addresses, suppliers, repeater addresses and the other facts the prose repeats agree with the USB-001 profile. It
does **not** prove that a prose sentence correctly describes the cited line (that is the reviewer's reading), that the plan works
on hardware, or what state S-Boot leaves the block in. The classes below say which steps are which.

Step classes: `V` vendor step kept in the minimal subset; `M-omit` vendor step left out of the minimal subset (reason listed);
`U` platform state or step the loader cannot know (each is tied to an unknown); `I` informational citation (offset, constant,
config, evidence). The minimal subset is exactly the set of `V` steps, and every `V` step belongs to a ladder rung; both are
checked.

## Findings

1. **The vendor sequence is fully on paper.** `exynos_usbdrd_utmi_init` runs: repeater enable (I2C), PMU isolation release
   (`0x12860000 + 0x61c` bit 0), PHY clocks, the USBCON link init, then the eUSB2 PHY initiate (`phy_exynos_eusb_initiate`, 19.2 MHz
   constants, waits of 10/1000/28/2500 us). The DWC3 core then runs GSNPSID check, soft reset, global control, frame-length and
   ref-clock setup, GSBUSCFG0 and the event buffer; the device side runs DEPSTARTCFG, ep0 DEPCFG/DEPXFERCFG, SETUP TRB +
   DEPSTARTXFER, DEVTEN, DCFG speed and `DCTL.RUN_STOP`.
2. **The power domain has an exact recipe.** `pd_hsi0` is switched through `PMU 0x12862000` (CONFIGURATION, bit 0) and
   `0x12862004` (STATUS, bit 0); on the first power-on the vendor also performs a DTZPC restore by SMC (`need_smc = 0x17810204`)
   and replays a fixed list of CMU_HSI0 writes (`hsi0_cmu_init`, steps 0.24-0.33). Reading the status needs no HSI0 access; the
   loader can learn the state before touching anything in the block.
3. **Two vendor macros are dead.** `SKIP_DWC3_CORE_POWER_CONTROL` (which compiles out the PHY power_on/power_off bodies) and
   `USB_USE_IOCOHERENCY` are only ever tested with `#ifdef` in the pinned tree and never defined (absence claims A1, A2, checked
   with a whole-tree word search). So the vendor PHY `power_on` is a no-op, and the sysreg sharability setup does not run.
4. **The SuperSpeed PHY (USBDP combo) is the big optional piece.** Its RAM-mode firmware download is only needed for USB3/DP.
   The vendor has a *detach pipe3* routine (LINKCTRL `force_pipe_en = 1`, `force_phystatus = 0`, `force_rxelecidle = 1`,
   LINK_CLKRST `link_pclk_sel = 0`) that it uses when USB3 is turned off or DP takes the lanes, with the USB2 port still working.
   The minimal subset replaces the USBDP enable by exactly that. **This is an inference**: the vendor uses detach after the combo
   PHY was up; running it with the combo PHY never initialised, in device mode, is not demonstrated (unknown U6).
5. **The repeater is a real question.** The eUSB2 PHY is configured for a repeater (`phy_cfg_rptr_mode = 1`); two repeater
   nodes (TUSB2E11 at I2C 0x3e, PTN3222 at 0x4f) are enabled in every board DTS and share one global slot. The I2C writes only
   tune signal quality; whether the fitted part works at its power-on defaults is unknown (U4). The first attempt skips them.

## Register map used (all from the plan's citations)

| block | base | notes |
|---|---|---|
| DWC3 | `0x17900000` (0x10000), SPI 403 | GSNPSID at `+0xc120`; IP id `0x5533` (DWC3) or `0x3331` (DWC31/32) |
| USBCON wrapper | `0x178a0000` | LINKCTRL `+0x04`, LINK_CLKRST `+0x0c`, UTMI_CTRL `+0x10` |
| eUSB2 control | `0x178b0000` | RST_CTRL 0, CMN_CTRL 4, PLLCFG0 8, PLLCFG1 0xc, TXTUNE 0x14, TESTSE 0x20 |
| eUSB2 PHY / USBDP / TCA | `0x178c0000` / `0x178d0000` / `0x178e0000` | USBDP and TCA are not used by the minimal subset |
| SYSREG_HSI0 | `0x17820000` | DRCG enable at `+0x104` (vendor cmu_init) |
| PMU | `0x12860000` | USB isolation `+0x61c` bit 0; pd_hsi0 CONFIGURATION `+0x2000`, STATUS `+0x2004` |
| CMU_HSI0 | `0x17800000` | USB32DRD mux `+0x1008`, EUSB divider `+0x1800`, user mux `+0x640`, NOC user mux `+0x630`, option0 `+0x800`, Q-channels `+0x300c..0x3064` |
| CMU_TOP | `0x22b20000` | HSI0_USB32DRD mux `+0x10c8`, gate `+0x20c4`, divider `+0x18a8` |
| hsi2c_34 (repeater I2C) | `0x110b0000` | only for the repeater tuning |

## The minimal subset and the ladder

The minimal subset (all `V` steps) is: read pd_hsi0 status and, only if off, power it on and replay the vendor cmu_init writes;
enable the LINK/control Q-channels; release PHY isolation; USBCON init; pipe3 detach instead of USBDP; the eUSB2 PHY initiate
verbatim; DWC3 core and glue setup with an event buffer; the ep0 start and `RUN_STOP`. Omitted with a stated reason: the USBDP
enable, the repeater I2C, the DisplayPort user muxes, the DTZPC SMC unless the domain is found off, and any IO-coherency setup.

NAT-043 must not run this as one block. `plan.json` → `ladder` lists nine rungs; each logs what it read or wrote before the next
one starts, so the first failing rung localises the fault, and the first rungs only read:

| rung | action | resolves |
|---|---|---|
| L0 | identity marker, touches nothing | — |
| L1 | read pd_hsi0 STATUS/CONFIGURATION (always-on PMU) | U2 |
| L2 | read CMU_TOP mux/gate/divider (always-on) | U3 |
| L3 | domain on: read CMU_HSI0/SYSREG registers; domain off: vendor power-on, bounded wait, SMC attempt, cmu_init, then the same reads | U2, U3 |
| L4 | read DWC3 GSNPSID | U6 |
| L5 | HS-only PHY bring-up with read-backs | U1, U6 |
| L6 | DWC3 core, soft reset, event buffer in loader-owned non-cacheable memory | U5, U6 |
| L7 | device start; with a host cable, USBRST then CONNECTDONE | U4, U5, U6 |
| L8 | the NAT-041 monitor's `GET_INFO` answers with a boot id the host did not choose | U8 |

Reading a block whose power domain is off may stall the bus; the loader's existing watchdog bounds that, and the ladder never
touches an HSI0 register before L1/L3 shows the domain on.

## Unknowns (each names the measurement that resolves it)

U1 state of the four USB supplies; U2 pd_hsi0 state and whether the DTZPC SMC works from the loader; U3 CMU_TOP/CMU_HSI0 clock
state; U4 fitted repeater and whether defaults pass HS traffic; U5 DMA path (S2MPU/PMMU in front of HSI0, coherency, address
width); U6 HS-only operation with the combo PHY never initialised, and the reference-clock rate; U7 PHY port GPIO (irrelevant
to the HS-only subset); U8 how a run ends (NAT-042). The resolving tasks are NAT-039 (Android read-only inventory; blocked only
while the phone is absent), NAT-041 (host engine and DMA placement), NAT-042 (autonomous return) and NAT-043 (the native run).

## Consequences for the next tasks

* NAT-041 builds the EP0 polled engine against this register order and places the event buffer/TRBs in one non-cacheable,
  loader-owned region (U5); it cannot assume the BSP's DMA mapping.
* NAT-042 specifies the return to Download Mode through the PMU reboot node of `s5e9945.dts` (`reboot-offset 0x3c00`,
  `reboot-cmd-offset 0x190`); this plan does not touch it.
* NAT-043 runs the ladder under decision 0019, one rung at a time, and reports each rung through the screen markers *and* the
  USB monitor when it comes up. Its verification criterion is unchanged: an unattended archive with a new boot id and a stage
  message only the new image can know.
