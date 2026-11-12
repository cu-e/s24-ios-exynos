# NAT-079: the delivery loader `loader-diag-xnu-rx-md1` (host-test)

Evidence category: **host-test**. Nothing in this directory was run on the phone. The receive phase was compiled twice (arm64 for the loader,
host `cc` for a fixture) and run (a) as arm64 code under Unicorn on its own and inside the real loader build with the NAT-076 DWC3 model
behind the USB engine, and (b) as host code against the same model. None of that is the Exynos 2400 controller, the S24's DRAM or its caches.

## What this is for

NAT-075 left the phone with a registered, empty `md1`/`rmd1` of 2,475,720,704 bytes (4096 MiB window, 16 KiB pages). NAT-076 made a USB
bulk-OUT receive path for the engine, NAT-077 made the PID 1 that reads `/dev/rmd1` back and prints a SHA-256. This directory joins them in the
loader: the engine comes up with the bulk-OUT endpoint present, the loader tells it where the reserve is, waits until every byte has been
committed or a cap passes, reports what happened and boots the payload kernel whatever the result (as NAT-074/075 did). It builds the image
that the NAT-078 run would use and a template for the decision that run needs. NAT-078 itself is **not** run, and no decision exists for it.

## Files

| file | purpose |
|---|---|
| `src/nat079_impl.h` | the receive phase (`nat079_receive_root`) and its pure helpers; included by the loader build and by the host fixture, so the host build runs this exact text |
| `src/nat079_fixed.h` | status codes, constants, `struct nat079_result` (the part of the generated `nat079.h` that does not depend on build parameters) |
| `make_variant79.py` | applies exact-match hunks to the NAT-074 loader tree (`markerlib47.c`, `loader.c`), copies the two headers in, generates `nat079.h` with the parameters; a hunk that does not match exactly once is an error |
| `build.py` | the build: NAT-074's chain with the NAT-076 engine and the hunks above; states and checks the time rules; `--ramdisk` replaces the md0 init |
| `fixture79.c`, `test_e2e79.py` | host fixture around the same header, model-backed end-to-end tests (20) |
| `test_nat079.py` | 90 tests: helpers, hunks, parameters, rules, the compiled loader code in Unicorn |
| `mutate_nat079.py`, `equivalent.json`, `mutation.json` | mutation pass over `nat079_impl.h`, `nat079_fixed.h`, `make_variant79.py`, `build.py` |
| `decision-template-nat078.md` | the template for the NAT-078 decision: question, image hashes, timeline, sequence, observables, pass table (rows 1-10), preconditions, deviations. Not a decision |

## How to run

```
TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-079/test_nat079.py     # 90 tests (needs unicorn, cc, zig)
TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-079/test_e2e79.py     # 20 tests
python3 -I docs/procedures/nat-079/build.py --out artifacts/nat-079/build-NNN --loader-source artifacts/nat-020/build-003/source \
        --ramdisk artifacts/nat-077/build-final3/hash-probe                       # --out must not exist
python3 -I docs/procedures/nat-044/package.py --build artifacts/nat-079/build-NNN --out artifacts/nat-079/package-NNN
artifacts/nat-065/venv/bin/python -B -I docs/procedures/nat-079/mutate_nat079.py --out artifacts/nat-079/mutation-runN --jobs 10
```

Use `-B`: with `-I` the interpreter ignores `PYTHONDONTWRITEBYTECODE`, and a file rewritten within the same second with the same size is then
served from a stale `.pyc` (this produced a false "the original fails" during a manual mutant check). `TMPDIR` must be on a volume with room:
the shared `/tmp` of the Claude Code session is a small tmpfs that returned `Disk quota exceeded` during the mutation passes (see below).

`make check` does not run these tests; `evidence.json` lists what was run.

## What changes against NAT-074's loader

Base: the tree `make_variant.patch_tree()` of NAT-074 has produced from `artifacts/nat-020/build-003/source` (NAT-065/NAT-052/NAT-047 loader
sources, GPL-2.0; full SHAs in `artifacts/nat-079/build-003/build.json`, which also records the SHA-256 of every file of the NAT-076 engine and of
the four sources here). The engine is NAT-076's (`docs/procedures/nat-076/engine/`, itself the NAT-041 engine from the vendor DWC3 code pinned
at `references/s24-linux` `417484173abc2c4fa93e738ea82ad9f2e84911b1`, GPL-2.0) compiled from its own directory, unmodified.

