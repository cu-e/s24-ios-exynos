# NAT-190: backboardd profiler run (native, decision 0077): FAIL, kernel assertion at the first tick

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scX-md1 (NAT-189), one run on 2026-11-14 (reboot 07:24:23Z).
Afterwards stock RECOVERY was restored with a full hash check, and Android was verified:
- `restore-001/report.json`, from the nat-012 trace;
- nat-013 assess: pass;
- `check_android.py`: pass, recovery_hash_match true.

## What happened

Up to 200 s, the image behaved like scV:
- home screen with pixels on the panel;
- driver K2 at 2.26 ms per frame, idle 8.7 fps;
- cpu0 at 1958 MHz (C2);
- touch P1;
- both samplers' threads started at 122.77 s.

At **200.07 s**, the e1s-pc sampler's first tick, the kernel panicked:

```
panic(cpu 0 caller ...): recount.c:567 Assertion failed: ml_get_interrupts_enabled() == FALSE
backtrace: _e1s_pc_thread+0xac -> _recount_current_thread_times(.cold.1) -> _Assert
```

Without the fed watchdog, the loader reached its deadline and went to Download Mode by itself. No button was needed.

**Cause.** The sampler read its own CPU time with `recount_current_thread_time_mach()`. That function may only be called with interrupts
disabled, and our DEVELOPMENT kernel checks the assertion. The sampler thread runs with interrupts on.

The host harness provided a stand-in without that precondition, so the tests passed.

**Not affected:** the sampling path itself (`recount_thread_time_mach(thread)`, `get_user_regs`, `task_act_iterate_wth_args`) has no such
assertion. It had not run yet when the panic came.

## Verdicts

- **pc190: P-none.** No window line was printed.
- **top186: U-none.** Its first span would have been at 205 s.

The run answered nothing about the profile. It does give one finding: **the e1s kernel is a DEVELOPMENT build with live `assert()`s**.
Every kernel interface used from our objects needs its preconditions checked in the source, not only in a harness.

## Follow-up

**NAT-191 (host):**
- read the self time with `recount_thread_time_mach(current_thread())`. It is accumulated at each context switch, has no interrupt
  precondition, and the sampler blocks every 1 ms, so it is current enough;
- make the harness abort on any call of `recount_current_thread_time_mach` / `recount_current_thread_times`;
- review every other interface the sampler calls for `assert`s.

**NAT-192:** the native rerun under its own decision. The new verifiable reason is the identified assertion and its host-checked fix.
