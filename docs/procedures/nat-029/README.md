# NAT-029: the payload kernel's return-to-loader contract

Evidence kind: source-review plus host-test (decoding the real payload bytes). Nothing here ran on the
phone. Date: 2026-11-10. Owner: claude-nat029-20261110-krnret.

## Why

The owner asked (2026-11-10) to run the kernel for real and to get its logs to the computer without
video in the kernel. Native run 007 (decision 0015) only ran our own stub at the kernel copy's entry
address; no XNU instruction has executed. Before building anything new, this task reads what the
payload kernel itself already offers a loader, from the bytes the loader copies
(`artifacts/nat-020/build-003/payload.bin`, SHA-256
`071bc632f7af0a6aa9b11a679c1d5a951ee80943be11669326949d0725caf544`; symbol names from the Mach-O it was
made from, `kernel.no-storage`, SHA-256
`7ceda59bdbedba4d32b80c319e35ec51fe766cf61daa648f80a0c42bbca3e407`).

Tool: `analyze_payload.py` (no disassembler; fixed instruction encodings). Cross-check:
`test_analyze.py` re-reads every site with capstone (skips without it). Output:
`artifacts/nat-029/payload-analysis.json` (local, not committed).

## Established (from the payload bytes)

1. **The kernel has a loader hook.** `_loader_stub_slot` at VA `0xfffffff00743c7f0` (PA
   `0x9e183c7f0` for the measured window base `0x9de400000`): four 8-byte words, the magic
   `"XNULDRST"` (once in the file) and three zero words that a loader fills:
   `[1]` PA of the loader's return stub, `[2]` checkpoint number to stop at (0 = none), `[3]` physical
   minus virtual address of the static image (`physical = va + [3]`, mod 2^64; for this window
   `0x19da400000`). The slot is 8-byte aligned and file-backed, so a loader with the MMU off can fill it with
   aligned stores. It is in the first segment page range that the loader already copies.
2. **The kernel's own first instruction is `b _start_first_cpu`** (`0x14000aed`, target
   `0xfffffff00743e05c`). No stub has to replace it: with the slot filled, the real entry runs.
3. **Five assembly checkpoints in `start.s`**, each the same macro (`adrp/add` slot, `ldr x10,[x9,#16]`,
   `cmp x10,#N`, `b.ne` over the stop; stop = `mov x0,#0; mov x1,#0; mov x2,#2; mov x3,#N`, clear
   `SCTLR_EL1.M`, `isb`, `ldr x9,[x9,#8]`, `br x9`):

   | N | VA | PA (window base 0x9de400000) | position |
   | - | -- | -- | -- |
   | 1 | `0xfffffff00743e068` | `0x9e183e068` | entry: DAIF masked, `x20 = x0`, nothing else done |
   | 2 | `0xfffffff00743e0c4` | `0x9e183e0c4` | VBAR set to the physical low vectors, `OSLAR` cleared |
   | 3 | `0xfffffff00743e304` | `0x9e183e304` | bootstrap page tables (V=P and KVA, 2 MB blocks) built |
   | 4 | `0xfffffff00743e408` | `0x9e183e408` | TCR/TTBR/MAIR set, TLB and I-cache invalidated, VBAR set to the virtual vectors; MMU still off |
   | 5 | `0xfffffff00743e470` | `0x9e183e470` | straight after `msr sctlr_el1` (value `0x3454593d`, M=1): **the first point with the MMU on** |

   The stop path is the macro's own: reason `x2 = 2`, code `x3 = N`, `x0 = x1 = 0`, DAIF masked,
   `SCTLR_EL1.M` cleared (C and I stay as the kernel set them), then `br` to slot `[1]`. The not-taken
   branch of each site goes to the instruction right after `br x9` (checked by the test), so a site is
   skippable; the source documents the macro as clobbering x0-x3 and x9-x11.
4. **Twenty-three C checkpoints**, `loader_checkpoint(n)` called from `arm_init`
   (`0xfffffff007431398`): n = 10, 11, 30..35, 12, 40..44, 13..21 (VAs in the JSON; the order of the
   source is 10, 11, 30-35, 12, 40-44, 13-21). `loader_checkpoint(n)` stops (via `loader_jump(2, n)`) when
   slot `[2] == n`.
