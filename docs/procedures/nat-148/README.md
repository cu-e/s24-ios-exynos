# NAT-148: scF, scE with one boot CPU in `/cpus` (host-test)

Re-registration of NAT-147 (see `docs/procedures/nat-147/README.md`). Input: NAT-146 failed on the phone. Both scE boots stopped
between loader checkpoints 35 and 12, i.e. inside `ml_parse_cpu_topology()`, before any PSCI call.

## Cause, confirmed by the kernel's own code on the host model

`model_topology.py` runs the NAT-022 payload kernel on the NAT-035 model. That model kernel has the same HackiOS `arm_init`
checkpoints and `ml_parse_cpu_topology`/`ml_is_boot_cpu` as the NAT-143 kernel. The run starts from a checkpoint-35 stop:
- the device tree is replaced in RAM (written at the ADT's PA, with `_DTSize`/`_DTEnd` set);
- `cpus=1` is blanked in `const_boot_args`;
- the run resumes to checkpoint 12 and stops early at `_Assert`.

Result `artifacts/nat-148/model-topology.json`:

| ADT | Result |
| --- | --- |
| baseline (the model's cpu0-only ADT, `cpus=1`) | checkpoint 12, num_cpus 1 |
| as built for scE (`make_adt145.add_cpus`: ten nodes, all `state` "running") | **`_Assert`: machine_routines.c:1193 `topology_info.boot_cpu == NULL`**, num_cpus 2 |
| fixed (`make_adt148.add_cpus`: cpu1–cpu9 `state` "waiting") | checkpoint 12, **num_cpus 10**, boot CPU index 0, phys ids 0x000…0x900; then the model's whole remaining chain 40, 41, 42, 43, 44, 13, 14; `master_cpu` 0 |

The as-built result matches the phone (stopped inside the topology parse, before the console). The fix passes the point where
NAT-146 stopped, as far as the model goes (checkpoint 14). The model does not run secondary-CPU start, the GIC, or anything later.

The defect comes from the donor: `tools/e1s/xnu/mkadt.py:175` gives every CPU `('state', cstr('running'))`
(`docs/e1s-smp.md`: "not device-tested"). `make_adt145` copied cpu0's property list, so it had the same bug.

## Image

`build.py` wraps `nat-145/build.py` and replaces `make_adt145.add_cpus` with the same call followed by
`make_adt148.fix_states`. It also checks the `/cpus` states inside the built payload's own ADT.

| Item | Value |
| --- | --- |
| image | `loader-diag-xnu-scF-md1`, tag `nat_attempt=NAT148-scF` (same length as scE's) |
| RECOVERY (100663296 B) | `56e9d3acfac4d0438c93c2eefb5f7da7b50ee94e4454bf613eb7c36b26386d3d` |
| payload (26206640 B) | `0788e7d812d604c6002e9096ef6b4f88d05a8b5da2e3e25ee7f73d92d3cb682a` |
| loader Image | `f1bb4ba9c8fe3475574f96bde46eb308cf32aa69b84ff120d001e10cafe1cfcf` (scE's loader with the new tag compiled in) |
| payload ADT record | `97d803733a5de648049f046a8e9960e2c90e33ea1260b5dc031b746c124c766f`; `/cpus` states running + 9 × waiting |
| kernel | `6aa8b6eb…d078`, unchanged (NAT-143/144/146) |
| cmdline | 239 bytes, scE's except the tag |
| session | `session_nat149.py` `80c97917…34cd`, counted from `session_nat146.py` (`derive149.py --check`) |

Payload byte diff against scE: 38 bytes in 11 runs. Two runs are the attempt tag in the command line. The other nine are
`running` → `waiting`, one per cpu1–cpu9 node. Nothing else changes (`test_nat148.py`).

## Tests

- `python3 -B docs/procedures/nat-148/test_nat148.py`: 9 tests (the 3 model tests skip without capstone).
- `artifacts/nat-065/venv/bin/python -B docs/procedures/nat-148/test_nat148.py`: 9 OK, about 30 s, including the model rows above.
- `make check` OK.

## For the native run (NAT-149, needs a new owner decision)

- The analyser is `nat-145/analyze146.py`, unchanged (C2/C1/C0, cpus, frame windows).
- New risk knowledge from NAT-146: a failure before the kernel feeds the watchdog (about jump + 13 s) resets into SEC_UPLOAD.
  Upload mode's automatic restart boots RECOVERY again, and only the owner's buttons end that loop:
  1. Volume Down + Side for 7–10 s;
  2. then Volume Up + Volume Down;
  3. then Volume Up into Download Mode.
- A failure later is handled as before: the kernel fails safe, or the loader deadline enters Download Mode.
- What the model does not cover: PSCI `CPU_ON` from EL1 under the retail monitor, secondary entry, the GIC redistributors of cores
  1–9, and scheduler behaviour. Any of these can still fail on the phone.
