# NAT-152: scH, NAT-150's early marks with the loader's kernel addresses in place (host-test)

Evidence kind: host-test. No device was used. Owner claude-opus-usb130-20261113.

## Why

NAT-151 ran scG on the phone and the loader stopped before the kernel. The loader checks ten kernel addresses fixed at compile time
(five `LOADER_CHECKPOINT` sites in start.s, `loader_jump`, `_set_mmu_ttb` and data). NAT-150's `start.patch` inserted code in front of
them, so the checks read other instructions. scH carries the same diagnostics with every one of those addresses unchanged.

## Changes against scF (NAT-148)

| Item | Change |
| --- | --- |
| `osfmk/start.o` (`start.patch`) | The `PSCI_SMP_EARLY_MARK` macro and marks 1–3 in the reset vector are NAT-150's. That code is in the reset-vector page, before every checked address. Marks 4–6 go **out of line**, after `LEXT(_start) b start_first_cpu` in the same page. Under `GENERIC_PSCI_SMP`, three existing branches are replaced by one branch of the same kind each (the originals stay under `#else`): `start_cpu`'s `b common_start` → `b Lpsci_smp_mark4` (mark, then `b common_start`); `common_start`'s two `cbnz x21, 1f` → `cbnz x21, Lpsci_smp_mark5/6` (mark, then a branch back to where the old `1f` landed). |
| `osfmk/psci_smp.o` (`psci_smp.patch`) | Byte-identical to NAT-150's: marks zeroed before `CPU_ON`, read back after a failed wait and printed with PSCI `AFFINITY_INFO`; 1 s start wait. |
| boot-arg `small_cores=0` | Replaces NAT-150's `machine_routines.o` change, which moved `_set_mmu_ttb`. `redwood.patch` reads `small_cores` in `ml_parse_cpu_topology()`. With 0, the ADT `small-core` flag sets no `l2_access_penalty`, so no core is paired as a slower core's secondary and the boot processor cannot be paired under a core that never runs (NAT-149). |

Where the original `1f` lands matters. `LOADER_CHECKPOINT` ends with its own `1:` label, so the old `cbnz x21, 1f` lands right after the
macro. A started core then still executes `E1S_BOOT_MARK 4`, and after checkpoint 5 the `MOV64 x0, SCTLR_EL1_DEFAULT` reload. The
first draft branched back past those instructions; the model reported it as a `replace` against NAT-143's trace. The labels now sit
right after each macro (`test_return_labels_where_the_old_branches_landed`).

## Gate: the loader's own check (`nat-150/check_loader_sites.py`)

`build.py` refuses an image unless two things hold:
- `nat036_check()` returns rc 0. This is the loader's `ckpt.c` + `ckpt3.c`, compiled for the host, run on the window copied from this
  image's payload.
- All 13 loader constants name the same symbol+offset as in the NAT-143 kernel.

| Image | rc | Verdict |
| --- | --- | --- |
| scH (this) | 0 | ok; `site1..5` = `_start_first_cpu+0xc/+0x68/+0x2a8`, `common_start+0xb4/+0x11c`; `_loader_jump`, `_set_mmu_ttb`, `_loader_stub_slot`, `_loader_return_entered`, `_invalid_ttep`, `_arm_vm_init+0xc08`, `_loader_log`, `_loader_recording` |
| scG (NAT-151, negative control) | 2 | `NAT031_SITE_BAD`, site 1, the failure seen on the phone |