5. **`loader_jump` (C path) contract**, read from the payload: it returns only if no loader is listening
   (`slot[1] == 0` or already entered). It requires `TCR_EL1.T0SZ` in 25..33 and the stub PA below
   `2^(64-T0SZ)` (the template TCR has T0SZ 26: stub PAs below 256 GiB qualify; the measured window is
   near 40 GiB). It builds a one-block 1:1 mapping of the stub in a private L1/L2 pair, cleans `loader_log`
   to RAM, sets DAIF, clears `TCR_EL1.EPD0`, loads `TTBR0_EL1` and `br`s to the stub with
   **MMU and caches still on**: `x0 = PA of loader_log`, `x1 = length`, `x2 = reason` (0 orderly end, 2
   checkpoint), `x3 = code`. The stub must turn the MMU off itself. It first calls
   `gic_v3_irq_quiesce()` (a GICv3 driver call in the kernel; whether it is safe at `arm_init` entry on
   this SoC is **unknown**).
6. **Early exceptions are reported** while VBAR is physical (set at `0xfffffff00743e0bc` to
   `_LowExceptionVectorBase` `0xfffffff00743c000`, replaced by the virtual `_ExceptionVectorsBase` at
   `0xfffffff00743e400`, just before checkpoint 4's site). All 16 low vectors branch to one handler at
   `0xfffffff00743c788` (decoded from the payload), which saves LR/SP/ESR/ELR/FAR, writes `loader_log` back
   (`dc cvac` loop) and clears `SCTLR_EL1.M`, then loads slot `[1]` (spinning if it is 0) and branches with
   `x0/x1` = log PA/length, `x2 = 1`, `x3 = ESR`, `x4 = ELR`, `x5 = FAR`, `x6 = LR`, `x7 = SP`. After
   `0x...e400` an exception vectors to a virtual address while the MMU is still off (a hang, not
   reported); after the MMU is on it reaches the kernel's normal handler.
7. **The log buffer.** `loader_log` (1.5 MiB, `0xfffffff007b90a00`, PA `0x9e1f90a00`), `loader_log_len`
   (`0xfffffff007d10a00`) and `loader_live` (magic `"XNULIVE!"`, `0xfffffff007af1210`) exist. Console
   output reaches `loader_log_putc` through `serial_putc_crlf` and `kmoutput`; 78 call sites in
   `psci_smp_note`, `say`, `redwood_*` and others append to it. Whether ordinary `kprintf` output gets there
   on this SoC depends on the kernel's serial/console path being enabled (`serial=3` is in the cmdline;
   not verified). The panic path (`panic_spin_forever`, `kdp_machine_reboot*`,
   `halt_all_cpus`, nested panic) calls `loader_return()`, which returns to the loader with the buffer
   (reason 0). 16 call sites of `loader_return` in total, among them four inside `redwood_ufs_init` and one each
   in the other `redwood_*_init` functions (what makes them fire in this image is not established).
8. **The payload cmdline** (header, from `report.json`): `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0
   ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT020-83s debug=0xc serial=3 cpus=1 keepsyms=1 -v`. It
   has no `loader_return_after` (timed return), no `bootcpu` and no `hv_wdt_pet` (that one is a
   Qualcomm-hypervisor watchdog and means nothing here).

## Not established

* Whether any of this runs on the S24. Every checkpoint is untested on hardware; the loader writes the
  slot nowhere yet (NAT-030).
* Whether the kernel's start code works with the loader's `boot_args` and window (physBase `0x9de400000`
  is above 4 GiB; the bootstrap code builds 2 MB blocks from it; only an interpreter run of the real
  bytes and a hardware run can say). NAT-030 starts with the interpreter.
* Whether the early-exception report fires for the faults that can happen (see item 6: between the VBAR
  change at `0x...e400` and the MMU enable at `0x...e464` the vector address is virtual with the MMU off).
