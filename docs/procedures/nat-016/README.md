# NAT-016: host archive that retains separate boot logs

Host implementation only. No phone commands, flash, reboot, raw-memory access,
UART configuration or native producer is implemented or executed here. NAT-015
explains why the attempted image's RAM records are not persistent. NAT-017 must
qualify a real channel before another native experiment.

`archive.py` accepts a local file, an existing FIFO or standard input. It creates
one new output directory, refusing an existing path. It never truncates, resumes,
rotates away or deletes an old archive. File/device paths and symlinks are refused
as input unless they are ordinary files or existing FIFOs; stdin is supplied by
the operator's already established receiver. It does not open a UART/USB device.

Example after an actual receiver has separately been qualified:

```sh
python3 -I docs/procedures/nat-016/archive.py \
  --out artifacts/nat-016/NEW-UNIQUE-ATTEMPT \
  --channel early-uart --provenance unqualified-live \
  --seconds 120 --max-bytes 33554432 < ALREADY-RECEIVED-FRAMES.jsonl
```

This command archives a local input; it does not initiate a phone boot. No example
uses a phone reset/flash command or selects a physical-memory address.

## Frame and storage contract

A producer/receiver adapter emits newline-delimited JSON. Binary payload is base64:

```json
{"boot_id":"attempt-unique-boot-001","seq":0,"kind":"boot","data_b64":""}
{"boot_id":"attempt-unique-boot-001","seq":1,"kind":"stage","data_b64":"ZW50cnk="}
{"boot_id":"attempt-unique-boot-001","seq":2,"kind":"end","data_b64":""}
```

Kinds: `boot`, `log`, `stage`, `fault`, `drop`, `end`. Maximum 4096 boots per archive;
further markers remain in raw input and are reported as errors. Each new boot starts with
seq0 and an unused ID; subsequent seq values increase by one. Use a new archive
per collector start. A reset must produce a **new** boot ID: that requires a
qualified host nonce handshake or a validated retained counter. A counter in
ordinary reset-cleared RAM is insufficient. USB disconnects alone are not boot
markers. The collector records receipt of a claimed marker, not proof of XNU.

Every received chunk is saved to `received.bin` and fsynced **before parsing**.
`chunks.jsonl` stores its offset, length, SHA-256, host UTC and monotonic timestamp.
All input, including invalid frames and binary bytes, remains in this raw file.
Parsed frames and decoded payload go to `boots/ORDINAL-BOOT_ID/frames.jsonl` and
`payload.bin`, with exclusive creation and append-only writes. A new boot marker
starts another directory; prior boot payload is not overwritten. Even a reused
producer ID gets a new host ordinal and separate files, while the reuse is
reported as an error; it cannot be treated as a qualified new hardware boot. Payload bytes
are fsynced before their frame record. `events.jsonl` records boundaries and errors.

`manifest.json` is created once at collection end and hashes all archive files.
Missing manifest means interrupted/unsealed capture. On SIGKILL or host failure,
already fsynced input remains; this is not a guarantee for bytes that had not yet
reached durable host storage. A new collector invocation must use another path.
Previous archives do not depend on counters in the phone or process.

Gaps, duplicate/reversed sequences, reused boot IDs, explicit producer drops,
invalid/oversize/truncated frames, missing end markers, I/O errors, interruption,
timeout and size limit are recorded. Raw collection continues after malformed
frames until EOF or the selected bound. There is no cyclic host buffer.

A `complete-received-stream` result (exit0) means a well-formed bounded input with
all observed boots ended; it **never** means a successful hardware or iOS boot.
Anything else returns exit2 and `incomplete`, or leaves an unsealed archive if
storage/process failure prevents finalization. A crashed boot normally lacks an
end marker: its bytes remain useful despite the incomplete result. Unexpected
unframed UART text is retained in `received.bin` even though framing fails.
At a size limit only the explicitly bounded prefix is retained and reported.

## Actual verification

`python3 -I docs/procedures/nat-016/test_archive.py -v`: 9 tests using actual
subprocess pipes and synthetic frames. Controls cover two boots and collector
restart, output reuse, duplicate IDs, gaps/drop/reversal, malformed/oversize and
truncated data, fragmented input, idle deadline, byte limit, device/symlink refusal
and SIGKILL after the chunk has been fsynced. Another control archives 80 boots
with a 32-file-descriptor limit to detect leaked handles across boot boundaries.
No phone was accessed by these tests.
Logs: `artifacts/nat-016/tests-004/{command.json,output.log}`.
The two-boot `demo-002` archive is explicitly synthetic and inspectable.

## What still needs qualification

No full early-log channel exists on the phone yet. The next canary must establish
safe board-specific transport and earliest reachable instrumentation, export each
boot to this host archive, then retain both records through reset and collector
restart. Required stage coverage includes entry/EL, stack/vectors, watchdog,
MMU/cache checks, DTB, memory window, segment copy, ADT/boot_args, pre-branch and
actual kernel entry; fault records include ESR/ELR/FAR where those reads are valid.
The current kernel's early image marker is not exported to this recorder.
The current `JUMP TO XNU` text is emitted before the hold and branch, so it is not
accepted as a kernel-entry marker. No new experimental image was built or flashed.
