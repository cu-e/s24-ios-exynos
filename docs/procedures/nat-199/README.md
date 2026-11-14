# NAT-199: the reason for an uncaught exception, kept for the host (host-test)

**Evidence kind:** host-test. Nothing here ran on the phone. The native run is NAT-200.

## Why

NAT-198 ran ten CPUs. SpringBoard aborted twice there, at 216.4 s and 301.6 s, and never did in the one-CPU scV runs. The
symbolised abort stack is `abort` ← libc++abi ← libobjc ← `std::terminate` ← libdispatch ← `_pthread_wqthread`: an Objective-C
exception that nothing caught, on a dispatch worker thread.

Its text (`*** Terminating app due to uncaught exception 'N', reason: '...'`, then `*** First throw call stack:` and the addresses)
goes to the console. In NAT-116 that is where it was read. It lands in the loader log's 1 MB ring. On the way out, though, only an
8 KiB head and a 512 KiB tail of the 1.5 MB log reach the host. In NAT-198, 994 KB were lost in between, and with them both
aborts' text. The kernel message buffer arrives whole.

## Change against e21 (NAT-197)

One more object, `osfmk/user_exception_trace.o` (`user_exception_trace.patch`, additions only). `user_abort_trace()` already prints
the `userabort:` line and stack. It now also arms a thread call for 2 s later; the program's stderr arrives through a pipe and can
come after the abort. That call:

- **Search.** It searches the loader log, kernel memory, **read only** and without its lock, for
  `Terminating app due to uncaught exception`.
- **Print.** For each distinct text, keyed by a hash of up to 160 characters from the match, it prints once:
  - `userabort: reason: …`, up to 600 characters, anything unprintable as `.`;
  - `userabort: throw stack: (…)`, the line after `*** First throw call stack:` within the next 4 lines.
- **Count.** It ends with `userabort: reason scan: K line(s) in B bytes of the loader log, D distinct said`.

Its own printed lines carry the same text, so they hash the same and are not said again.

The code fits the `__TEXT_EXEC` page slack (112 B left), so no segment moves. Everything else, the command line included, is
e21's, apart from the tag `nat_attempt=NAT199-e2r`.

## Host checks

All on 2026-11-14:

- **`test_nat199.py`: 7 tests, OK.**
  - The harness compiles the patch's own `uar_hash`, `uar_say`, `uar_match` and `uar_scan` text with `cc`, against a synthetic loader
    log in NAT-116's real line format:
    - the reason and the throw-stack line are said once;
    - the same text again, and the scan's own output fed back into the log, are not repeated;
    - a second, different exception is said;
    - a log without the text gives only the count line;
    - unprintable bytes become `.` and the line bound is 600.
  - The patch only adds lines, and the scan never writes the log.
  - Segments equal e21's. The loader-checked symbols (`_LowResetVectorBase`, `_reset_vector`, `_start_cpu`,
    `_psci_smp_early_marks`, `_loader_log`, `_loader_log_len` …) are in place. 0 undefined symbols; the expect-string is present
    once.
  - Loader sites rc 0. The session derivation is current, and the image hashes match.
- **Mutants.** Removing the dedup, the wrong throw-stack line offset and no look-ahead lines are each killed.

## Image

`loader-diag-xnu-e2r-md1`:
- RECOVERY `artifacts/nat-199/package-001/loader-diag-xnu-e2r-md1/recovery.img`, SHA-256
  747f74e7a612f9502a3c248b154cbe302579d992b68b50a26a0d9e7f57c805de;
- payload bfc2914b00ce27cca966fa01fcc5a575c7d483a126da5c7de6cee11c0c3331e6 (26208400 bytes);
- kernel no-storage 320420f4e08ee2204f449f62c6a8585177f8caf8ce59d383915b741cfb78c6a3.

Session driver: `session_nat200.py`, SHA-256 eccf26acda1e7a885d713d5309009021817cc1ef7e464fe2f6ce1470dedd306b, derived by
`derive200.py` from NAT-198's.

```
python3 -c 'import json,subprocess,sys;a=json.load(open("docs/procedures/nat-199/rebuild-args.json"));sys.exit(subprocess.run([sys.executable,"-B","docs/procedures/krn-044/rebuild.py",*a]).returncode)'
python3 -B docs/procedures/nat-199/build.py --out artifacts/nat-199/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-199/build-001 --out artifacts/nat-199/package-001
python3 -B docs/procedures/nat-199/derive200.py
python3 -B docs/procedures/nat-199/test_nat199.py
```

## Criteria registered for NAT-200 (before the run)

`reason200.py` on the kernel text. The first match wins:

| verdict | condition |
|---|---|
| R-no-abort | no `userabort: … aborts` line (nothing to explain in this run) |
| R-none | abort lines, but no `reason scan` line: inconclusive |
| R-reason | at least one `userabort: reason:` line, with its exception name, reason and throw stack (symbolised with `--table`) |
| R-abort-no-text | scan lines, no reason line |

Reported beside it:
- `smp198`;
- the boot CPU's scV measures: display, fbcopy181, bbd188, top186, cpuclk173, touch170.