Kernel against NAT-143's: the segment layout is the same. Symbols move only in these places, none of them held by the loader:
- the reset-vector page (the trampolines);
- `__TEXT_EXEC` from `_psci_smp_cpu_off` on (psci_smp.o grows, +252/+256);
- `__DATA` from `_psci_smp_start_fault` on (+2112: the 2 KiB marks array);
- read-only constants and strings in `__TEXT` (psci_smp's changed strings).

## Host model of the start path (`nat-150/model_secondary.py --new nat152`)

This is NAT-150's unicorn + capstone model of the built kernels, with the MMU off and its own system-register values.
`compare()` now also accepts the one extra `b` around an out-of-line block. Result: `artifacts/nat-152/model-secondary.json`.

| Case | scH | Against NAT-143 |
| --- | --- | --- |
| cpu 4, handler `start_cpu` | to `CPACR_EL1`, lr = `arm_init_cpu`, marks 1, 2, 4, 5, 6, last `0x5ec00006` | same instructions plus 5 mark blocks and their branches; registers bar x9–x12 and every system-register write equal |
| handler `resume_idle_cpu` | same | same |
| MPIDR 0x81000a00 (no cpu data) | spins, mark 3 with x0 = 0xa00 | same apart from 2 mark blocks |
| null handler | spins, mark 3 with x0 = 0 | same |
| boot processor cold start (`__start`) | to `CPACR_EL1`, no marks | **identical**: 0 instructions inserted (NAT-150 added 2 `cbz`) |

What the model does not cover: the firmware, the EL2 layer, caches and coherency, real page tables, and anything after the MMU switch.

## Build

| Item | Value |
| --- | --- |
| kernel | `artifacts/nat-152/kernel-001`, kernel.no-storage `8d62baff503ddfe75ebf388fa13e9e8bf47cf46e942b54887f5c9221b44d14b4`, 0 undefined, 29 stubs |
| image | `loader-diag-xnu-scH-md1`, tag `nat_attempt=NAT152-scH`, command line 253 B (scF's tokens, other tag, plus `small_cores=0`) |
| RECOVERY (100663296 B) | `e90fe5b00269b434b8707f565d3d4365d9ba03c72a94e9a754c86c4a16d39164` |
| payload (26206800 B) | `2a35d84282ad5570255a31c4768e84740d3bead3de1f56c5c8c3646fa70e3ca2` |
| loader Image | `48841f6ca11f8dba715ef3db3d6370c4523e9d55cf4cce4129505413f11f08aa` |
| session | `session_nat153.py` `f97f9d4bfd6228048a14648a5821b133362c5f882398fcb801b7218dcdce5e0a`, derived from `session_nat151.py` by count (`derive153.py --check`); NAT-152 added to the preconditions, decision glob `*-nat153-…`, marker `artifacts/nat-153/…` |

Payload against scF:
- same VM layout up to `__LINKEDIT`;
- md0, the ADT and everything after them are byte-identical;
- the tag and `small_cores=0` are the only command-line differences.

## Tests

| Command | Result |
| --- | --- |
| `artifacts/nat-065/venv/bin/python -B docs/procedures/nat-152/test_nat152.py` | 18 OK |
| `python3 -B docs/procedures/nat-152/test_nat152.py` | 18, of which 5 skip without unicorn |

The tests cover:
- the loader check on scH and on scG;
- where symbols move;
- the five unchanged objects;
- the patch shape and the branch-back labels;
- `small_cores` in the source, the kernel and the command line;
- the model cases;
- the printf format against analyze150's parser;
- the payload, the build record and the session derivation.

## For the native run (NAT-153, decision 0061 + its per-image file)

- **Expected without new knowledge:** the loader passes its checks as in NAT-149 and the kernel runs as in NAT-149. For each core
  that fails to start, `psci: cpu N early marks: … affinity_info S` says how far it got:
  - E0: no entry at all;
  - E1–E3: the reset vector / cpu-data lookup;
  - E4–E6: `start_cpu` / before / after the MMU.

  If cores do join, `analyze150` reports C1/C2. The 1 s waits leave the home screen near NAT-144's time, so the single-core frame
  rate can be measured too.
- **Risk:**
  - The boot processor's executed instructions are unchanged (model).
  - A started core writes only its own 128 B of marks.
  - `small_cores=0` changes the scheduler's view of the four small cores only once they run.
  - A failure before the kernel feeds the watchdog can bring NAT-146's SEC_UPLOAD loop, which the owner breaks with:
    1. Volume Down + Side 7–10 s;
    2. then Volume Up + Volume Down;
    3. then Volume Up.
  - A loader-side stop ends at the 595 s deadline in Download Mode (NAT-151).
