# NAT-125: fail-closed touch IRQ admission and source review

Owner `claude-opus-nat116-20261113`. Host-test only; no phone actions.

## Regression guard

NAT-124 enabled a low-level IRQ/event thread despite the controller read being
classified as no response. The same path is reproduced by compiling the actual
C on the host: the unmodified sc8 source attaches one IRQ and starts one thread
with a constant-low MISO. The fixed source attaches neither. A constant-high
MISO is also refused. A clearly labeled synthetic responding peer still reaches
stage 3 (one IRQ/thread). This verifies admission logic, not hardware SPI.

The fix also sequences stm_chip_id before printf. C does not specify argument
evaluation order: the old printf could load id[] before executing the transfer.
Indeed host tests with high MISO previously printed "no response" with five
zero bytes even when the buffer actually contained FF. Thus NAT-124's status
shows no response (all-zero OR all-FF), but its printed bytes alone cannot
reliably distinguish those two. Do not rewrite the native capture. This is a
correction to the interpretation in NAT-124's README, not a new measurement.

`e1s_touch.patch` is incremental against sc8; `e1s_touch_combined.patch` includes
NAT-121's mapped GPIO/stages plus this change, against the unchanged STR-014 donor.
KRN-044 uses the combined patch; all other rebuilt objects are sc8's.

## Samsung source review and correction of earlier hypothesis

Pinned source: references/s24-linux at
417484173abc2c4fa93e738ea82ad9f2e84911b1.

- stm_spi.c:169-181 `stm_ts_set_spi_mode` in THIS pinned tree only raises CS
  and sets Linux SPI_MODE_0; it does NOT send STM register commands. Earlier
  conversation speculation about a required chip-side SPI-mode programming
  sequence was not established and must not be implemented from memory.
- stm_spi.c:589-637: ordinary addressed read sends the command through the
  C0 write wrapper, then a separate D1 00 00 transfer; payload begins after
  buf_len+1=4 bytes. The donor's stm_read_address matches this framing.
- stm_spi.c:590-597 special-cases 0x87 (event read) with no prior C0 wrapper;
  payload begins after its command byte plus dummy byte. Donor
  stm_read_command uses length+2 and rx+2, matching that shape.
- stm_fn.c:142-158 reads five ID bytes and prints first two characters plus
  three ID bytes. Its hardware-read variant starts FB 20 00 00 00; useful
  diagnostic candidate, not run here.
- stm_core.c:1179 raises CS/configures host mode, then delays 10 ms. Around
  1129/1238 its startup uses sense-on and scan-mode setup. stm_fn.c:589 uses
  A0 00 scan_mode with echo-event waiting. These activate scans; they do not
  establish why the initial chip-ID read did not respond.
- stm_fn.c:323 issues a controller reset and waits for ready. No such reset,
  firmware download, calibration or persistent command is added in this task.
- s5e9945-pinctrl.dtsi:1377-1395 names SPI9 bus pins gpp9-2/1/0 and CS gpp9-3.
  These names alone do not independently prove which bus pin is CLK/MISO/MOSI;
  retain the signal-order mapping as an item to verify against controller docs.

## Native regression remains unresolved

NAT-124 had no launchd lines or recorded frames but did return on schedule.
IRQ storm/starvation is a hypothesis: this guard removes one unsafe admission
path, not proof of the cause. Another changed path is e1s_input.c:56-60 recurring
PMIC power-key reads once ACPM is available. Avoid combining both hypotheses
in a causal claim. Next useful diagnostic plan: staged/polling-only touch,
no recurring power-key reads, bounded logs for event/IRQ counts and scheduler
progress, compare with successful sc7 before considering scan activation.

No new RECOVERY image or native decision is prepared here. The owner's one
prepared PMIC run has been consumed by NAT-124. A further PMIC-writing run
requires a fresh owner choice on a concrete plan; host review/building continues
without it.
