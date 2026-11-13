# NAT-071: a kernel window longer than 63 s — feasibility, chosen option, built kernel

Date: 2026-11-13. Owner: `claude-opus-nat071-20261113`. Evidence kind: host-test (source review + build + host tests).
No phone action.

## The bound today, from the code that runs

* `guard.c` (the e1s RECOVERY loader, NAT-020 line) arms the S5E9945 CL0 watchdog at `0x10040000` for **83 s**
  (`s5e_wdt_arm(&w, 83)`, 25.6 MHz, prescaler 256, `/128`): the counter's maximum is 65535 → the longest period this
  watchdog can have at that clock is **83.88 s** (`65535 * 256 * 128 / 25.6e6`).
* The loader pets it every 30 s (`NAT074_PET_S`) inside its own wait loops and once more just before the jump
  (`nat074_final_pet`). While the kernel runs, **nothing feeds it**: the kernel has no S5E9945 code;
  its `hv_wdt_pet` thread call is a Qualcomm-hypervisor SMC, not enabled here (`hv_wdt_pet` boot-arg absent).
* Hence `loader_return_after <= 63` (nat-079 rule: 63 s + margin < 83 s) and the 63 s window of NAT-110..113.

## Options (as the task asked)

| | A: longer loader cap | B: kernel-side feed |
| --- | --- | --- |
| Change | the loader arms a longer watchdog | the kernel feeds the same watchdog |
| Feasible? | **No**: 83.88 s is the hardware maximum at 25.6 MHz; a longer period needs another clock source for the watchdog, a new, unverified clock register write | **Yes**: two register writes the loader already does (`s5e_wdt_pet`: `WTCLRINT=0`, `WTCNT=WTDAT`), from the kernel's existing 10 s heartbeat thread call |
| New hardware access | clock-tree write (unverified) | write to the watchdog the loader armed (verified by the loader's `guard.c` decrement check on every run since NAT-020) |
| What stops a hang | the watchdog | the watchdog: a kernel that hangs makes no thread calls and stops feeding; ≤ 84 s later the phone resets |

**Chosen: B.** It needs no new kind of hardware access and keeps the watchdog as the one stop that does not depend on
the kernel being healthy.

## The change (`0001-e1s-wdt-pet.patch` on `osfmk/arm64/loader_return.c`)

* boot-arg `e1s_wdt_pet=1` turns it on.
* `e1s_wdt_window()` runs in `loader_return_timer_init` (EARLY_BOOT) before the timed return is armed. It maps
  `0x10040000`, requires `WTCON` enabled-with-reset (`0x21`) and `64 <= WTDAT <= 0xffff`, reloads `WTCNT` and **reads it
  back** (must be within 1/64 of `WTDAT`: the counter runs at ~781 Hz). Only then is the feed armed, until
  `loader_return_after + 5 s`; afterwards it stops for good.
* **Fail-safe**: if the feed is off or any check fails, `loader_return_after` is **cut back to 63 s** in the kernel —
  the window that is safe without a feed (the NAT-079 rule) — and one line says why. A boot-arg of 150 s therefore never
  runs unfed for 150 s.
* Feeding happens in `hv_wdt_pet()` every `HV_WDT_PET_SECONDS` = 10 s (≪ 83.9 s; a static assert pins the 10 s the
  message states).

What it cannot protect against: a livelock in which thread calls still run but nothing else does — the stop is then
the `+5 s` limit (≤ 89 s after the planned end), the timed return, or the loader's own NAT-044 deadline.

## Built and tested

* Kernel: `python3 docs/procedures/krn-044/rebuild.py --out artifacts/nat-071/kernel-001 --object osfmk/loader_return.o
  --patch docs/procedures/nat-071/0001-e1s-wdt-pet.patch --expect-string "e1s_wdt: fed every 10 s for %u s"
  --expect-string "cut to %u s: the watchdog is not fed"` → kernel.unstripped `da571853...`, STR-041 checks pass,
  NAT-020's 29 stubs apply → `kernel.no-storage` `3d57d66c...`. Disassembly: `loader_return_timer_init` loads
  `0x10040000`, `0x21`, `0x3f` (the 1/64 read-back) and has the `dsb`; `hv_wdt_pet` has the feed's `dsb`.
* Host tests `test_nat071.py` (11): the block is cut from the patched source as compiled and run against a register /
  boot-arg / clock model: off → window cut to 63 (or kept when shorter); refuses a disabled watchdog, `WTDAT` outside
  64..0xffff, no mapping, a counter that does not take the reload (each → unfed, 63 s); maps `0x10040000`; each feed is
  the loader's pet; stops at window+5 s and stays stopped; bound holds for windows 8..300 s.
  Mutation pass `mutate_nat071.py`: **17/17 killed**.
* The loader needs no change. The nat-079 host rule `loader_return_after <= 63` is overridden by the next image's build,
  which is safe because the kernel itself enforces 63 s whenever the feed is not proven.

## Image and window for the next run (NAT-116, see research/notes/NAT-115-post-logo-diagnosis.md)

* `loader_return_after = 150` (kernel window 150 s instead of 63 s), `e1s_wdt_pet=1`.
* Watchdog arithmetic: last loader pet at the jump; the kernel's first reload is in `loader_return_timer_init`
  (EARLY_BOOT, seconds after entry), then every 10 s until 155 s; after the timed return at 150 s the loader pets
  again on its own 30 s period. If the kernel never reaches EARLY_BOOT the watchdog resets the phone at ~84 s, as
  in every run so far.
* Loader deadline: receive cap 240 + 150 + 60 work + 25 pixel report = 475 s ≤ 600 (NAT-074 MAX_CAP_S).
* Log size: NAT-113 returned 320 KB in 63 s of kernel time with a 512 KiB return tail; a 150 s window can exceed it
  (the ring keeps the newest 1 MiB; the loader returns head 8 KiB + tail 512 KiB): the older middle may be lost — the
  KL end line reports it; the diagnostic lines of NAT-115 are printed late, so they are in the tail.

## Not established

* That the feed works on the phone (no run): the first run must check the `e1s_wdt: fed ...` line, the number of feeds,
  and that the kernel returned at 150 s rather than the phone resetting at ~83 s.
* That 150 s are enough for any later frame — a hypothesis (NAT-115).
