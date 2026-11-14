# NAT-191: the profiler without the interrupts-off call (host)

**Evidence kind:** host-test. NAT-192 is the native run.

## Why

NAT-190 ran NAT-189's scX image on the phone. At 200.07 s, on the e1s-pc sampler's first tick, the kernel panicked:

```
recount.c:567 Assertion failed: ml_get_interrupts_enabled() == FALSE
```

The backtrace led to `_e1s_pc_thread+0xac` and then `_recount_current_thread_time_mach`, called for the sampler's own time.

In XNU 8796 that function starts with `assert(ml_get_interrupts_enabled() == FALSE)`. Our e1s kernel is a DEVELOPMENT build, so its
asserts are live. The NAT-189 harness provided the function without that precondition, so the tests passed.

## Change (scY)

The only code change is in `e1s_display.patch`. It is NAT-189's, with the three self-time reads switched:

```
recount_current_thread_time_mach()  ->  recount_thread_time_mach(current_thread())
```

`recount_thread_time_mach` sums the thread's recorded lifetime usage, which is accumulated at each context switch. It has no
assertion. The sampler blocks every 1 ms, so the value lags by at most one tick. A comment in the patch records the reason.

Everything else stays as in scX:
- the sampler;
- the e1s-dpp snapshot stays out;
- minsize;
- the root;
- the command line, with the tag `nat_attempt=NAT191-scY`.

## Audit of every interface the object calls

These are the undefined symbols of `e1s_display.o`, each checked in the XNU 8796 source (`references/apple-xnu`) for interrupt,
preemption or lock preconditions:

- **`recount_thread_time_mach`, `recount_task_times`:** sums only, no asserts.
- **`current_thread`, `thread_tid`, `get_user_regs`, `proc_pid`, `proc_task`, `proc_best_name`:** field reads.
- **`proc_iterate`, `proc_find`, `proc_rele`:** process-list locks. Kernel-thread context is fine, and NAT-186 used `proc_iterate`.
- **`task_act_iterate_wth_args`:** takes `task_lock`, a mutex. Thread context is fine. The callback only reads.
- **`vm_shared_region_get`, `vm_shared_region_start_address` (task NULL), `vm_shared_region_deallocate`:**
  - all three assert only reference counts and the mapping-in-progress state, and `start_address` first waits until no mapping is in
    progress;
  - the reference taken by `get` keeps the count above 1 during `deallocate`.
- **`kalloc_ext` / `__zone_site_register`, from `kalloc_data(Z_WAITOK | Z_ZERO)`:** thread context.
- **`printf`, `snprintf`, `strncmp`, `bzero`, `delay_for_interval`, `absolutetime_to_nanoseconds`, `mach_absolute_time`, `PE_parse_boot_argn`,
  `kernel_thread_start`, `thread_deallocate`, `ml_cpu_idle_time`, `ml_io_map`:** as used by NAT-185/186. `ml_io_map` is only the
  original framebuffer probe.
- **`__ubsan_handle_add_overflow_minimal`:** it is a `brk` on a signed overflow, called from `e1s_top_thread`, NAT-185's code. That code
  ran through 380 s in NAT-186 and NAT-188.

## Host checks

- **`test_nat191.py`: 13 tests, all OK.**
  - NAT-189's tests run on the new harness, `host/shim191.h` and `host/fake191.c`. In the harness, `recount_current_thread_time_mach` and
    `recount_current_thread_times` print `PANIC` and abort, as on the phone.
  - A regression test runs NAT-189's patch in this harness and gets that abort, which reproduces NAT-190.
  - Another test checks that only the three self-time lines changed against NAT-189.
  - 7 mutants, all killed.
- **Object.** `nm -u` of the compiled `e1s_display.o` shows no `recount_current_*`. NAT-189's object referenced
  `_recount_current_thread_time_mach`.
- **Kernel.** The kernel (`artifacts/nat-191/kernel-001`, no-storage `dd2b9f3f…`) has 0 undefined symbols. Every segment has the same size
  as in scV/scX, and the loader sites check returns rc 0. The command line is 254 B.
- **Package and session.** Package RECOVERY `cafc0d33…`, payload `89fcb733…`. The counted session `session_nat192.py` (`d1bda36a…`) comes
  from `derive192.py`.

NAT-192 uses NAT-189's analyser `pc190.py` and symboliser `dscsym.py` unchanged.

## Lesson

**Every XNU interface called from our objects needs its preconditions read in the source.** A harness stand-in must enforce them, because the
e1s kernel's asserts are live.
