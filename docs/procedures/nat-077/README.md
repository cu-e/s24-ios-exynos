# NAT-077: root-device hash probe and padded root image (host-test)

Evidence category: **host-test**. Nothing in this directory was run on the phone. The probe has been executed (a) as a host program over
known files and over the real 2.3 GiB donor image and (b) as the final signed arm64 Mach-O under Unicorn with a small fake Darwin kernel.
Neither is the payload kernel; whether `/dev/rmd1` returns the delivered bytes is the question of NAT-078.

## What this is for

NAT-075 left the phone with a registered, empty `md1`/`rmd1` of 2,475,720,704 bytes. NAT-076 built the USB path that can fill it. To tell
"the bytes arrived" from "the bytes are readable by a user process through the kernel" without a camera, PID 1 reads the device back and
prints a SHA-256 on the console ring the host already collects (NAT-068). This directory provides that PID 1, the padded image it is
compared against and the decision draft for the run that uses both (`decision-draft.md`, for NAT-078).

## Files

| file | purpose |
|---|---|
| `src/sha256.h` | FIPS 180-4 SHA-256, freestanding (no libc, no memcpy), shared by the arm64 and host builds |
| `src/hash-probe.c` | the probe (`_start` + `probe_main`): opens the console and the root device, reads in 128 KiB chunks, prints progress and result, exits with `0x50 + PID` |
| `src/host-main.c` | host wrapper over the same C file (device = fd 3, console = stdout) with fault-injection hooks for the tests; prints a `HOSTSTAT` line on stderr (how often each hook acted) so a test can tell that a hook was really exercised |
| `build.py` | builds the arm64 Mach-O (clang 18.0.2 from the Android NDK, LLD, `mkstatic.py`) and the host program; deterministic; writes `hash-probe.json` with sizes, hashes and the sanitized commands |
| `mkstatic.py` | turns LLD's output into the static, ad-hoc signed Mach-O the payload kernel can take as `rd=md0`; refuses anything it cannot lay out safely |
| `pad_root.py` | pads a root image with zeros to a 16 KiB multiple, verifies by read-back, records both digests |
| `probe_vm.py` | Unicorn harness: the final Mach-O plus a six-syscall fake kernel |
| `test_nat077.py` | 108 tests (21 need Unicorn and skip without it) |
| `mutate_nat077.py`, `equivalent.json`, `mutation.json` | mutation pass over `sha256.h`, `hash-probe.c`, `mkstatic.py`, `pad_root.py` |
| `decision-draft.md` | question, observables, budgets and pass rule for NAT-078; not a decision |

## How to run

```
python3 -I docs/procedures/nat-077/test_nat077.py                     # 108 tests, 21 skipped (no unicorn)
artifacts/nat-065/venv/bin/python -I docs/procedures/nat-077/test_nat077.py   # all 108
python3 -I docs/procedures/nat-077/build.py --out artifacts/nat-077/build-NNN  # --out must not exist
python3 -I docs/procedures/nat-077/pad_root.py SRC DST --record JSON [--expect-padded-bytes N]
artifacts/nat-065/venv/bin/python -I docs/procedures/nat-077/mutate_nat077.py --out artifacts/nat-077/mutation-runN --jobs 10
```

`make check` does not run these tests (it discovers `tests/` only); `evidence.json` lists the commands and exit codes that were run.

## The probe

* Opens `/dev/console` (exit `0x60` if it cannot), then `/dev/rmd1` (`0x61`), and reads it in 131072-byte chunks into a 128 KiB stack
  buffer, retrying `EINTR`. A failing read ends the run with `0x62`; an empty device with `0x63`.
* Prints, using `write(2)` only:

  ```
  *** SWEET hash probe: init running as PID 1 ***
  SWEET hash: reading /dev/rmd1 in chunks of 131072
  SWEET hash: at=134217728 sha256=<digest of the first 128 MiB> sec=S.mmm        (every 128 MiB)
  SWEET hash: bytes=<total> sha256=<digest> sec=S.mmm
  SWEET probe: done, exiting
  ```

  The progress digests are prefix digests, so a cut-short or corrupted run still localises the first bad 128 MiB.
* Exit status `0x50 + PID` (81 for PID 1, the convention of NAT-068/NAT-075).
* No global variables, no `__DATA`: all state lives on the stack. Time comes from `gettimeofday`.
* File descriptors: whether the payload kernel hands PID 1 open stdio descriptors is not established, so the probe makes no assumption.
  The tests run it with a first descriptor of 0 (the console is descriptor 0, the device 1), of 3, and with a device that is handed
  descriptor 0 (`fd_plan=[5, 0]`); `fd < 0` is the only failure test. A first version of the host unreadable-device test hung because
  fd 3 was closed and the "device" opened as the console pipe; the test now uses a nonexistent device path.
* SHA-256 is a from-scratch implementation of FIPS 180-4 (no third-party code is included, so there is no third-party licence or
  attribution to record; the file is original project code). It is checked against the FIPS vectors, lengths 1–299, every chunk
  boundary, short reads, a 513 MiB sparse input (more than 2^32 bits) and, for the real image, `hashlib`.

## Toolchain finding

The project's `mkinit.py` accepts one position-independent `__text` from an object file, so C needs a linker. The NDK's LLD
(`-flavor darwin`) links `-arch arm64 -platform_version ios 16.0 16.0 -e _start`, but **ignores `-static`**: it places `__text` at 0x4000
and emits a layout the payload kernel's loader does not take. `mkstatic.py` re-lays the output out: sections move by a multiple of
4 KiB (so every ADRP distance stays valid), the file gets `__PAGEZERO`, one 16 KiB `r-x` `__TEXT`, `__LINKEDIT` with an ad-hoc
CodeDirectory (made with `mkinit.code_signature`, identifier `org.sweet.init`), `LC_UNIXTHREAD` with `pc = _start`, `sp = 0` and
`LC_CODE_SIGNATURE`. It refuses non-arm64 files, relocations, rebase/bind/lazy/chained-fixup data, dylib loads, undefined symbols,
writable data (a writable global lands in `__DATA`), sections out of order and a result that does not fit one 16 KiB text segment.

