# VM-028: guest console source preflight

This source and diagnostic preparation does not establish kernel execution.
The tool reads existing inputs and logs; it launches no compiler or QEMU and
does not access a physical device. VM-008 namespace acceptance, image lineage,
resource admission, a root QEMU lease and independent execution review remain
separate gates.

The exact Scion, public XNU and QEMU revisions and 12 source hashes are in
[`inputs.json`](../../../fixtures/public/avf-guest-console/inputs.json).
Its 37 line facts bind the actual prepared source, rather than an inferred
donor configuration. Five console objects also match `bound_source` and
`bound_source_sha256` in the immutable VM-008 1080-object graph, whose full
SHA256 is `afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
This does not assert that those objects have been compiled or accepted.

The route is:

1. QEMU `hw/arm/virt.c` places virtual UART0 at `0x09000000`, declares
   `arm,pl011` and connects it to `serial_hd(0)`.
2. Scion `avf/shim/avfboot.c` discovers the FDT PL011 and initializes its own
   polled UART. Its early `HakiOS XNU boot` and `jumping to XNU` strings belong
   to the shim; neither establishes XNU execution.
3. The shim translates the FDT to Apple DT `/arm-io/uart0`, retaining
   `arm,pl011`, address relative to `io_base`, extent and `boot-console`.
   BCM2837 enables `VMAPPLE_UART`. Kernel `pe_serial.c` finds `uart0`, uses
   `ml_io_map(soc_base + reg[0], reg[1])`, registers the PL011 function table,
   polls flag register offset `0x18` bit `0x20` and writes 32-bit data at `0x00`.
   The separate `ns16550a` branch uses byte registers; it is not the QEMU route.
4. `PE_init_platform` calls `pe_init_debug`; `PE_init_kprintf` selects
   `serial_putc_crlf` after `serial_init`. `debug=0x8` supplies `DB_KPRT`, while
   DEVELOPMENT additionally requires `-enable_kprintf_spam` to enable kprintf.
   `arm_init.c` prints `kprintf initialized` and the selected serial mode.
   `serial=3` combines output bit1 and input bit2 without the on-demand bit64.
5. `arm_init.c` switches the console when serial output is selected and a
   device was found. `startup.c` later prints `version`; `MasterVersion` is
   22.5.0. A version banner is a later text observation, not PID1 or Stop proof.

The shim supplies `debug=0x8 serial=3` when no serial argument is supplied and
defaults `console_quiet=1`. An explicit proposed FDT append string for later
diagnostics is:

```text
debug=0x8 serial=3 -enable_kprintf_spam console_quiet=0 disable-uart-irq=1
```

Preflight checks this proposed string for omissions, conflicting duplicates and
silent/on-demand choices. It does not inspect a payload's command line or claim
to reconstruct the final combined boot args. Before a later admitted launch,
the runner/reviewer must bind payload command line, FDT append and the shim's
printed final boot args. `console_quiet=0` avoids the shim's default user-console
quiet option; `disable-uart-irq=1` requests the source-supported polling route.
No boot argument grants a build, QEMU or physical MMIO authorization.

Read-only use from the owning checkout, with new output paths:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -s \
  tools/build/avf_guest_console.py preflight \
  --main /home/egor/dev/pet/s24-ios-exynos --out artifacts/console/NEW-preflight.json
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -s \
  tools/build/avf_guest_console.py diagnose --log EXISTING-CONSOLE \
  --out artifacts/console/NEW-diagnostic.json
```

Diagnostics always report `genuine_kernel_success=false`, `pid1_success=false`
and `natural_stop_verified=false`. Anchored kernel-like markers are observations
of untrusted text. Synthetic markers/cookies, fatal/panic lines and reversed
stage order remain explicit failures even if a later banner appears. Exit0
means the diagnostic completed; it does not mean the guest passed. Exit2 means
rejected/failure/inconsistent text; exit1 means an input or output error.
Logs are streamed with a 64MiB total and 64KiB line bound. The SHA256 covers the
same bytes actually classified, and retained failure line indexes are bounded.

Compiler stdout/stderr from VM-009 must remain separate from guest console.
VM-005's genuine QEMU execution of an owned synthetic payload is explicitly
rejected as kernel success. Authored test strings in `check.py` are controls,
never guest measurements. Independent review and integrator common checks are
required before the owner closes the task.
