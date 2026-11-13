# NAT-123: host qualification of touch-rail diagnostic sc8

Owner: `claude-opus-nat116-20261113` (same Hermes session retained after model
switch). Evidence: host-test; no native run belongs to this task.

## What changed

The existing uncommitted kernel-001 draft is preserved, not selected. The final
candidate uses kernel-003 / build-002 / package-002. Earlier host-only packages
must not be flashed.

- ACPM channel descriptor q_len/element/poll offsets were double-based in the
  donor. Use slot-relative offsets matching Samsung's S5E9945 C structs.
- Reject invalid queue index pointers, non-queue channel type, unexpected element
  size and invalid queue extent before sending.
- S2MPS27 regulator block is PM1 0x05, not DT node address 0x1d; SID is 0x0d.
- At the transport boundary permit only (reg,value) (0x34,0xf0) and (0x3d,0xd8)
  on that SID/block. Masked updates are disabled, including the panel path.
- Fix the draft's readback error returning success and missing equality check;
  first-rail failure prevents the second write. Refuse enabled unexpected voltage.
- Pin the COM revision sanity check to 0x01, read from Android's cached
  `/sys/class/sec/ap_pmic/pmic_id` (root, read-only, exit 0). This is not proof
  that ACPM already works natively or a unique PMIC identity.
- Keep NAT-121 mapped GPIO and hakios-touch changes. Stage 3 is already the
  driver's compiled default; omit redundant e1stouch_steps token to fit e1spmic=2.
  Actual cmdline is 248 bytes. No Samsung controller init sequence is added yet.

## Primary source/provenance

Samsung Linux checkout `references/s24-linux`, full SHA
`417484173abc2c4fa93e738ea82ad9f2e84911b1`:

- `drivers/soc/samsung/acpm/fw_header/framework.h`, S5E9945 conditional branch:
  channel stride 48, channel_info +12, queue length +40, element size +41,
  polling +44. `host/framework.h` is that file, retaining Samsung author header;
  `host/framework_noinc.h` removes include lines only for host compilation.
- `drivers/soc/samsung/acpm/acpm_ipc.c:962` channel_init swaps firmware TX/RX
  fields for the AP; mailbox-master uses INTGR0 high bits / INTSR1 low bits.
- `drivers/soc/samsung/acpm/acpm_mfd_spmi.c` and
  `include/soc/samsung/acpm_mfd.h`: SID/type/register/function/value packing.
- `drivers/mfd/samsung/pmic/s2mps27_core.c:371`: COM revision is read once and
  cached; `drivers/regulator/samsung/pmic/s2mps27_regulator.c:781` pmic_id_show
  returns it without a new hardware transaction.
- `s2mps27_regulator.c:487,496`, regulator header: LDO9 group 3 (1.8 V + 25 mV
  selector steps), LDO18 group 1 (1.5 V + 12.5 mV); 0x30 = 3.0 V and
  0x18 = 1.8 V. CTRL registers 0x34 and 0x3d. Enable mask 0xc0.

Samsung source remains under its upstream Linux/GPL licensing; no new blanket
license is applied to copied header. Donor source SHA-256 values and exact
compile/link commands are in kernel-003/rebuild.json. No Apple binary is tracked.

## Checks actually executed

- `python3 -B -I docs/procedures/nat-123/test_nat123.py`: 12 tests pass, real
  patched ACPM/PMIC C compiled with -Wall -Werror against synthetic SRAM/APM.
  Tests exercise readback transport failure/mismatch, wrong identity, unexpected
  enabled voltage, forbidden writes/update, wrong channel metadata, timeout,
  wrong response sequence; previous native NAT-122 archive is the negative
  analyzer control. Initial failing tests reproduced the draft defects.
- `mutate_nat123.py`: 7/7 behavioral mutants killed; compile errors do not count.
- `audit_binary.py` under recovery-rescue venv: actual ARM64 object write entry
  contains the six allowlist constants and conditional branches; masked-update
  entry is mov w0,#22; ret. This is not an exhaustive formal binary proof.
- KRN-044 kernel-003: five rebuilt objects, zero undefined symbols, 29 storage
  stubs. Kernel SHA-256 27c3f36984e67474badd43fe5d9c5eff22605d3b348c2f6138081c1def55c917.
- Build/package-002 succeeded, cmdline 248 bytes. RECOVERY SHA-256
  09acac9f78749da81744c59e402e47dc1b84b09b87de20f4b06e0c33ef3168de.
- `derive123.py --check` passes; without a decision the read-only session gate
  stopped with device_write_started=false and reboot_sent=false.
- `make check`: 448 tests pass (log in artifacts/nat-123/make-check.log).

## Next

Decision 0050 pins the final image for one NAT-124 run under decisions
0019/0044/0049. Before launch complete host task, claim separate native task,
open permit, preflight, commit decision/registry, then run once. Restore stock
RECOVERY and check Android even if the touch experiment fails. Analyze power,
chip response, reader and actual physical touch separately. No GPU/FPS claim.
