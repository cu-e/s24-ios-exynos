# NAT-151: native run of loader-diag-xnu-scG-md1: the loader stopped before the kernel (stale kernel addresses)

- **Evidence kind:** native-device (plus a host reproduction).
- **Outcome:** **fail**. The kernel did not run, so nothing about the cores was measured. The task is not complete.
- **Decision:** 0062 under 0061, one attempt, consumed (`artifacts/nat-151/native-attempt-loader-diag-xnu-scG-md1-used.json`).
- **Restore:** stock RECOVERY and Android verified.

## What ran

- **04:19:04 local:** RECOVERY a9f0eed0…6de0 written to sda18, readback equal, then reboot.
- **04:19:40:** the loader is up (1209:0001).
- The loader ran exactly as in NAT-149 up to "PREPARING XNU HANDOFF": XNU RAM zeroed, the 11 segments copied, the ADT and boot
  arguments written. The command line carries `nat_attempt=NAT150-scG`, and entry_pa is 0x90183b570.
- **04:19:45:** stage 31 (exception), then `EXCEPTION slot=4 esr=0x96000010 elr=0x800b36d4 far=0x1f935 spsr=0x800003c5`. This is a
  synchronous external abort on a data access at EL1, recorded twice by the USB engine.
- The loader's exception loop kept USB up and polled the NAT-044 deadline.
- **04:24:08:** the delivery companion gave up (`never-ready`: the receive window was never installed).
- **04:29:32:** Download Mode came up by itself ("SAMSUNG USB"), at the 595 s deadline. There was no SEC_UPLOAD and no owner action.
- **Restore:** `restore_stock.py` (venv) rc 0, then check_android pass at 04:31:04 (boot_completed=1, stock RECOVERY hash,
  user-data dirs), then assess pass.

## Cause (reproduced on the host)

The loader holds kernel virtual addresses as compile-time constants. They are checked by instruction pattern before use:
- the five `LOADER_CHECKPOINT` sites of start.s (`nat-022/src/ckpt.c`);
- `loader_jump` and `_set_mmu_ttb` (`nat-036/src/ckpt3.h`);
- the slot, the flag byte, `_invalid_ttep`, arm_vm_init's call and the log (data or other objects).

NAT-150's `start.patch` inserted mark blocks into `start_cpu` and `common_start`, so the code after them moved. In the scG kernel,
the constant addresses fall on other code (`check_loader_sites.py --kernel-dir`):

| Constant | NAT-143 kernel (scF) | NAT-150 kernel (scG) |
| --- | --- | --- |
| site 1 0x…743e068 | `_start_first_cpu+0xc` | `start_cpu+0x50` |
| site 2–3 | `_start_first_cpu+0x68 / +0x2a8` | `+0x28 / +0x268` |
| site 4–5 | `common_start+0xb4 / +0x11c` | `+0x74 / +0xdc` |
| `loader_jump` 0x…744f1cc | `_loader_jump` | `_loader_return+0x5cc` |
| `_set_mmu_ttb` 0x…74428bc | `_set_mmu_ttb` | `_ml_get_backtrace_pc+0x24` |
| slot, flag, `_invalid_ttep`, arm_vm_init site, log, recording | unchanged | unchanged |

`check_loader_sites.py` compiles the loader's own `ckpt.c` + `ckpt3.c` (`-DNAT031_HOST`, the NAT-036 harness build) from the image's
own source tree. It runs `nat036_check()` on the window that the loader copies from the image's own payload:
- **scG: rc 2 `NAT031_SITE_BAD`, site 1**;
- scF: rc 0.

On the phone the loader should then have printed "XNU checkpoint site 1 check failed". Instead it took the data abort above, so its
failure path faults after a failed check. That is a separate loader defect, not explained yet (FAR 0x1f935).

NAT-150's host model checked only the kernel's own start path. It did not check the loader's view of the kernel, so it could not see
this. The gap was in my check, not in the phone.

## What this establishes

- Any change that moves code in start.s, or in the objects that contain `loader_jump` / `_set_mmu_ttb`, breaks the loader's checkpoint
  checks. A build must pass `check_loader_sites.py` before a native run.
- The NAT-044 deadline brings the phone to Download Mode from the loader's exception loop as well (595 s), with no SEC_UPLOAD.

## Next

NAT-152 (host) will build scH, the same NAT-150 diagnostics with the loader's view intact. Then `check_loader_sites.py` rc 0 is a
build gate, and NAT-150's model and tests are re-run. Two ways to get there:
- keep every checked address in place: the marks go out of line, and a same-size branch replaces an existing one;
- or derive the loader constants from the kernel's symbols and patterns.

Separately, find why the loader's failure path faults.
