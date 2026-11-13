# NAT-115: why no frame follows the Apple logo (NAT-113) — evidence, hypotheses, the next experiment

Date: 2026-11-13. Evidence kind: source-review of the NAT-113 kernel text (`artifacts/nat-113/analysis/kernel-text.txt`,
SHA-256 `1b87e84f...`) and of donor documentation. Nothing ran on the phone for this note.

## What the NAT-113 log shows after the logo

| Time (kernel clock) | Event |
| --- | --- |
| 189.39 / 189.77 s | backboardd[16] / SpringBoard[13] spawned |
| ~227.98 s | hakios hooks: `no accelerated renderer; the software one will draw`, `render_update -> 0x1` |
| 229.03 / 229.10 / 229.18 s | backboardd swaps 1-3 (surfaces 2, 2, 4, 1125x2436 BGRA). The recording holds 3 identical frames = the Apple logo |
| 229.2 → 250.4 s (return) | **no swap, no IOMobileFramebuffer selector call, no new IOSurface**. Meanwhile launchd spawns on demand: datamigrator (third time), profiled, misagent, tccd, online-auth-agent, fontservicesd, UserFontManager (pids 46-52); `memorystatus_update` traffic; failed lookups (analyticsd, cloudd, identityservicesd, mobileassetd, powerlog...) |
| hb round 5 (~232 s) → round 6 (~242 s) | SpringBoard alive, state `Ss` (sleeping); CPU 5.25 s → 5.53 s between hb rounds 3 and 5 (+0.28 s in ~22 s) |
| same | lsd: 5.21 s → 12.46 s CPU (+7.3 s in ~22 s, **~33 % of the only CPU**), state `R`; 454 `denied attempt to escape CPU monitor` lines; containermanagerd 2.37 → 6.49 s (+4.1 s), usermanagerd +1.3 s |

backboardd draws whatever CoreAnimation's layer tree holds; the boot logo stays until SpringBoard commits its first
scene (the lock screen). So the question is why SpringBoard did not commit a scene within ~21 s after the logo.

## Hypotheses (none established)

| ID | Hypothesis | For | Against / open | Observation that decides |
| --- | --- | --- | --- | --- |
| H1 | **SpringBoard is still starting**; more time is enough | Donor (HakiOS/Scion `docs/getting-started/qemu.md` l.38, one emulated core): "Apple logo at about one minute, home screen at about five"; here the logo came 39 s after SpringBoard's spawn, and on-demand daemons were still being started at the end | SpringBoard used only 0.28 s CPU in the last ~22 s: it was mostly **waiting**, not computing | a longer window: does a swap with new content follow, and when |
| H2 | **CPU starvation on `cpus=1`** (lsd, containermanagerd) | lsd ~33 % CPU, CPU-monitor denials; NAT-109: 71 processes delayed swaps ~40 s | SpringBoard sleeping (S), not runnable (R), in both late ps lists: starvation would show R | a run where lsd is limited/absent; or per-thread wait states |
| H3 | **SpringBoard blocks on a service that is absent or never answers** (an XPC reply that never comes) | many failed lookups (identityservicesd, analyticsd, cloudd...) — those fail fast, but a *present* daemon that never replies (datamigrator restarts 3x; containermanagerd busy; lsd) would hold SpringBoard indefinitely | not identified | **which port/process SpringBoard's main thread waits on** (kernel: `block_hint` + wait owner) |
| H4 | **backboardd/display state**: SpringBoard's scene is ready but backboardd does not swap (unimplemented IOMFB selectors 15, 17, 22, 27, 29, 33, 50, 55, 57, 68, 84 answer "not implemented") | the selectors are called once at start; backboardd went on to swap 3 times after them | backboardd sleeping too; no selector calls after 229.18 s | backboardd's main-thread wait; a swap counter over a longer window |

The owner's note stands: more time reaching the lock screen is a **hypothesis** (H1), and NAT-113 alone cannot
separate H1-H4: SpringBoard sleeping fits H1 (waiting on daemons that are slowly coming up), H3 and H4.

## What the next image must measure (NAT-116, prepared on the host; needs a decision to run)

1. **Window**: 150 s of kernel time instead of 63 s (NAT-071's kernel feed; `loader_return_after=150`, `e1s_wdt_pet=1`).
   The swap count and times after 229 s answer H1 directly: a new swap with *different* surface content → H1 (and the
   recording shows what it is); none in 150 s → H3/H4 become the main line.
2. **Wait states at the end**: just before the timed return, the kernel prints, for SpringBoard and backboardd (and lsd,
   containermanagerd), each thread's state, `block_hint` and — for Mach port waits — the owning process of the port (the
   stackshot `kdp_mqueue_*_find_owner` logic already in this kernel), plus run/system time. This separates H2 (R state,
   CPU) from H3/H4 (S state, waiting on a named process).
3. **Pixels**: unchanged PX/PR report (rec_secs=30 starting at the first swap would end at ~259 s; with the ring,
   `rec_ring=1` keeps the *last* 30 s, which then covers any late frame).

Items 2 and 3 need the kernel rebuild loop (KRN-044, done) for item 2 only; the boot-args for 1 and 3 are existing.

## Pass rule for NAT-116 (fixed before the run)

* `P-window`: the `e1s_wdt: fed ...` line is present, the kernel returns by its timer at 150 s (banner
  `--- loader_return_after expired ---`), the KL dump and PX/PR report arrive, and stock RECOVERY + Android are verified.
  Without this the run answers nothing about H1-H4.
* Then exactly one of:
  * `H1-frame`: ≥ 1 swap after 229 s whose recorded frame hash differs from the logo's (`0xd5b719ed`); the PX thumbnail
    shows it.
  * `H2-cpu`: no new frame; SpringBoard's main thread runnable (R) in the final dump, lsd/containermanagerd dominating CPU.
  * `H3-wait`: no new frame; SpringBoard's main thread waits on a Mach port whose owner is a named process (that process
    is the next target).
  * `H4-display`: no new frame; SpringBoard waits on backboardd, or backboardd waits on the framebuffer/IOSurface.
  * `X-none`: none of these is readable (state the gap).
