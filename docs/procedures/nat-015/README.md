# NAT-015: early logging and reset retention audit

2026-11-10. Source review only; no device operation or new XNU execution.
The inspected attempted RECOVERY is SHA-256
`db19e3b775119c10431f38224c7b8eb3ecf19afd0ba96aff052f321c38d556eb`.
`audit.py` checks its identity, the embedded-kernel input identity and actual linked
loader/kernel symbols. Run output: `artifacts/nat-015/audit-001/inspection/report.json`.

## Findings in the exact attempted loader

Source root: `artifacts/nat-009/check-002/source/shim/e1s-xnu`.

| Location | What the code establishes | What it does not establish |
|---|---|---|
| `loader.c:58-90`, linked ELF `loader_log` offset `0x21a20`, size 65300 | Image-owned `.data.bootlog` record. `log_init` resets length/reserved/text[0]; each new image load supplies initialized data again. Maximum text 65280 bytes (`0xff00`); further characters are silently dropped. | Persistent storage, per-boot archive or actual execution of the logger. This is a saturating buffer, not a rotating file. |
| `start.S:el1_entry`, then `recovery_guard`, then `loader_main`; `loader.c:415-421` | Incoming EL and SCTLR checks, stack/vectors, BSS and guard precede log initialization. Even DTB validation returns before log initialization on failure. | A missing banner does not locate the fault. Some assembly halt paths precede arming the project's watchdog. |
| `loader.c:734-748` | Exception path records slot, ESR, ELR and FAR in the same RAM record, then waits. | Cache persistence through reset, a host receiver, or recovery of that record by Android. |
| `loader.c:712-725` | `JUMP TO XNU` is logged **before** window cache cleaning, the requested hold and actual branch. Payload command line includes `e1s.hold=10`; code holds before returning the entry address. | That string would not prove kernel entry. A configured 30s watchdog includes loader work and the hold if those stages execute; it is not a measured 30s XNU run. |
| `loader.c:8` | `0x91200000` is explicitly described as a legacy exclusion, not this log destination. | Reading the old fixed-address recipe would locate the current loader log. No arbitrary physical-memory read was attempted. |

Thus repeated loads/initializations would replace/reset the RAM log. Whether an
old log ever existed during the observed loop is unknown. No surviving log can be
reconstructed from the initial bytes in the disk image.

## Kernel and extraction

The exact kernel input hash is `4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f`.
Its symbols include `_e1s_log_storage` at `0xfffffff007e87a70`, `_e1s_log_init`
and `_e1s_log_append`. STR-034/035 changed the former fixed physical storage into
an image-owned 1MiB BSS ring and a private image-data marker. The existing append
logic wraps and replaces older bytes within a boot; total/seq reset during init.
Pre-init append calls return without recording. The marker is a single last-stage
slot, not a sequence archive. These are source/link facts, not captured execution.
See `docs/procedures/e1s-kernel-log/README.md`, its overlay and STR-035 object evidence.
The old fixed-address diagnostic table in NAT-002 must not be used as an actual
address contract for this image.

The pinned upstream `tools/e1s/read_log.py` is an **offline extractor**, not a
transport. It requires a dump already obtained. Its `--output` uses `open(...,'wb')`,
which truncates a reused output pathname. It selects one preferred decoded log.
No evidence shows this extractor was run against the failed attempt's live RAM;
therefore host-file overwrite is a risk in that command, not an established cause
of the missing incident logs. Keep all raw inputs before any decoding.
Primary source: [pinned extractor](https://github.com/RNDMBG/iOS-On-S24/blob/c8860decc62c6d6180e609036d027a2997972420/tools/e1s/read_log.py).

`pstore` does not discover arbitrary loader/XNU data. Ramoops requires a correctly
reserved RAM area that survives restart and compatible records; its documented
counter also resets on reboot and later dumps can replace old dumps.
[Linux ramoops documentation](https://docs.kernel.org/admin-guide/ramoops.html).
No such shared persistence/reader contract is qualified here. Do not change the
Android DT, use guessed RAM/MMIO, or write a log partition to manufacture one.

## Capture design and prerequisite gate

NAT-016 implements host archival: a new exclusive run directory, exact raw input,
receive timestamps, per-boot files keyed by explicit boot markers, sequence-gap
reporting, SHA-256 manifests, and no truncation/reuse/automatic deletion. USB
observations alone never create a claimed kernel boot or qualify a log transport.

A host recorder cannot receive bytes from a silent RAM-only producer. Before any
future native test, select and qualify an actual physical channel. An independent
UART could survive USB resets, but this board's pinout, electrical levels, pinmux
and native early transmitter are not established. No UART/MMIO probing is allowed
by this host task. The present USB path has no qualified XNU gadget/receiver;
framebuffer output needs camera capture and does not supply a complete serial log.

A future separately authorized canary must prove: unique attempt and boot IDs;
receipt of entry/EL/stack/vectors/guard/DTB/window/copy/ADT/pre-branch and actual
kernel-entry markers through that channel; bounded nonblocking output; explicit
buffer overflow/drop counters; receipt before a controlled fault; and retention
of **both** boots after a reset and host collector restart. Log arguments should
include ESR/ELR/FAR and stage, with no personal content. A pre-branch marker cannot
substitute for a kernel-entry marker. Do not extend timeout as a substitute for
progress evidence. Do not run XNU before the canary/return gates and a new owner
image-specific decision. NAT-017 tracks that unresolved native qualification.

No finite buffer or failed transport can promise every message. The enforceable
contract is preservation of every received byte, separate boot records, and explicit
indication of missing markers, gaps, invalid data, overflow, timeout or interruption.