* What `gic_v3_irq_quiesce()` does on an S5E9945 at `arm_init`, and what the `redwood_*_quiesce` calls in
  `loader_return()` touch on this phone (they are the Qualcomm port's; each is an unreviewed hardware
  access that would run on a panic return).
* The remaining C checkpoints' behaviour on this hardware (23 sites, never run).

## What a return stub in our loader has to do (from the above)

* Assembly checkpoint: arrives at EL1, MMU off, DAIF masked, `x2 = 2`, `x3 = N`. For N = 1..4 nothing is
  cached by the kernel; for N = 5 the kernel's D-cache has lines from MMU-on accesses (the macro cleans
  nothing). Our marker code only writes Device memory (the framebuffer and DECON registers), so it needs
  no coherent RAM read; reading `loader_log` after a C stop is safe because `loader_jump` cleans it.
* C path: arrives with the MMU **on** and caches on: the stub must run from the 1:1 stub block, clear
  `SCTLR_EL1` M/C, `ic iallu`, `dsb`/`isb`, set its stack, and only then call the marker code (aligned
  accesses, Device memory, like the loader).
* Early exception: MMU already off; `x3..x7` carry the exception record that the loader's marker kinds
  `ESR/ELR/FAR` already display.
* Resume (asm checkpoints only): because a site is skippable and clobbers only x0-x3 and x9-x11, a stub
  could draw, restore `SCTLR_EL1.M` (for N = 5), set slot `[2]` to the next number (cleaning that cache
  line, since the kernel may hold it after the MMU is on) and branch to the site's continuation. That would
  trace checkpoints 1..5 in one run. It is not verified; NAT-030 must check on the real bytes that nothing
  after each site reads x0-x3/x9-x11 before writing them. The C path cannot resume (`loader_return_entered`
  is set and the kernel's TTBR0/TCR have been changed).

## Transports (what exists, what each needs)

| Channel | State | Unknown / check that resolves it |
| -- | -- | -- |
| Loader-side screen (markers, later text/optical codes) | Works today for stage markers (runs 001-007). The kernel contract gives the loader the log bytes' PA and length at a return, so the loader could draw log text or a dense code. | Only if the kernel returns: a silent hang gives nothing. Bandwidth with the camera is low (run 007 repeated about 2.5 loops in 83 s). A decoder for a denser optical code is host work (no new device access). |
| S-Boot upload mode over USB | Observed, not used: after the 83 s watchdog the host saw `04e8:685d` with product `SEC_UPLOAD` about 34 s later (run 007: 117 s after start, gone at 140 s, then `SAMSUNG USB` at 145 s; earlier runs similar). | Protocol unknown; whether RAM survives the watchdog reset and whether the mode offers a dump is unknown. Resolving checks, cheapest first: (a) record the standard device/configuration/interface/endpoint descriptors in the window (read-only host USB, no bulk traffic); (b) NAT-017's reset-retention canary (a pattern in RAM before a deliberate reset, read back by some channel). |
| Kernel or loader USB gadget (DWC3 + PHY) | Not built. Large: clocks, PMU, regulators, the S5E9945 USB PHY. USB-001 has host-buildable adapters only. | Needs its own research and a decision per run; it would be the real "kernel to computer" link. |
| Storage write by the loader | Not authorized (decision 0002); no UFS driver in the loader. | Would need a decision naming a scratch area, not any existing Android partition. |
| UART | Needs a debug cable/adapter on the phone; none is documented. | Owner hardware. |
| Android side after the run (`pstore`, `/dev/mem`) | Absent on this ROM (no ramoops node, `CONFIG_DEVMEM` not set); reading RAM needs a kernel module (not authorized). | None cheap. |

## Consequence for the plan

The first real kernel run does not need a replayed first instruction or a new in-kernel print: fill the
slot, jump to the real entry (`br x16` of the existing handoff), and stop at a chosen checkpoint. That is
NAT-030. GPU work depends on a kernel that gets through `arm_init` and the IOKit/driver stage; this task
changes nothing about that ordering, and no GPU step is possible before checkpoints beyond 21 and a
working console channel exist.
