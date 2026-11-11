# NAT-061: what follows C checkpoint 21 — the payload kernel's own log and return paths (source review)

Evidence kind: **source-review**. Date: 2026-11-12. Nothing here ran on the phone. Sources read: `artifacts/nat-020/build-003/source/xnu/hackios/files/osfmk/arm64/loader_return.c`
(and `redwood.patch` for `pe_kprintf.c`/`kmoutput`), `.../e1s/patches/0011,0012,0014`, `docs/procedures/nat-029/README.md` (payload byte analysis),
`artifacts/nat-020/build-003/storage-patches.json`, the ADT of `artifacts/nat-020/build-003/e1s.adt`, NAT-036/052/059 stub and glue sources and the NAT-041/047 engine.

## Why

NAT-060 delivered the kernel's checkpoint notes up to C checkpoint 21 (the last call of `arm_init`) and the loader held there by design. The payload has no
checkpoint after `arm_init` (`machine_startup` -> `kernel_bootstrap` -> startup tasks -> IOKit), so more checkpoints would need binary patches of kernel code
(a rebuild of the kernel is blocked: KRN-001). Before doing that, this note asks what the kernel *already* offers a loader that the stub does not use yet.

## Established (source)

1. **The kernel's console text is collected in `loader_log`.** `serial_putc_crlf()` (`pexpert/arm/pe_kprintf.c`, patched in `redwood.patch`) calls
   `loader_log_putc(c)` for every character `kprintf` writes, and `kmoutput` does the same for user-space console writes. `loader_log` is a `char[1536 KiB]`
   (`LOADER_LOG_SIZE`): the first 256 KiB are kept as written (`LOADER_LOG_HEAD`), after that a 1 MiB ring (`LOADER_LOG_RING`); `loader_log_linearize()` puts the
   pieces in order (a note replaces the dropped part) and `loader_log_len` is the used length. Addresses from the payload (NAT-029): `loader_log`
   `0xfffffff007b90a00`, `loader_log_len` `0xfffffff007d10a00`. Whether `kprintf` output really reaches it on this SoC (`serial=3` is in the payload's cmdline) is **not
   measured**.
2. **`loader_jump()` hands the stub the log at every stop, not only at the end.** After `dc cvac` of `[loader_log, loader_log + loader_log_len)` it jumps with
   `x0` = PA of `loader_log`, `x1` = `loader_log_len`, `x2` = reason (0 orderly end, 2 checkpoint), `x3` = code. So at C checkpoint 21 the stub already knows where
   the kernel's text so far is and how long it is, and the NAT-036 stub already receives these in `f->x[0]`, `f->x[1]` (`nat036_report` stores them as `r->x0`, `r->x1`). The
   notes of NAT-060 do not print them. A C stop arrives with `x1 != 0` (the stub's `cbnz x1`) whenever the log is not empty.
3. **The kernel returns by itself** in these cases, all of them ending in `loader_return()` -> `loader_jump(0, 0)` (reason 0, the log in `x0`/`x1`, after the kernel
   appended its message buffer and the panic buffer): a panic (`panic_spin_forever`, `kdp_machine_reboot*`, `halt_all_cpus`: 16 call sites), the boot-arg
   `loader_return_after=<seconds>` (`loader_return_timer_init`, a `thread_call` entered at `STARTUP(EARLY_BOOT, RANK_LAST)`; it first calls
   `redwood_var_save_on_return()`, `redwood_adreno_stop()`, `redwood_wifi_stop()`, `redwood_adsp_stop()`, then `loader_return()`), and a stop request from a second core
   (`loader_live.stop`, not applicable: one core). **The payload's cmdline has no `loader_return_after`** (NAT-029 item 8), so only a panic would return today.
4. **The timed return needs timers.** `thread_call_enter_delayed` needs the kernel's timer wheel and a working timer interrupt (generic timer via the GICv3
   code: `gic_v3_irq_cpu_init`, `pe_init_fiq`). Whether these work on the S24 is **unknown** (it is part of what the run would measure); if they do not, the kernel
   idles and nothing returns.
5. **Storage is not reachable through the stubbed entry points.** `storage-patches.json` lists 29 register-only stubs (`e1s_ufs_*`, `redwood_ufs_init`,
   `redwood_ufs_quiesce`, `ufs_*`, ...). `redwood_var_save_on_return()` returns at once unless `ufs_ready` and `ufs_write_part >= 0`; both are set only inside `redwood_ufs_init()` (`redwood_ufs.c` lines 1490 and 1533),
   which is one of the 29 register-only stubs. This is containment by entry-point denial, not a hardware proof (as NAT-020 says).
6. **What the ADT puts in front of the kernel** (16 nodes): `cpus/cpu0` (`samsung,exynos2400`, reg 0), `arm-io` (`samsung,e1s-io`) with `gic` (`arm,gic-v3`,
   GICD `0x10200000`, GICR `0x10240000`), `wdt` and `disp0` (`sweet,display`) without `reg`, `sweet-fbcon` (framebuffer `0xfa200000`, `0x9a4000` bytes — the
   loader's frame buffer), `buttons`, `options`, `pram` (`reg` `0xbff00000`, `0x80000`), `sweet-ufs` (`0x17100000`, stubbed). There is no UART node; the e1s
   patches 0011/0014 keep a console ring in the kernel image (a static 1 MiB array after STR-034), also mirrored by `kprintf`.
7. **The engine can carry a log.** The NAT-041 ring is 32 KiB in the NAT-047 image, `READ_RING` serves up to 4 KiB per transfer, records carry up to 1 KiB of
   payload (`USBMON_REC_MAX`), NAT-047 already replays the loader's own RAM log in 512-byte TEXT records. The engine has **no acknowledgement from the host**
   (`written`/`oldest` only), so a dump larger than the ring must be paced; the collector (`dead_after` 30 s of consecutive failures, unchanged by the launcher)
   survives a silent kernel run of up to about that long.

## Unknown (and the check that resolves each)

| Unknown | Check |
|---|---|
| Does `kprintf` text land in `loader_log` before checkpoint 21 on this SoC? | print the log (`x0`/`x1`) over USB at checkpoint 21 (needs no further kernel execution) |
| Does the kernel run on after `arm_init` (timers, GIC, scheduler)? | resume after checkpoint 21 with `loader_return_after=N`; a reason-0 arrival is the proof, its absence (until the watchdog) is not a proof of anything but a hang |
| What does the kernel print after `arm_init` (version banner, GIC/timer init, IOKit)? | the log of the reason-0 arrival |
| What would the kernel do to hardware in 10 s? | not bounded by review (indirect calls); bound is the stop list, the 83 s watchdog and the stubs |

## Chosen design (minimal)

One image, the NAT-059 image plus:

* a **log dump** over the NAT-047 engine (TEXT records `KL <offset> <chunk>` with begin/end records), head and tail limited, paced against the ring, with the log's PA
  and length checked against the payload's `loader_log` address before anything is read;
* at the **last stop** (checkpoint 21): dump the log so far, then **resume** with no further stop (`slot[2] = 0`) instead of holding;
* at an arrival with **reason 0** (the kernel's own return): note, dump, hold (the NAT-044 deadline reset ends the run);
* the payload cmdline gets `loader_return_after=10` (a plain byte patch of the NUL-padded cmdline field; the header has no checksum).

Alternatives not chosen now: binary-patched checkpoints in `kernel_bootstrap` (new payload code, needs its own review), a second-core watcher (`bootcpu=`, needs coherent
reads of the kernel's log), and the persistent console ring read from Android after a reset (needs a root memory reader). They stay available if the run shows the kernel
does not return.

## Limits

No hardware result exists for anything past checkpoint 21. The design assumes the kernel resumes cleanly after the last stop in the same way it did after the others; `loader_return()`
itself runs unreviewed kernel code (the `redwood_*_quiesce` calls, `psci_smp_stop_others` with one core). A hang ends with the 83 s hardware watchdog, whose behaviour on this phone
has never been observed (NAT-021 never ran); the decision text for the run must say so.
