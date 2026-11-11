# NAT-062: the payload kernel's own log, delivered to the computer, and a free run after C checkpoint 21 (host-test image)

Evidence kind: **host-test**. Nothing in this directory has run on the S24. The image was built and exercised only in the C host build of the new dump code, the
unicorn-based simulators of NAT-036 (resume model) and NAT-047 (DWC3 device model + the unmodified NAT-041 collector, used through the NAT-059 run layer) and in static reads of the XNU
payload. A simulated host seeing a simulated device is not hardware evidence, and unicorn is not an Exynos model.

## Why

NAT-060 (decision 0025, native-device) delivered all 27 kernel stop notes to C checkpoint 21 and the loader held there by design. The payload has no checkpoint after `arm_init`, and a kernel
rebuild is blocked (KRN-001). NAT-061 (source review, `docs/procedures/nat-061/README.md`) asked what the kernel already offers a loader: its console text is collected in `loader_log` and handed
to the stub in `x0`/`x1` at every stop, and the kernel can return by itself (`loader_return()`, e.g. through the boot-arg `loader_return_after`). The owner's goal is that the computer
receives the messages of a real native run by itself; a kernel that prints text and is allowed to run on gives far more than one more checkpoint.

## What was built

`build.py` is NAT-059's build (NAT-036 + NAT-044 + NAT-047 + NAT-052 + NAT-059, each patch step and the link unchanged) with the image name `loader-diag-xnu-run-usb`, one more patch step,
`patch_run62.py`, and a command-line patch of the payload.

* **`src/glue62_impl.h` (`nat062_dump_log`)**, included by `markerlib52.c`: sends the kernel's log as TEXT records through the NAT-047 engine: `KL begin why= len= head= tail= gap= x0=`,
  `KL <6-hex offset> <escaped text>` (96 log bytes per record; printable ASCII as is, `\\`, `\n`, `\r`, `\xHH` otherwise), `KL end why= recs= bytes=`, or `KL refused why= x0= x1=`. The newest bytes go
  first, then the oldest, so a deadline reset cuts the least interesting part; head and tail are limited (final dump 8192 + 8192, return dump 8192 + 32768 bytes; the middle is a counted gap). Nothing is
  read unless `x0` is exactly the PA of the payload's `loader_log` (VA `0xfffffff007b90a00`, pinned against the NAT-035 symbol table) and `x1 <= 0x180000`. The engine has no acknowledgement
  from the host and its 32 KiB ring overwrites the oldest record when full, so after about 8 KiB of record bytes the stub polls the engine for 0.5 s (a burst times three stays below the ring).
* **`patch_run62.py`** (exact-anchor hunks, each exactly once or nothing) rewrites two places of the derived tree only: `ckpt3.c`, where after `nat052_note_stop` the last stop (`d.final`, TTBR0 to give back
  checked by `ttbr0_ok`) dumps the log with `why=1`, sets `RESUME_C` and `next = 0` (`slot[2] = 0`: `loader_checkpoint(n)` compares `slot[2]` with n and 0 is no checkpoint id, so the kernel never stops again) and a
  reason-0 arrival dumps with `why=2` and holds as before; and the include in `markerlib52.c`. The stub assembly, the stop list and the NAT-059 resume model are untouched.
* **The command line** (`build.py:patch_cmdline`): `nat_attempt=NAT020-83s` -> `nat_attempt=NAT062-run` and ` loader_return_after=8` appended in the NUL-padded 608-byte field at payload offset 0x48 (no checksum in
  the header; `payload_fixes` of `build.json` carries the new hash). The kernel parses it with `PE_parse_boot_argn("loader_return_after", ...)` (NAT-061).
* **`analyze_nat062.py`** reuses NAT-059's analyser through hooks (restored after each call) and adds the rules for what follows the stop notes, `kernel_log` in the result and `--log-out` (the reconstructed
  texts, one section per dump, nothing invented). **`session_nat062.py`** is the NAT-059 driver with 12 pinned substitutions (image, hashes, package, required-done list incl. NAT-060/NAT-062, decision glob,
  marker path); `test_nat062_run.py` compares the two files line by line so that nothing else differs.

## Pins

* RECOVERY SHA-256 `a618b98ccbbc655ca20db2dfac033274582ccdc89d8f8b6128a635b8d48392ff` (100663296 bytes, `artifacts/nat-062/package-001/loader-diag-xnu-run-usb/recovery.img`); `Image.payload`
  `c7863c99b2448dd1ea518a83dcfa90cb4e405b6445ddf3d4718e2c9be7e0aadd` (21861984 bytes at offset 2048); loader-only `Image` `1abdaf3a4716dc45f6828092c1e058a1a10f07bc4af6c473eff45cc7a28dd29a` (307200 bytes);
  command-line-patched XNU payload `a0562ac40a25449de0a3b81767dadb4f0a2f1a65ef3e693f67509a323b5023ea`.
* Sources: `patch_run62.py` `b51f9d2f3306cbb5b686fcb0b8552218cee3c84f11efd74ff301c52e8955337a`, `build.py` `2acef6448d9207c4143e0fa73bc1d420fbb5a28fb89a07e01499bad97bf36b24`, `glue62.h`
  `6d903add9b84dbdee16035ea296acd9f13aa94929814eaf85eb6a7dff2867473`, `glue62_impl.h` `6bc5898470d0c2933f4de95fa093932a6b25cf2160b3850cd94ac1e8d00aa688`.
