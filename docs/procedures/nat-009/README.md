# NAT-009 watchdog arming and S-Boot recovery-marker clearing, 2026-11-10

Host-verified integration of the NAT-007 S5E9945 Cluster 0 hardware watchdog
(`0x10040000`) and PMU recovery-reason clearing (`0x128600bc`) on top of the
accepted NAT-006 build-002 and NAT-010 entry/coherency hardening.

## S921BXXS9BYH3 S-Boot and H-Arx contract (verified from on-device `epbl` and `harx`)

1. **`sbl_check_reboot_mode` (`epbl` `0x29d994..0x29dec4`, called from `platform_init` at `0x2466f8`)**:
   - Reads `w19 = *(uint32_t *)0x128600bc` (`PMU_PANIC_INFORM` / `INFORM3`, `0x29d9ac..0x29d9b4`).
   - Checks `(w19 >> 8) == 0x00123456` (`0x29d9d8..0x29d9f8`).
     - When true (e.g. `0x12345604` from `adb reboot recovery`), compares `get_param(0)` (`REBOOT_MODE`) with `w19 & 0xff` (`4`); if unequal, prints `"setting REBOOT_MODE to %d\n"` and calls `set_param(0, w19 & 0xff, 0, 1)` (`0x29da64`), persisting `REBOOT_MODE = 4` into the `param` partition.
     - At `0x29dde8`, executes `str wzr, [x21]`, **zeroing `*(uint32_t *)0x128600bc` (`0x00000000`) before returning**.
     - When `(w19 >> 8) != 0x00123456` (including `0x00000000` after a hardware watchdog reset if `0x128600bc` is left zero), jumps to `0x29dec4` (`"%s: skip\n"`) and **does not modify `param(0)`**.
2. **`platform_init` (`0x2466fc..0x246704`, `0x246acc..0x246b08`) and `load_boot_images` (`0x247bd0..0x247dc0`)**:
   - Reads `get_param(0)`; when `(val & ~1) == 4`, sets boot-mode bit 19 (`0x80000`, `"Recovery Set!"`).
   - When bit 19 is set, `load_boot_images` selects the `RECOVERY` partition (`0x247ce4`), calls `set_param(2, 0x4f4c, 0, 1)` (`"Set debug level to low(%x)\n"`, `0x247d78`) and `set_param(17, 0, 0, 1)` (`"Set upload mode to disable(%x)\n"`, `0x247d9c`), preventing `sbl_check_upload` (`0x2bb6c4`) from entering Upload Mode on a subsequent watchdog reset (`CL0_WDTRESET`, `0x12860010` bit 24). However, `load_boot_images` does not clear `param(0)`.
3. **One-shot recovery guarantee (`recovery_guard.c`)**:
   - Because S-Boot zeroes `0x128600bc` at `0x29dde8`, the register reads `0x00000000` at kernel entry (or `0x12345604` if entered without S-Boot clearing it).
   - `recovery_prepare()` writes `0x12345600` (`SEC_RESET_REASON_UNKNOWN`) to `0x128600bc` whenever the incoming value is `0x12345604` or `0x00000000`, followed by `dsb sy` and readback verification.
   - On the subsequent watchdog reset, `sbl_check_reboot_mode` reads `0x128600bc == 0x12345600`, matches `(w19 >> 8) == 0x00123456`, sees `get_param(0) != 0`, and calls `set_param(0, 0, 0, 1)` (`"setting REBOOT_MODE to 0\n"`), clearing the persistent recovery mode in `param` and booting normal Android (`BOOT`).
4. **Kernel entry state (`epbl` `0x248afc..0x248b74` and `harx` `0xd148..0xd178`, `0x11478..0x114cc`)**:
   - S-Boot masks IRQ (`msr DAIFSet, #0x2`), stops its internal timer (`0x24652c`), cleans D-cache and clears `SCTLR_EL1.M` and `SCTLR_EL1.C` (`0x246294` -> `0x245994`).
   - With Protected KVM allowed (`[PKVM] Allow Protected KVM`), `harx` clears `SCTLR_EL2.M`, `SCTLR_EL2.C`, `SCTLR_EL2.WXN`, `HCR_EL2.VM` and `HCR_EL2.AMO`, sets `DAIFSet = 0xf`, `x0 = 0xa0000000` (FDT), `x1 = x2 = x3 = 0`, and enters the kernel at EL2 (`CurrentEL == 0x8`, `0x80000000 + kaslr_offset`).
   - `start.S` drops from EL2 to EL1 (`from_el2` -> `el1_entry`), verifies `SCTLR_EL1.M == 0` and `SCTLR_EL1.C == 0`, initializes stack/vectors/timer/FP/BSS, calls `recovery_guard` (which writes `0x12345600` to `0x128600bc`, arms Cluster 0 WDT for 30s at 25.6 MHz, and verifies counter decrement within 1,000,000 iterations), and runs `loader_main`.

## Reproduction (`artifacts/nat-009/check-002`)

```sh
cp -a artifacts/nat-010/check-001/source artifacts/nat-009/check-002/source
python3 docs/procedures/nat-009/patch.py artifacts/nat-009/check-002/source
python3 docs/procedures/nat-010/build.py artifacts/nat-009/check-002
cc -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra -Werror \
  -Isrc/native/watchdog src/native/watchdog/s5e9945.c docs/procedures/nat-009/recovery_guard.c docs/procedures/nat-009/test.c \
  -o artifacts/nat-009/guard-test
./artifacts/nat-009/guard-test
```