* `markerlib47.c`: the engine is brought up with the bulk-OUT endpoint present and a **512-byte placeholder** destination
  (`NAT079_HOLD_BYTES`). Enumeration happens before the loader knows where the reserve is, and the descriptor the host reads depends on
  whether the endpoint exists. The project's sender refuses a file larger than the capacity `GET_RX` reports, so nothing reaches the placeholder
  from the project's tools; a host that sends anyway is detected (`NAT079_PREMATURE`).
* `loader.c`: one call, `nat079_receive_root(win_base, mem_end, kernel_end - NAT074_RESERVE_BYTES, NAT074_RESERVE_BYTES, &r)`, between the
  checkpoint-slot installation and the final cache clean, then the result as `key=0xHEX` records (`nat079_status`, `_pa`, `_bytes`,
  `_committed`, `_rx_bytes`, `_trbs`, `_errors`, `_resets`, `_dups`, `_gaps`, `_rejects`, `_aborts`, `_last_sum`, `_elapsed_ticks`, `_freq`,
  `_selftest_bad_pa`).

The phase (`src/nat079_impl.h`): refuse unless the engine is up and has the endpoint; check the arguments (page alignment of address and size,
at least 8 pages, no wrap, inside the window, the engine's own memory not inside the range); refuse if the engine has already seen host traffic;
a CPU self-test (write, read back, zero a few words of 8 pages of the reserve, twice, with a per-boot salt) whose failure leaves `RX_BEGIN`
refused; only then install `rx_dest`/`rx_size` and loop `nat044_tick(); nat047_poll();` (the watchdog pet and the hard-cap reset ride on every
round) until all bytes are committed, the cap passes or the engine goes down. A progress line `NAT079 rx MiB=<n> trbs=<n> err=<n> t=<n>s` is logged
every `report_s`. **`NAT079_DONE` means "committed", not "verified"**: it needs `rx_bytes == rx_committed == bytes` and the engine's per-chunk
checksum, which the sender checks; it says nothing about the bytes at the destination. Reading them back is PID 1's job (NAT-077).

## Direct versus staged

The default is **direct**: the DWC3 writes bulk-OUT data straight into the md1 reserve (`rx_direct = 1`, chunks up to 8 MiB). NAT-076 and
NAT-077's draft assumed the staged mode (the controller writes the engine's 64 KiB DMA block, the CPU copies each chunk into the destination).
I judged that unworkable at this point of the boot and chose direct. That is a **judgement from reading the code, not a
measurement**: the loader runs with the MMU off and copies with a byte-granular `mcopy` loop, so staging 2.3 GiB would take a time that was not
measured and that has to fit the same 240 s cap; direct mode has no copy.

What direct mode puts at risk, and how the run tells:

* NAT-040 item **U5**: whether the controller's DMA reaches addresses above 4 GiB. The first accepted chunk decides it (the engine's
  `rx_errors`/`rx_rejects`/`GET_RX` state; the companion's first checksum). If it does not reach, the fallback is `--rx-direct 0` (a rebuild, a
  new image hash, a new decision file). The staged contract is run on the model in `test_e2e79.py`; it has never run on hardware, and its copy
  is the byte loop whose duration I judged too long.
* Cache coherency of the reserve: the loader's final clean covers the window, but a stale dirty line over the reserve would be written back
  over delivered bytes and make the kernel read old data. Not established either way; the read-back digest (NAT-077) is the end-to-end check and
  row 2 of the pass table is the reading for it. If row 2 appears with a correct engine checksum, the follow-up is a clean+invalidate pass over the
  reserve **before** the receive phase.

## Time rules (checked by `build.py`, restated in the decision template)

```
pet + 20 <= 83                      NAT-074: the hardware watchdog is about 83 s unpetted
8 <= return_after <= 63             the kernel runs unpetted for loader_return_after seconds (83 s - 20 s margin)
deadline >= rx_cap + return_after + 60       the 60 s are the loader's own work before and after the phase (about 13 s measured in NAT-075) and the log dump
deadline <= 600     0 < rx_cap <= 580
```

Built values: receive cap 240 s, `loader_return_after` 45 s, deadline 360 s, pet 30 s, progress every 10 s. At 240 s the stream needs 10.3 MB/s;
no host-to-phone rate has been measured. The kernel's own run is limited by the unpetted watchdog (NAT-071 is the task for a kernel keepalive):
hashing 2.31 GiB inside `loader_return_after` = 45 s minus boot time needs more than 55 MB/s, so a cut hash (row 3a/4 of the pass table) is a
likely first outcome and tells the rate rather than failing the delivery.

## `--ramdisk`

