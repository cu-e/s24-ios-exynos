# NAT-101: launchd-independent heartbeat small root (`pid1-hb`)

Host build, small-root packaging, host-model tests, and mutation pass. Evidence
kind: **host-test**. Nothing here ran on a phone.

## Purpose

NAT-098 (`loader-diag-xnu-sq-md1`, inconclusive) showed Apple's `logd[16]` and
`containermanagerd[12]` running, while both `launchd`'s console-form lines and
the `com.nat085.ps` job's `ps -A` lists disappeared from the returned kernel log
(hypothesis **H-logd**, untested).

`hb` (`src/hb.c`) is a freestanding static arm64 Mach-O using raw Darwin system
calls (`svc #0x80`, number in `x16`, carry = errno in `x0`, `fork` child in
`x1 != 0`) started directly from `/redwood/etc/rc` as `/redwood/bin/hb &` before
`exec /sbin/launchd.darwin`. Every 10 s (60 rounds) it writes a `SWEET hb:` marker
line directly to `/dev/console` and forks/execs `/bin/ps` (odd rounds `ps -A`,
even rounds `ps -Ao pid,ppid,stat,comm`) with an 8 s timeout (`SIGKILL` + wait).

## Artifacts and hashes (local)

| What | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Source | `docs/procedures/nat-101/src/hb.c` | — | `92f99762ec659a21513255e9792e2d60bb9a77a8a76e1786fbcb76024cb21361` |
| Static binary | `artifacts/nat-101/hb-build-001/hb` | 16,635 | `1819a4a89ec06403fa21df2facd73ff9723c2debd03c2ec6df9d7f6717103163` |
| Small root (md0) | `artifacts/nat-101/pid1-hb/root.apfs` | 4,194,304 | `97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c` |
| Base small root | `artifacts/nat-096/pid1-sq/root.apfs` | 4,194,304 | `62801cecc5cdf1e2bfaff8c056bd02e2539295e516fe2011b82fa3d2a5a37057` |

## Checks

* `build_hb.py`: builds `src/hb.c` via NAT-077's `clang -target arm64-apple-ios16.0`
  + `lld -flavor darwin` + `mkstatic.py` pipeline and audits the Mach-O header
  (`__PAGEZERO`/`__TEXT`/`__LINKEDIT`, `LC_UNIXTHREAD`, no `LC_MAIN`, no
  `LC_LOAD_DYLIB`, no `LC_LOAD_DYLINKER`).
* `build_hb_root.py`: verifies the pinned NAT-096 base (`root.apfs` and `etc/rc`
  hashes, 25 files), adds `bin/hb` (0755), inserts the comment block and
  `/redwood/bin/hb &` before `exec /sbin/launchd.darwin` in `etc/rc`, packs
  `root.apfs` with donor `mkapfs.py`, and verifies all 26 files with both
  `verify.py content --all` (26 identical, 0 differing) and the kernel's
  `apfs-tool` (`apfs_lib`) readback (26 files compared, 0 mismatches).
* `test_nat101.py`: **39 tests pass** (`artifacts/nat-101/test-nat101.*`,
  re-verified after task transfer), including structural audits, builder
  refusals, `HOST_TEST` control-flow tests (normal rounds, hung `ps` killed
  after timeout, missing `ps`, missing `/dev/console`, failing `fork`), full
  byte-for-byte tree comparison against NAT-096's root, and byte-identical
  target compilation with `#ifdef HOST_TEST` code stripped (`test_the_host_model_code_is_not_part_of_the_darwin_binary`).
* `mutate_nat101.py`: RAM-capped passes merged by `merge_mutation.py` and
  annotated against `equivalent.json` (`mutation.json`):
  - `src/hb.c`: 311 total — 244 killed, 11 survived (all 11 in `HOST_TEST`
    wrappers / `ld()` / unreachable `return 0`, explained in `equivalent.json`),
    56 invalid.
  - `build_hb_root.py`: 208 total — 199 killed, 0 survived, 9 invalid (run with
    `--mem-mib 2560`).
  - `build_hb.py`: 152 total — 147 killed, 1 survived (explained in
    `equivalent.json`), 4 invalid.
  - Note: the 39th test (`test_the_host_model_code_is_not_part_of_the_darwin_binary`)
    was added to `test_nat101.py` after the mutation annotation pass; no target
    source file (`hb.c`, `build_hb.py`, `build_hb_root.py`) changed after it.

## Evidence levels and limits

| Level | State |
| --- | --- |
| code written | yes |
| built | yes (`hb` and `pid1-hb/root.apfs`) |
| checked in a model | `HOST_TEST` libc model + builder tests pass (39 tests) |
| ran on the S24 | **no** |
| showed real iOS UI | **no** |

`HOST_TEST` does not test the raw Darwin system-call layer (syscall numbers,
`x1 != 0` fork child flag, carry-flag error convention, or `/dev/console` routing
after `logd` starts). The Unicorn Darwin-ABI model is in NAT-102, and only a
native run tests the S24 kernel.

## Provenance / Ownership

Started and built by `claude-nat065-20261112-ramdisk` (stopped on quota limit in
session `6d8d2b72-99b6-4186-8e1f-3855e1c37544`). Transferred to
`gemini-ios-20261113-a` under `docs/decisions/0003-task-transfer-from-stopped-agents-2026-11-10.md`
for final verification, documentation, evidence recording, and completion.
