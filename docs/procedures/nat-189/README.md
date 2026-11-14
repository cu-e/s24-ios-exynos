# NAT-189: a user-pc profiler for backboardd (host)

**Evidence kind:** host-test. Nothing here ran on the phone; NAT-190 is the native run.

## Why

NAT-186 showed the only running core (cpu0, A520 at 1958 MHz) full during the synthetic swipes. backboardd, the CoreAnimation render
server, took 76 % of it: about 30 ms of CPU per frame on home-page swipes and about 190 ms in the Today view. NAT-188 turned on Reduce
Transparency and Reduce Motion, and the cost did not change (67.27 vs 67.95 ms per frame). The per-process sampler cannot say *which
code* inside backboardd uses the time. This task adds a profiler that can.

## What scX is

scX is scV (NAT-185: NAT-110 md0 root, scU command line with the tag changed) with `bsd/e1s_display.o` rebuilt from
`e1s_display.patch`. The patch is NAT-185's patch with two changes.

**Added: an `e1s-pc` sampler thread.** From 200 s to 375 s of uptime it runs once every 1 ms:

- It finds the process named `backboardd` with `proc_iterate`, and looks it up again by name if it goes away. It takes the slid start of
  that process's shared cache from `vm_shared_region_start_address`, with no task argument, so nothing is copied in.
- It walks backboardd's threads with `task_act_iterate_wth_args`. For each thread whose run time (`recount_thread_time_mach`) grew since
  the last tick, it adds one sample at the saved user pc and one at the saved user lr (`get_user_regs`). The pc is where the thread was
  preempted, or the trap it is now blocked in.
- It keeps three tables: pc in 64-byte buckets, pc in 64 KiB buckets, and lr in 64-byte buckets.
- At 220, 265, 310 and 375 s it prints one header line and the busiest buckets: 64 fine, 32 coarse and 32 lr. Each bucket is printed as
  `c<offset>` from the cache start, or `a<address>` when it is outside the cache. Then the tables start again.
- The header line reads: `e1s-pc: END window A-B s ticks T busy N samples S tlost L self U us pid P start X`.

The sampler only reads kernel memory. It does no MMIO, no copyin or copyout, and writes no thread state. Boot-arg `e1spc=0` turns it off.
Its tables, 150 KiB, are allocated with `kalloc_data` when the thread starts.

**Removed: NAT-176's `e1s-dpp` display-register snapshot.** It was measured in NAT-177, and nothing changed between the probe and 300 s.
It had to go to make room, as the next section explains.

## Why the snapshot had to go: room in `__TEXT_EXEC`

The first build stopped at the NAT-150 gate with `rc 5, NAT036_JUMP_BAD`. The sampler code grew `__text` by 2.3 KB. scV's kernel had only
1232 bytes left in its last `__TEXT_EXEC` page, so the segment took one more 16 KiB page. That moved every later segment by 0x4000,
including the data the loader checks (`_loader_return_entered`, `_loader_log`, `_loader_recording`).

Moving the 150 KiB of static tables to `kalloc_data` was not enough on its own. Three changes together reduced the object's `__text`
growth to +704 bytes:

- the snapshot is removed;
- the sampler functions are built with `__attribute__((minsize))`;
- so are NAT-185's `e1s_top_*` functions. Their behaviour is unchanged, and the harness still checks their output.

Every segment of the scX kernel now has the same size as in scV (`__TEXT` 1671168, `__DATA_CONST` 950272, `__TEXT_EXEC` 8749056,
`__DATA` 5505024, `__BOOTDATA` 311296). The loader-sites gate passes with rc 0 and every constant names the same symbol.

**Rule for later kernel work:** any further growth of the e1s objects must stay within this slack, or it must move code out.

## Host checks

- `test_nat189.py`: 11 tests, all OK. They build the patched file against a simulated kernel (`host/shim189.h`, `host/fake189.c`). In
  the simulation, backboardd's threads run on a fixed pattern of the tick number: A 6/10, B 3/10, D 1/50 outside the cache, C never.
  The harness also simulates `proc_find`/`proc_rele` and shared-region reference counts, a restart into a new pid, a new thread every tick
  (churn), 120 extra threads (table overflow), no shared region, and failed allocation. The tests check:
  - the windows, tick counts, sample counts, buckets, top order, lr, self time and balanced references;
  - that `e1spc=0` turns the sampler off, that e1s-top is unchanged, and that the dpp snapshot and its register maps are gone;
  - the patch scope against NAT-185: only the dpp block is removed; no MMIO, copyin, copyout or thread-state writes are added;
  - 7 mutants, all killed;
  - the analyser `pc190.py` on the harness output with a synthetic symbol table.
- The kernel (`artifacts/nat-189/kernel-001`, no-storage `dc827310…`) was rebuilt by KRN-044 with 0 undefined symbols. The display
  object's compile has no new warning kinds.
- The image `loader-diag-xnu-scX-md1` has a 254 B command line, and its loader sites check returns rc 0. Package: RECOVERY `170f8c93…`,
  payload `03e586cc…`.
- `derive190.py` derives the session `session_nat190.py` by counted replacement from NAT-177's driver. Only the image, its hashes, the
  package, the decision glob, the marker and the precondition list change.

## Symboliser (`dscsym.py`)

The donor cache is the owner's iOS 16.5 20F66 copy, kept local in the gitignored `artifacts/apple-inputs/`. 7z leaves three of its files
LZBITMAP-compressed: `.symbols`, `.28.dyldlinkedit` and `.42.dyldlinkedit`. These were expanded with the donor's `unzbm` into copies under
`artifacts/nat-189/dsc-symbols/`. The original extraction is unchanged.

`dscsym.py build` reads the images and their `__TEXT` ranges (2710 images, no overlaps), every image's own `LC_SYMTAB`, and the local
symbols. It writes a local pickle of 7,159,062 function starts.

Apple's `.symbols` file shows most local names as `<redacted>`; QuartzCore has 9989 of 12750. Such a function is reported as
`image:sub_<address>`. The image is always known.

Nothing from Apple is committed. Only offsets, counts and symbol names go into reports.

## Analyser (`pc190.py`), pre-registered for NAT-190

The verdict is decided over the swipe windows (220–310 s) as follows:

| verdict | condition |
|---|---|
| **P-none** | no window line |
| **P-thin** | fewer than 2000 samples |
| **P-ok** | otherwise |

With P-ok, the analyser reports:

- the coarse-table coverage;
- the share of each group over the swipe windows, and the leading group;
- the same for the last window (310–375 s, where NAT-186 drifted into the Today view);
- the top images and functions from the fine table and from the lr table.

The groups are:

| group | images |
|---|---|
| copy | libsystem_platform |
| trap | libsystem_kernel: the thread blocked in a trap, so it was waiting, not computing |
| ca | QuartzCore |
| raster | CoreGraphics, libRIP, ImageIO, vImage, vDSP, CoreImage, IOSurface, … |
| runtime | objc, CF, dispatch, malloc, pthread, Foundation, libc++ |
| other | any other cache image |
| outside | not in the cache |

## Limits

- A thread that ran and then blocked inside a tick is counted at its trap pc. The `trap` group shows that share separately.
- Samples go only to backboardd threads that ran. If more than one ran in a tick, each gets a sample.
- The cost is one walk over the thread list per millisecond. The window header reports it as `self`; the harness assumes 5 µs per
  tick.
- Removing the e1s-dpp lines means the dpp177 analyser has nothing to read in NAT-190. It was not a measurement goal there.
