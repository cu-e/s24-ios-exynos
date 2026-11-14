# NAT-201: the user-exception trace on, for mediaserverd's fault (host-test)

**Evidence kind:** host-test. Nothing here ran on the phone. The native run is NAT-202.

## Why

NAT-200 found SpringBoard's abort under SMP: `NSInternalInconsistencyException`, `Invalid parameter not satisfying:
routingContextUID`, thrown in MediaPlayer, called from MediaControls on a libdispatch thread. The routing context comes from the
media server. mediaserverd has crashed with SIGSEGV in every run since NAT-118; launchd respawns it about every 5 s. Nothing has
recorded where it faults.

The kernel already has that recorder: `osfmk/arm64/user_exception_trace.c`, called first in `exception_triage_thread()`. For every
`EXC_BAD_ACCESS`, `EXC_BAD_INSTRUCTION`, `EXC_ARITHMETIC` or `EXC_BREAKPOINT` of a user thread, before delivery, it prints:
- `usertrap: NAME[PID] exception E code C0 C1: pc … lr … sp …, shared cache slide …`;
- the printable text that x0–x3, x8 or x16 point at (crash helpers leave their message in one);
- up to ten frame-pointer return addresses.

It is off unless the tunable `systrace` is set.

## Change against e2r (NAT-199)

The boot-arg cannot be used. `systrace` is also read by:
- `bsd/dev/arm/systemcalls.c`: level 1 logs every failing system call of every process, "megabytes a minute";
- `bsd/kern/kern_exec.c`: failed execs.

That would flood the 1 MB message buffer and perturb the run. The filter, `systrace_name=`, does not fit: the kernel's
`BOOT_LINE_LENGTH` is 256, and e2r's command line is 254 bytes.

So one line of `user_exception_trace.patch` differs from NAT-199's: the default of `user_exception_trace_enabled` is 1, not 0. The
other two readers keep their default of 0. Everything else is e2r's:
- the NAT-197 EL2→EL1 drop and the ten CPUs;
- the NAT-199 abort-reason scan;
- the command line, apart from the tag `nat_attempt=NAT201-e2s`.

Against NAT-199's no-storage kernel, only three things differ:
- the UUID;
- the build-path strings (`nat-199` → `nat-201`, the same length);
- one data byte, the default (0 → 1).

Every symbol and segment is where it was. The loader sites check is rc 0.

## Host checks

All on 2026-11-14.

**`test_nat201.py`: 8 tests, OK.**
- **Analyser.** `trap202.py` reads synthetic kernel text whose `usertrap:` lines are built from the printf formats in the compiled
  source, so a format drift fails the test:
  - verdicts T-none / T-other / T-media;
  - register text and frames attach to their own trap, also across an interleaved trap of another process;
  - a frame line whose trap line was lost belongs to nothing;
  - mediaserverd's sites group across respawns.
- **Patch.** It is NAT-199's plus the default line; the patched source equals NAT-199's but for that line.
- **Command line.** It is e2r's with the tag changed and no `systrace` token, under 256 bytes.
- **Kernel.** It is classified byte by byte as above. Symbols and segments are equal, both trace formats are present once, and
  loader sites are rc 0.
- **Package and session.** The package hashes match, and the counted session derivation is current.

**Mutants of `trap202.py`.** All three are killed:
- the stray-line guard removed;
- the mediaserverd filter widened and truncated;
- the slide not subtracted.

## Image

`loader-diag-xnu-e2s-md1`:
- RECOVERY `artifacts/nat-201/package-001/loader-diag-xnu-e2s-md1/recovery.img`, SHA-256
  9e21d2cb7a0b66f0c2ae151d70c431c21cdf6a9b233cc0b8b5d020332b0c1e17;
- payload 3bf77cfecf5f6e60e96e9a341ba607bb9a397c0ddf212070a5b1af9a7d3812d8 (26208400 bytes);
- kernel no-storage dd5cbc7d9c6e58935b6bd1f3e0ad96632ad43bd174040c14d1c6b09e9861c07f.

Session driver: `session_nat202.py`, SHA-256 4e565de9256aba8bd51e9b2a543f3e2b40d2f2b97ee2fd8a12a18686aa8e673b, derived by
`derive202.py` from NAT-200's.

```
python3 -c 'import json,subprocess,sys;a=json.load(open("docs/procedures/nat-201/rebuild-args.json"));sys.exit(subprocess.run([sys.executable,"-B","docs/procedures/krn-044/rebuild.py",*a]).returncode)'
python3 -B docs/procedures/nat-201/build.py --out artifacts/nat-201/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-201/build-001 --out artifacts/nat-201/package-001
python3 -B docs/procedures/nat-201/derive202.py
python3 -B docs/procedures/nat-201/test_nat201.py
```

## Criteria registered for NAT-202 (before the run)

`trap202.py` on the kernel text. The first match wins:

| verdict | condition |
|---|---|
| T-none | no `usertrap:` line: inconclusive (the trace did not run, or its lines were lost) |
| T-other | `usertrap:` lines, none of mediaserverd's |
| T-media | at least one mediaserverd `usertrap:` line: exception, codes, pc/lr, register texts and frames, symbolised with `--table`; sites grouped |

Reported beside it:
- `reason200`, whether SpringBoard aborts again and why;
- `smp198`;
- the boot CPU's scV measures.

The trace prints before delivery. A process that handles its own faults, or a debugger break, is listed too. Those are counted per
process.