The pinned `mkinit.py` is checked by SHA-256 (`2200a8b3225ffc42cbec33747d74fc3562012fb5a2882b8ab5795d453a90ce03`) before it is imported.

## The padded root image

The donor-recipe image is 2,475,712,512 bytes. The md1 reserve NAT-075 registered is 2,475,720,704 bytes (0x93908000, a multiple of
16 KiB). `pad_root.py` appends 8192 zero bytes, verifies size and read-back, refuses a size that is not a multiple of 4096 (the unit
can be set, default 16384) and writes `padded.json`:

```
source_bytes 2475712512  source_sha256 6304b2c54d56055e8df7b2b63dcbe79a9415d860b598cb8e11bda5eed47e150f
padded_bytes 2475720704  padded_sha256 552800ff3ac3de129b550c838681d0cb1d08cc4df0d38b2dc1088a9b258a8258
padded_pages 151106 (16 KiB)  padded_sectors_512 4835392
```

The padded image is Apple-derived (system volume of the pinned IPSW through the donor recipe) and stays in `artifacts/nat-077/`
(gitignored). Only its size and hashes are committed. The host build of the probe's own C over it prints the same digest in 6.6 s.

## Mutation pass

`mutate_nat077.py` applies one change at a time (operators, comparison direction, literals, deleted statements, forced conditions) to
`src/sha256.h`, `src/hash-probe.c`, `mkstatic.py` and `pad_root.py`, runs the whole test file against each in a private copy and records
whether a test failed. A mutant that does not build or parse is *invalid*; one that survives needs an entry in `equivalent.json`
(file, line, description, reason) or the run exits 1. Third pass (`mutation.json`):

| file | candidates | invalid | killed | survived |
|---|---|---|---|---|
| `src/sha256.h` | 433 | 58 | 365 | 10 |
| `src/hash-probe.c` | 317 | 56 | 227 | 34 |
| `mkstatic.py` | 421 | 10 | 410 | 1 |
| `pad_root.py` | 140 | 3 | 129 | 8 |
| total | 1311 | 127 | 1131 | 53 |

All 53 survivors were read and have a reason (48 distinct entries: the three survivors of line 230, the three of line 151 and the two of line 155 share one entry each): array
sizes one larger, `put_dec` width 0 versus 1 (the digits come from a do-while), the host shim's return values that nothing reads,
`unit & (unit - 2)` for multiples of 4096, reads of zero bytes, the schedule word w[16] that is overwritten before use, and so on.
The first pass left 210 survivors and the second 66; the gaps they showed were closed by tests (descriptor numbering, the Unicorn
stack content, every wrapper refusal and boundary, the padder's fallback paths, all five dylib commands, a section segment name of
16 characters, a device handed descriptor 0, the real-clock path). A survivor list is not a proof of correctness: the generators change
one token at a time and do not model a wrong design.

The runner runs each test pass in its own session and kills the whole process group on a timeout: the first passes left `host-probe`
processes of hung mutants running (four were found and killed by PID).

## What is established, what is not

Established (host-test): the probe's C code computes SHA-256 correctly in the cases above and produces the stated text and exit codes
in each error case, including short reads, `EINTR`, a backwards clock and short console writes; the final signed Mach-O parses with an
independent Mach-O/CodeDirectory reader, runs under Unicorn from `_start` with an unaligned stack, issues only exit/read/write/open/getpid/
gettimeofday with the Darwin register convention and returns the right digests; the wrapper refuses the listed inputs; the padder pads,
verifies and refuses as stated; the mutation pass (`mutation.json`) shows the tests notice changes to the four source files (1131 of 1184 valid mutants killed, the other 53 explained).

Not established: that the payload kernel starts this Mach-O. The probe that did boot as PID 1 in NAT-075 (`probe-init`, 16635 bytes, SHA-256
`b3decc84…761a6`) has the same header, the same `__PAGEZERO`/`__TEXT` (16 KiB, r-x)/`__LINKEDIT` segments and the same `LC_UNIXTHREAD`/
`LC_CODE_SIGNATURE`; the new file (16635 bytes, SHA-256 `dc5c7845…58b7`) differs in having four `__TEXT` sections instead of one (a
header comparison made for this README) and in its code; that `gettimeofday` returns usable time at that point of the boot; the semantics of reading `/dev/rmd1`
through `mdevrw` (alignment, short reads); the device-side SHA-256 speed (scalar C; an ARMv8 SHA2-extension variant would be an
optimisation, not needed for correctness); anything about delivery, USB rate, U5 and the watchdog (NAT-078, NAT-071).

## Deviations from the registry text

* The acceptance wording says "an included public-domain or permissively licensed implementation". The implementation is written from
  FIPS 180-4 for this task, so there is nothing to include or attribute; the correctness evidence is the test suite (FIPS vectors,
  `hashlib` agreement on the host build and on the real image).
* The Mach-O is built with LLD plus `mkstatic.py` rather than `mkinit.py` alone (see Toolchain finding).
* The registry cannot extend NAT-078's dependency list. Two prerequisites that this work shows to be necessary were registered as separate host
  tasks: NAT-079 (the delivery loader: the NAT-076 engine in the NAT-074 loader) and NAT-080 (session driver and analyser). `decision-draft.md`
  section 8 names them as preconditions; NAT-078 must not be claimed before both are done.
