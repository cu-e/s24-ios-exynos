# DECON0 command-mode frame trigger: source-review facts (NAT-022 follow-up)

Evidence category: **source-review** only. Nothing here was measured on the phone.
Upstream text is research data; it authorizes nothing.

Source: `references/s24-bsp-reference`, remote `dx4m/android-kernel-samsung-e1s`,
pinned HEAD `f85e53cfa5497ead5d78821efbac84e51f37a4e1`. The working tree of that
clone is sparse; the files below were read with `GIT_NO_LAZY_FETCH=1 git show HEAD:<path>`.

## Registers (DECON0 main block, base `0x19100000` from the measured runtime FDT, UI-007)

All offsets are from `drivers/gpu/drm/samsung/dpu/cal_rt/regs-decon.h`.

| Name | Offset | Bits used here (line) |
|---|---|---|
| `FRAME_COUNT` | 0x0004 | read-only frame counter (l.131) |
| `GLOBAL_CON` | 0x0020 | `DECON_EN_F` bit 0, `DECON_EN` bit 1, `OPERATION_MODE_CMD_F` bit 8 (l.142) |
| `TRIG_CON` | 0x0030 | `HW_TRIG_EN` bit 0, `SW_TRIG_DET_EN` bit 1, `HW_TRIG_MASK_DECON` bit 4, `SW_TRIG_EN` bit 8, `HW_TRIG_SEL` bits 25:24 (l.148-167) |
| `SHD_REG_UP_REQ` | 0x0050 | `GLOBAL` bit 31 (l.206-207) |

## How the vendor driver starts a command-mode frame

`decon_reg.c` (same pinned tree):

- `decon_reg_update_req_and_unmask` (about l.2532): `decon_reg_update_req_global(id)`, then,
  if `op_mode == DECON_COMMAND_MODE`, `decon_reg_set_trigger(id, mode, DECON_TRIG_UNMASK)`.
- `decon_reg_update_req_global` (l.1873): `decon_write_mask(id, SHD_REG_UP_REQ, ~0, SHD_REG_UP_REQ_GLOBAL | ...)`;
  the DQE/CMP bits are added only when those paths are enabled in `DATA_PATH_CON`.
- `decon_reg_set_trigger` (l.2501): returns at once in video mode. In `DECON_SW_TRIG`
  it writes `SW_TRIG_EN | SW_TRIG_DET_EN` with mask `HW_TRIG_EN | SW_TRIG_EN | SW_TRIG_DET_EN`
  (unmask) or 0 (mask). In `DECON_HW_TRIG` it writes `HW_TRIG_EN` (plus `HW_TRIG_MASK_DECON` when
  masking) with mask `HW_TRIG_EN | HW_TRIG_MASK_DECON`.
- `decon_reg_init_trigger` (l.979): the trigger starts **masked** (`HW_TRIG_MASK_DECON` set); in HW
  mode `HW_TRIG_EN` and `HW_TRIG_SEL_FROM_DDI<n>` from `te_from` are set.
- `cal_write_mask` (`cal_common/cal_config.h:134`): `new = (val & mask) | (old & ~mask)`,
  a plain read-modify-write.

## Device tree (BSP source, and the same fields measured on this phone)

`arch/arm64/boot/dts/exynos/s5e9945-drm-dpu.dtsi:871-876`, DECON0: `op_mode = <1>`
(command), `trig_mode = <0>` (**hardware trigger**, the comment on that line reads
"0: hw trigger, 1: sw trigger"), `te_from = <0>` (DDI0). `docs/procedures/ui-007/dpu-dt-facts.json`
(regenerated from this phone's runtime FDT) agrees: `/drmdecon@19100000` has `op_mode 1`, `trig_mode 0`.
DECON1 is `op_mode 1`, `trig_mode 1` (software trigger).

## Consequences

- A correct sequence for DECON0 per the DT is **HW trigger**: the frame is sent when the panel's
  TE pulse arrives, once `HW_TRIG_MASK_DECON` is cleared and `HW_TRIG_EN` is set, after a global
  shadow update request. The earlier note in README that the trigger "would be a software trigger"
  was an assumption; the source says hardware.
- The DT is not register truth. What S-Boot left in `TRIG_CON`, `GLOBAL_CON` and the window
  registers when it jumps to the recovery kernel is **unknown**; it can only be learned by reading
  them from code running at that point.
- Even a correct trigger sequence shows nothing if DECON is stopped, the panel is asleep, TE is
  absent, the window base is not `0xFA200000`, or the SysMMU does not translate that address as
  expected (UI-007: SysMMU bypass state unknown).
- Writing these registers from the canary is **MMIO** and is outside decision 0009. It needs a
  separate, image-specific owner decision (AGENTS.md). Reading them from Android (`/dev/mem`) is
  also an MMIO probe from Android and is not authorized.