* Reproducible: two builds (`artifacts/nat-062/build-001`, `build-002`) gave the same hashes.

## What the host tests establish (and what they do not)

* **Derivation** (`test_nat062.py`): the hunks apply once each and only add lines; the built tree differs from NAT-059's in exactly `ckpt3.c`, `markerlib52.c` and the two new files; the stub, stop list and
  resume rules are NAT-059's; the order in the handler (note, final dump + resume only when the TTBR0 was checked, return dump, hold) is pinned (a source-level guard: `nat036_ckpt_c` is aarch64-only).
* **Cmdline**: only the command-line field changes, to exactly the expected string; the boot-arg is the one the kernel parses; a field that is not the expected one is refused; the built payload carries it.
* **Host** (C harness of the real `glue62_impl.h`, with the NAT-047 formatters taken from `markerlib47.c`): every byte value round-trips through the escaping into the Python parser; head/gap/tail, the
  boundaries (len = head + tail, one more), empty log, the largest legal log and one byte more (refused before any read), only `loader_log`'s PA is read, nothing is sent while the engine is down, record
  size within the buffer and the engine's 1 KiB, pacing (the maximum burst times three below the ring, a wait after the last record, the wait length bounds), begin/end records agree with the parser.
* **Parser/Payload/Build**: damage in transit is named (missing record, cut dump, bad escape, wrong offset, wrong end counts); the log address and the array size are the payload's and the kernel
  source's; the package pins the RECOVERY and payload hashes of this directory's sources.
* **Run** (`test_nat062_run.py`): the driver (derivation pins, registry gates incl. NAT-060/NAT-062, decision-file gate, one-shot marker, RECOVERY-only write with readback, reboot once) and the analyser
  on archives written by the real NAT-041 collector from the DWC3 model: PASS only for a complete chain (27 notes, one complete final dump, one reason-0 note, one complete return dump, HOLD); `NO RETURN`
  is PARTIAL and still carries the first dump; a refused, cut or damaged dump, a dump before its stop note, a return before the first stop, an exception, a synthetic archive and an old-image boot each get
  their own verdict or reason.
* **Mutation check** (`mutants.py`, 69 mutants of the patch, the build, the dump code, the analyser and the driver): results and the explanation of each survivor in `evidence.json`.
* **Not established on hardware**: everything about the kernel after checkpoint 21 (below).

## Limits, disclosed

* The kernel after `arm_init` has never run on this phone and is **not modelled**: `machine_startup`, `kernel_bootstrap`, the startup tasks, timers, the GIC and the scheduler, `loader_return_timer_init`'s
  `thread_call`, `loader_return()` and the `redwood_*` quiesce calls. Its reach to MMIO is not bounded by review (indirect calls, thousands of functions).
* Whether `kprintf` output reaches `loader_log` on this SoC, whether timer interrupts work, and what the kernel does in 8 s are exactly what the run measures. A hang ends with the 83 s hardware watchdog,
  whose behaviour on this phone has not been observed (NAT-021 never ran); `SEC_UPLOAD` and an automatic restart were seen once (2026-11-11, a debugfs read, NAT-051).
* The deadline budget: final dump about 1.5 s, kernel 8 s, return dump about 4 s: the return dump should end about T0 + 70 s, before the loader's reset at about T0 + 81 s; a slower kernel is cut by the reset
  (a cut dump is PARTIAL and named).
* The collector's `dead_after` (30 s of consecutive failures) survives the silent run of the kernel (≤ 8 s plus the dump pauses).

## Commands

* Build: `python3 -I docs/procedures/nat-062/build.py --out artifacts/nat-062/build-NNN --loader-source <copy of artifacts/nat-052/build-003 source>`; package:
  `python3 -I docs/procedures/nat-047/package.py --build artifacts/nat-062/build-NNN --out artifacts/nat-062/package-NNN`.
* Tests: `<venv with capstone+pyusb>/bin/python -W ignore -I docs/procedures/nat-062/test_nat062.py` (31+ tests, 3 s) and `... test_nat062_run.py` (24 tests, about 2.5 min), with `TMPDIR=$PWD/artifacts/nat-062/tmp`
  (the user `/tmp` tmpfs is nearly full on this host); `NAT062_BEHAVIOUR_ONLY=1` skips the source-text pins.
* Mutants: `... docs/procedures/nat-062/mutants.py --json OUT [--only M5,M7] [--check-anchors]`.
* Run on the phone (not done): `docs/procedures/nat-062/session_nat062.py --image loader-diag-xnu-run-usb --out artifacts/nat-063/run-001 --execute`, gated by decision 0026
  (`decision-draft.md`), a native permit citing it and the one-shot marker; analysis: `analyze_nat062.py --archive ... --events ... --report ... --out ... --log-out ...`
  (run after the collector and the watcher have exited).

## Next

NAT-063: one native run under decision 0019 (owner confirmation recorded before the launch), restore of the stock RECOVERY and the Android check, then analysis; the kernel's text goes into the
next task's input (what XNU printed and where it stopped decides the next obstacle: checkpoints in `kernel_bootstrap`, the console path, or the GPU/display work).
