# NAT-122: fixed touch driver, step 2 (`loader-diag-xnu-sc7-md1`)

Evidence kind: **native-device**. One RECOVERY-only run, 2026-11-13 14:24:24Z, decision 0048 (under 0044/0019). Owner `claude-opus-nat116-20261113`.
Restore: `nat-012/restore_stock.py --bus 5 --address 53`, Android booted, RECOVERY = stock, user-data present, `assess` pass. Permit closed.

## Result (`analyze122.py`): `W-ok` / display `D2-refreshing` / iOS `F1-new-frame` / touch **`T1-no-response`**; reader opened

* **No fault.** The NAT-066 abort is gone: `e1s-touch` ran steps 1 and 2 at kernel 198.10 s and stopped as designed.
* **What S-Boot leaves (step 1, read only):** gpp9 `CON 0` (all four pins input), `DAT 0`, `PUD 0x1111` (pull-down on pins 0-3), `DRV 0`;
  gpa1 `CON 0`, `DAT 0x8` (**pin 2, the touch IRQ, reads low**), `PUD 0x11111111`, EINT `con 0 mask 0xff pend 0`. S-Boot does not set up
  SPI9 for the touch controller.
* **Step 2:** gpp9 → `CON 0x1110` (pins 1-3 out, pin 0 in), CS high; device-id read returned `00 00 00 00 00` ("no response").
* **Reader side works:** `redwood-touch: opened by pid 16` = backboardd (the `/dev/hakios-touch` node is used);
  `hakios: input: touch screen service 0x137d3dc50, buttons 0x137d423d0`; backboardd sets touch detection mode 0xff → 0xfe → 0x1 → 0.
  The HID side of input is in place; there are no samples to deliver.
* Display/iOS as NAT-120: DECON kicks +1200 per 10 s, no SpringBoard abort, 6-8 frames/s.

## Reading (hypotheses, not established)

The most likely cause of all-zero bytes is an **unpowered controller**: the e1s DT (`e1s_eur_openx_w01_r13.dts`) supplies the STM from
`vdd_ldo18` (1.8 V I/O) and `vdd_ldo9` (3.0 V analog) and deletes `regulator-always-on` / `regulator-boot-on` for both, so nothing obliges
S-Boot to switch them on; in Android both are `enabled` with one user each (measured via root, sysfs). The IRQ line reading low with a pull
-down fits an unpowered chip. Alternatives: SPI mode/timing of the bit-bang (Samsung uses SPI mode 0, up to 10 MHz; our half-bit delay is a
busy loop), or the controller held in reset. The kernel log says `e1s-pmic: ACPM is not available; PMIC stays untouched`: there is no
working path to switch LDO9/LDO18 in this kernel today.

## Next

Turning on the touch rails is a PMIC (power) operation through ACPM. AGENTS.md lists power operations as not authorized; decision 0044
allows bounded input experiments. This needs an explicit owner decision before an image that writes PMIC registers is run.
Host work that needs no decision: why ACPM is unavailable (`channel 2 queues are outside SRAM`), and the S2MPS27/ACPM LDO9/LDO18 register
facts from the pinned Samsung source.