`build.py --ramdisk MACHO` replaces NAT-065's probe-init (md0) with the given arm64 Mach-O (at most 1 MiB, checked for the 64-bit Mach-O magic;
its SHA-256 is in `build.json` as `nat079_ramdisk`). The image used here carries NAT-077's hash probe (16,635 B,
`dc5c7845b3856274b0c8b5519f5b2a726c595de5410cb6cfa818fe0645a258b7`). The kernel command line is NAT-067's with `loader_return_after=45` and
`nat_attempt=NAT078-rx1` (`nat079_cmdline_append`).

## The image (build-003, package-002; local, not committed)

| item | SHA-256 | size |
|---|---|---|
| RECOVERY image | `d95024989a2cc8cd96c39a10bf9c4c33552047c36dc0c2618b88dcfef10c02ef` | 100,663,296 |
| `Image.payload` | `95aec19a75594a89378f79fe372bf67db1301667073ceef3036a61ad59520512` | 21,956,576 (offset 2048) |
| loader image | `713b0330c487b6e0ad88e4996dabf206d135bd6fce8fd1c5ee446e87d5109442` | |
| pinned stock RECOVERY (restore source) | `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` | |
| `build.py` / `make_variant79.py` / `nat079_impl.h` / `nat079_fixed.h` | `050893ee…` / `9dcc92a5…` / `5b018d10…` / `6d8e218d…` (full values in `evidence.json`) | |

If any of those four sources changes, the image has to be rebuilt, repackaged, the hashes in the decision template updated and
`docs/procedures/nat-080/derive.py` re-run. The build record's key `nat041_engine` is NAT-074's label and is **not** the engine used; the
engine files are in `nat079_engine`.

## What the tests show

* The helpers (`nat079_check_args`, probe addresses, pattern words, `nat079_decide`, the progress-line formatter) agree with hand-computed
  values at the edges, as host code and as the compiled aarch64 code run alone under Unicorn.
* The phase inside the real loader build, with the NAT-076 model behind the engine: it ends on `rx_bytes == rx_size` with DONE, on the cap with
  TIMEOUT, on a failed self-test (and then refuses `RX_BEGIN`), on engine-down, on premature host traffic; the pet schedule and the final pet are
  those of NAT-074; `rx_dest` is the md1 reserve computed from the layout, 16 KiB aligned, inside the window and not inside the clear plan.
* NAT-074's binary rules hold in the built loader: one `s5e_wdt_pet` call from `nat074_pet`, none in `recovery_guard`.
* Writes of the phase are confined to the reserve (self-test pages) and the engine's own memory.
* `build.py` refuses each rule above when broken, a root size that is not a multiple of 16 KiB, and a ramdisk that is empty, over 1 MiB or not
  a 64-bit Mach-O (the limits are tested exactly: 1,048,576 accepted, 1,048,577 refused).

## Mutation pass

`mutate_nat079.py`, final pass `artifacts/nat-079/mutation-run5-full` (copy: `mutation.json`): **580 candidates; 91 invalid** (51 do not parse in
Python, 40 fail the real loader build under `zig -Werror` or the fixture under `cc -Wall -Wextra`: not counted); **486 killed** (3 of them by
timeout: a loop that no longer advances); **3 survivors, all examined and recorded in `equivalent.json`** with reasons (`pa + bytes <= pa`
differs only for bytes in {0, 2^64}, excluded by the earlier check; `return NAT079_DONE` versus `return 0` is the same after preprocessing;
a 21-byte instead of 20-byte digit buffer holds the same digits).

Honest notes on how the pass got there:

* Earlier passes were polluted: the Claude Code `/tmp` tmpfs hit `Disk quota exceeded` and 180 of 214 `nat079_impl.h` mutants of pass 2 became
  "invalid" for that reason. Their C results are not used; pass 5 ran with `TMPDIR` on the NVMe volume and has no such entries.
* Pass 4 found four `build.py` survivors (the `RAMDISK_MAX` literal and the size checks); a test with the exact limits killed them.
* NAT-076's pass had found two engine defects (a double `ENDTRANSFER`; an idle `XferComplete` leaving the endpoint enabled); they are fixed in
  `docs/procedures/nat-076/engine/`, and this build uses the fixed engine.

## Not established

* Anything on the S24: that the DWC3 DMA reaches the reserve above 4 GiB (U5), the host-to-phone rate, that the cache state leaves the
  delivered bytes visible to the kernel, that `/dev/rmd1` returns them, that the kernel survives its unpetted run past 83 s (NAT-071), that
  PID 1 has console descriptors.
* That the staged mode (`--rx-direct 0`) works on the S24, or how long its CPU copy takes there: model only.
* Anything about Apple userland. The root image's contents are the donor recipe's (IOS-012/013); this task does not look inside.
