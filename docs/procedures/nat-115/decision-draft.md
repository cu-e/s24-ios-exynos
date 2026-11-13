# DRAFT — not a decision. NAT-116: one RECOVERY-only run of `loader-diag-xnu-sc4-md1` (NAT-115)

Status: DRAFT prepared on the host by NAT-115. It authorizes nothing. For the run, a decision file
`docs/decisions/NNNN-nat116-loader-diag-xnu-sc4-md1-single-run-YYYY-MM-DD.md` (the session driver's glob) must quote the owner's
consent for this image, name both hashes below and refer to decision 0019; then
`python3 tools/lab.py project permit --scope native --value true --decision <that file> --owner <owner>`; after the run the same
command with `--value false`.

## Image

| Item | Value |
| --- | --- |
| RECOVERY image | `artifacts/nat-115/package-001/loader-diag-xnu-sc4-md1/recovery.img`, 100,663,296 B, SHA-256 `c0642059a4ba21e1205461bedc1b448952779b27f841b750211eb1b3c3d553f9` |
| Image.payload | 26,138,512 B, SHA-256 `85c2989b3ef7d5ba4774894c3bde0f2039ef61acfe4056a097890afc02582dc1` |
| Kernel | KRN-044 rebuild of STR-041 + `docs/procedures/nat-115/kernel-combined.patch` (loader_return.c only), NAT-020's 29 stubs: `kernel.no-storage` `cc952151c8d6007fa6ccd3c0e57d0320d85f329166fa23700930b8f2af680b18` |
| Loader | NAT-113's (PX/PR pixel report, KL dump), unchanged |
| Root | NAT-110's md0 + delivered md1, unchanged (SHA-256 `4377e988...` for md1) |
| Driver | `docs/procedures/nat-115/session_nat115.py` = `session_nat113.py` + 9 counted substitutions (`derive115.py --check`) |

Command line (246 B): `rd=md1 e1sufs=0 e1sufs_probe=0 ufs_write=0 nat_attempt=NAT115-sc4 debug=0xc serial=3 cpus=1 -v
loader_return_after=150 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 rec_secs=150 rec_mb=64
e1s_wdt_pet=1 wait_dump=1 xrd=md0`. (Dropped relative to NAT-113: `sweethw=0 ufsrw=0 e1s.hold=0`, which nothing reads.)

## Question

After the Apple logo (NAT-113), does any other frame follow within 150 s of kernel time, and where do SpringBoard and
backboardd wait? More time reaching the lock screen is a **hypothesis** (H1); H2-H4 are the alternatives
(`research/notes/NAT-115-post-logo-diagnosis.md`).

## Changes relative to NAT-113 (decision 0043) and their risk

1. **The kernel writes the S5E9945 CL0 watchdog** (`0x10040000`): the same two register writes the loader does on every run
   (`WTCLRINT=0`, `WTCNT=WTDAT`), every 10 s, only after reading back `WTCON=enabled+reset`, a plausible `WTDAT` and a counter that
   takes the reload; only until `loader_return_after + 5 s`. New relative to earlier runs: the kernel touches this one register
   block. No other hardware register is touched.
2. **Fail-safe**: if any check fails, the kernel feeds nothing and cuts `loader_return_after` to 63 s itself — the NAT-113 window.
3. **The wait dump** reads kernel data structures (task/thread lists, wait queues) with the task-list lock and a *try*-lock per
   task, interrupts off per task; it prints; it writes nothing. A bug here could panic the kernel at ~150 s: the panic path returns to
   the loader (why=2 with a panic buffer), as before.
4. Window 150 s instead of 63 s; loader deadline 475 s instead of 390 s.

## What ends the run (each one independent of the kernel's health)

| Failure | What stops it | When |
| --- | --- | --- |
| kernel hangs before EARLY_BOOT | the watchdog, unfed since the loader's last pet | ≤ 84 s after the jump → SEC_UPLOAD / reset, as in NAT-021 |
| feed not proven | the kernel's own cut to 63 s | timed return at 63 s, as NAT-113 |
| kernel hangs after the feed started | thread calls stop → no feed | ≤ 84 s later |
| timed return never happens, feed still running | feed stops at 155 s | ≤ 240 s after the jump |
| loader stuck after the return | NAT-044 hard deadline 475 s → Download Mode | as in every run since NAT-074 |

Timeline from NAT-113 (measured): loader on USB +26 s, kernel start ~+201 s, return at +351 s, report +351..358 s, KL dump
~6.5 KB/s → ~80 s for 512 KiB → ~+440 s, deadline/Download Mode ~+502 s, collector window 600 s.

## Restore (unchanged, decision 0019 protocol, as NAT-109/111/113)

Download Mode at the deadline → `docs/procedures/nat-012/restore_stock.py --bus B --address A --out .../restore-trace` (stock
RECOVERY `96620b8b...`) → Android boots → `check_android.py` (RECOVERY SHA-256 readback via su, user data directories) →
`nat-013/restore_stock.py assess` must say `pass` → native permit closed.

## Pass rule (fixed now; analyser `docs/procedures/nat-115/analyze116.py`)

* `P-window`: line `e1s_wdt: fed every 10 s for 155 s`, no cut line, banner `--- loader_return_after expired ---`, the PX/PR report
  complete, Android restored. Otherwise `X-window` — the run answers nothing about H1-H4 (but tells whether the feed works).
* Then exactly one of: `H1-frame` (a recorded frame other than the logo hash `0xd5b719ed` with non-zero bytes), `H2-cpu`
  (SpringBoard's first thread runnable), `H3-wait` (it waits on a Mach port/turnstile owned by a named process),
  `H4-display` (it waits on backboardd, or backboardd on the framebuffer/IOSurface), `X-none` (no owner readable).

## What stays unknown even with a pass

Whether the panel lit the pixels (nobody looks at the screen unless the owner does); input; any GPU acceleration; any frame rate.
