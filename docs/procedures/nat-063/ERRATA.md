# NAT-063 errata (added 2026-11-12 by NAT-064; the pinned files of this directory are unchanged)

`README.md` and `evidence.json` of NAT-063 are pinned by hash and keep their original text. Two statements in `README.md` are superseded by the source review in
`docs/procedures/nat-064/README.md`; read them with these corrections:

1. **"+49.1 s ... the kernel handed control back by itself 1.7 s after the last stop"** and **"the kernel ran 1.7 s of host time after the last stop"** give a *host receive-time* gap as if it
   were a kernel interval. The NAT-041 engine has a 32 KiB ring and no host acknowledgement, so receive times are drain times, not creation times. The kernel's own stamps put the
   `Darwin Kernel Version` line at 39.85 and the `!BSD` line at 40.14: about 0.3 s of kernel run from after checkpoint 21 to the panic. The conclusion that the 8 s timer did not cause the return is unchanged
   (the panic did).
2. **"the timestamps carry an unnormalised microsecond field ... not used as timing evidence"**: the field is inflated by 1.024 (`rtclock_usec_divisor` is the integer 25 for the 25.6 MHz timebase), so
   real time = field x 25/25.6; with that correction the `!BSD` wait is about 102.5 ms, matching the project's 100 ms patch for `rd=md*`. `!BSD` is by design; it is not a fault.
   It also shows a thread blocked with a deadline was woken at its deadline, i.e. the timer/decrementer path worked (the README's "Timer interrupts" item is therefore partly resolved: a timer wake was observed; the
   thread-call path of `loader_return_after` is still untested).
