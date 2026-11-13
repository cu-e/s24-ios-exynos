# NAT-146: native run of loader-diag-xnu-scE-md1 (ten CPUs): the kernel stops inside `ml_parse_cpu_topology()`

- **Evidence kind:** native-device.
- **Outcome:** **fail** (task not complete).
- **Decision:** 0059, one attempt, consumed (`artifacts/nat-146/native-attempt-loader-diag-xnu-scE-md1-used.json`).
- **Restore:** stock RECOVERY and Android verified.

## What ran

| Time (local, 2026-11-14) | Event (`artifacts/nat-146/run-001/usb-events.jsonl`) |
| --- | --- |
| 02:42:52–02:42:59 | preflight; RECOVERY ffa91748…c80f written to sda18; readback hash equal; reboot |
| 02:43:26 | loader 1209:0001 up (boot 1) |
| 02:44:41 | root delivered: 2475720704 B at 38.114 MB/s |
| 02:46:12 → 02:46:18 | loader gone → **04e8:685d "SEC_UPLOAD"** (Samsung upload mode, the bootloader's crash state) |
| 02:46:26 → 02:46:28 | upload mode restarted the phone by itself → **our RECOVERY again** (boot 2, no delivery: the session delivers once) |
| 02:52:09 → 02:52:15 → 02:52:34 | again SEC_UPLOAD → restart → loader (boot 3) |
| ~02:57 | owner: forced restart and Volume Up + Volume Down → Download Mode ("SAMSUNG USB" 04e8:685d, 02:57:20) |
| 02:57:2x | `restore_stock.py` (venv) rc 0: PIT 8192, 100663296 B acknowledged, 0x67/0 and 0x67/1, normal reboot |
| 03:02:19 | `check_android.py` pass: boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, stock RECOVERY hash, user-data dirs; assess pass |

The session's own stop path did not end the run. That path is the kernel's timed return, the loader's log dump and the deadline
into Download Mode. It was never reached. Instead, each reset went into upload mode, and upload mode's automatic restart booted
RECOVERY again. This boot loop needed the owner's buttons. It wrote nothing beyond RECOVERY, and Android was unharmed.

## Where it stopped: loader checkpoint records

The kernel reports C checkpoints to the loader's USB log (`archive/boots/*/payload.bin`, `CK n=… last=…`):

| Run | Last checkpoints received |
| --- | --- |
| NAT-144 (scD, `cpus=1`) | … 35, **12, 40, 41, …, 21** (28 records) |
| NAT-146 boot 1 (scE) | … 32, 33, 34, **35** (12 records), then nothing |
| NAT-146 boot 2 (scE, no root) | … 32, 33, 34, **35** (12 records), then nothing |

`loader_checkpoint(35)` is the call immediately before `ml_parse_cpu_topology()` in `arm_init`, and `loader_checkpoint(12)` the
one immediately after (HackiOS `xnu/hackios/redwood.patch`). Both scE boots therefore stopped **inside `ml_parse_cpu_topology()`**.
That is before the console, before the kernel's watchdog feed (NAT-144: `e1s_wdt: fed every 10 s` at 108.10 s, about 13 s after the
jump), and before GenericARMPE. **No PSCI call was made.**

The resets came 86 s (boot 1) and about 89 s (boot 2) after the jump, the length of the bootloader-armed watchdog (≈ 83 s) the
kernel had not yet taken over. This fits an early panic or spin that leaves the watchdog unfed.

## Cause (source review; host model check is NAT-147)

`ml_parse_cpu_topology()` (STR-014 derive-001 `osfmk/arm64/machine_routines.c:1035-1240`) takes a CPU as the boot CPU when its
`state` property is `"running"` (`ml_is_boot_cpu`, line 910). For each boot CPU it executes
`assert(topology_info.boot_cpu == NULL)`.

The scE ADT gives **all ten** CPUs `state = "running"`. `make_adt145.add_cpus` copies cpu0's property list, and so does the donor's
`tools/e1s/xnu/mkadt.py` (line 175), which `docs/e1s-smp.md` marks "not device-tested". cpu1 is therefore a second boot CPU, and
the assertion fails at the second `/cpus` child, before serial output exists.

With `cpus=1` the loop stops after cpu0 (`num_cpus >= cpu_boot_arg`), so no earlier run could see this.

Not the cause: HAS_CLUSTER is not defined for E1S, so all CPUs fall into one logical cluster (no `MAX_CPU_CLUSTERS` = 4 overflow).
The secondary-entry lookup in `start.s` already matches Aff1|Aff0 under GENERIC_PSCI_SMP.

## Analyser

`analyze146.py` needs the kernel ring, which comes only with the timed return's log dump. No dump was sent, so there is no
verdict line. `artifacts/nat-146/analysis/` is empty, by design.

## What this establishes

- The ten-CPU ADT as built stops the kernel before checkpoint 12. The checkpoint records of both boots agree, and NAT-144's
  one-CPU image passes the same point.
- An early-kernel failure on this phone resets through the bootloader's watchdog into SEC_UPLOAD. Upload mode's automatic restart
  boots RECOVERY again, so **the run cannot end by itself**. This is a new limit of the stop mechanism. Every later image that can
  fail before the kernel feeds the watchdog must plan for it (see Next).

## Not established

- The exact instruction where it stopped (no kernel ring). The assertion is the source-review explanation; NAT-147 runs the
  kernel's own code on the host model with both ADTs.
- Anything about PSCI CPU_ON, the secondaries, or the frame rate with ten CPUs.
- What the panel showed (not asked during the loop).

## Next

1. NAT-147 (host): the ADT fix (`state = "waiting"` for cpu1-9, same 8-byte length), proven on the NAT-035 kernel model. The
   all-"running" table should reach `_Assert` inside `ml_parse_cpu_topology`; the fixed one should reach checkpoint 12 with
   num_cpus 10 and boot_cpu = cpu 0. Then a rebuilt scE image.
2. A rerun needs a new decision with this verifiable reason, and the owner at the phone ready to break a SEC_UPLOAD loop with
   Volume Down + Side (forced restart) and then Volume Up + Volume Down into Download Mode.
