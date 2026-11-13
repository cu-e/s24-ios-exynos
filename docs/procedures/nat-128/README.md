# NAT-128: prepared polling-only diagnostic, no native execution

Owner claude-opus-nat116-20261113. Host evidence only.

## Implementation and checks

NAT-125's mapped GPIO setup is retained. Replace touch IRQ/thread setup with
exactly three attempts, each reading ordinary device ID (C0 22 then D1 00 00
plus dummy/data) and hardware ID (FB 20 00 00 00, one dummy, eight data bytes),
then waiting 50 ms. No event thread, EINT configuration, IRQ attachment,
sense-on, scan-mode, reset, firmware update or calibration command is sent.

test_nat128.py compiles actual C with clearly synthetic responding/nonresponding
SPI peers; it asserts exact nine transmitted frames and zero IRQ/thread starts.
Both cases pass. This is not electrical SPI proof. KRN-044 five-object ARM64
compile/link succeeded, zero undefined symbols and 29 storage stubs, kernel:
d6d56001d32aadda5059ab0a2255b313d7ca2055da88d645d1610214bf284517.
Primary framing reference is Samsung stm_spi.c / stm_fn.c at
417484173abc2c4fa93e738ea82ad9f2e84911b1, reviewed by NAT-125.

## Concrete next single-run plan (requires fresh permission)

Purpose: determine if a powered controller replies to ordinary or hardware ID
reads without the sc8 IRQ/userland regression. Not a working-input test yet.

- Enable only SID 0x0d / PM1 0x05 LDO18_CTRL 0x3d=0xd8 and LDO9_CTRL 0x34=0xf0,
  same 1.8 V / 3.0 V settings and strict allowlist as NAT-124.
- Require revision 0x01, preread both rails; after each write read exact value.
  Refuse unexpected already-enabled voltage, any failed prerequisite/readback;
  do not proceed to second write after first failure. No new PMIC register.
- e1skeys=0 disables the entire key thread, so no recurring PMIC power-key reads.
- Run the bounded read-only SPI sequence above; no IRQ even if controller replies.
- Preserve visible sc9 display, product ADT, no marker overwrite, readonly RAM
  root/storage stubs, kernel watchdog feed/timed return and loader deadline.
- Build and package as a new uniquely named image; host-check actual cmdline
  including both e1spmic=2 and e1skeys=0 within 255 bytes. If necessary omit
  recorder sizing tokens only after verifying defaults and tests; do not guess.
- Pin final RECOVERY/payload hashes in a new per-image decision, claim a separate
  native task; preflight and run once only. Do not run this kernel directly.
- Restore stock RECOVERY, full hash readback, Android boot/data checks, assess,
  close permission before asking optional owner observation. Other partitions,
  data, accounts, keys, EFS and encryption remain untouched.

Risks: PMIC layout/routing error can destabilize power; readback is not a voltage
measurement. Existing allowlist and previous exact readbacks reduce uncertainty
but do not eliminate electrical risk. GPIO assignment and timing remain unproven;
SPI may not answer. Native timeout/watchdog/Download Mode restore remain required.
No reset/erase or other rail operation. No automatic repeat after failure.

Decision 0049's single prepared run was consumed by NAT-124. Decision 0044
continues to authorize independent host work and non-PMIC native controls; this
plan does not enlarge the specific power-operation consent. Obtain a new owner
choice before building the per-image native authorization and executing it.
