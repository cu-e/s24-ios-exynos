# NAT-076 — bulk-OUT receive path for root delivery: engine variant, model, sender

Evidence kind: **host-test**. Nothing here ran on the phone and nothing in this directory touches it. The engine is authored
code that compiles for `aarch64-freestanding`; the tests run it against a model that is *my reading* of the vendor `dwc3`
driver; the sender is tested against the same model. Passing shows that the engine, the wire protocol and the sender agree
with each other and with that reading. It does not show how the S24's DWC3 behaves, how fast the host can push bytes, or that
the controller can write into the region where the root image will live (see "Not established").

Why this exists: NAT-075 put the 2.31 GiB root reservation (`md1`, 0x93908000 bytes) into the kernel's view on the phone, but
no byte of it has ever been written. The only channel that survives into the loader window is USB, and NAT-041's engine is
EP0-only. This task adds the missing direction (host → phone, bulk OUT) as a **variant** of that engine under its own path;
`docs/procedures/nat-041` is not edited. NAT-077 (probe PID 1 that hashes the region) and NAT-078 (the native run) consume it.

## Files

| path | role |
|---|---|
| `engine/usbmon.h`, `engine/usbmon.c` | the NAT-041 engine plus one bulk-OUT endpoint: wire protocol (`RX_BEGIN`, `GET_RX`, `RX_ABORT`), TRB ring, completion handling, checksum. The rx code is the section "bulk-OUT receive (NAT-076)" |
| `engine/dwc3_regs.h`, `engine/usbmon_port.h`, `engine/port_aarch64.h` | NAT-041's register constants (plus `UPDATETRANSFER`, endpoint-enable and the other bulk-endpoint values) and hardware contract, copied with attribution (GPL-2.0) |
| `model/model.c`, `model/host_port.h` | the device-side model extended with one bulk-OUT endpoint, a TRB-ring walker, a destination window that is pre-filled with `0xEE`, a non-coherent cache model for it, injectable faults, and read-only views of the controller's own endpoint state and of the ring slots (`t_ep_started`, `t_rxtrb`), so tests can compare what the engine believes with what the controller holds |
| `modelhost.py` | ctypes front end (`Machine`: `bulk_out`, `bulk_fault`, `set_dma_limit`, `dest*`, `stage_cpu_dirty`, `trb_slot`, `engine_ep_started`/`hw_ep_started`, `end_hw_transfer`, `cmd_trace`, `write_trace`); the model is built with `-ftrivial-auto-var-init=pattern` so an uninitialised local in the engine gives a poisoned value, not a lucky zero |
| `cdefs.py` | `#define` parser/evaluator copied from NAT-041's `test_engine.py` (used by the vendor cross-check) |
| `test_rx.py` | 227 tests of the engine against the model: protocol, endpoint lifecycle and the exact commands/register writes, compatibility with NAT-041, static checks, vendor cross-check, seeded defects |
| `mutate_rx.py` | mutation pass over the receive state machine of `usbmon.c` and over `tools/ios/root_send.py` |
| `equivalent.json` | the survivors that were examined and judged equivalent, with reasons |
| `mutation.json` | the mutation result (copied from `artifacts/nat-076/`) |
| `../../../tools/ios/root_send.py` | the host sender (pyusb) |
| `../../../tests/test_root_send.py` | 93 tests of the sender against the model; runs in `make check` |

Run (host only; `cc` and `zig` needed, `references/s24-linux` at the pin for the cross-check):

```sh
python3 -I docs/procedures/nat-076/test_rx.py
python3 -m unittest discover -s tests -p test_root_send.py
python3 -I docs/procedures/nat-076/mutate_rx.py --out artifacts/nat-076/mutation --jobs 10
```

## Wire protocol (`engine/usbmon.h`)

The NAT-041 requests are unchanged (`GET_INFO` 0x01, `READ_RING` 0x02, `GET_EXC` 0x03, `SET_NONCE` 0x04, `PEEK` 0x05 = stall).
New, all vendor/device:

| request | direction | data | meaning |
|---|---|---|---|
| `RX_BEGIN` 0x06 | OUT | 16 bytes `{u64 offset, u32 length, u32 flags = 0}` | arm **one** bulk-OUT transfer of `length` bytes that continues the stream at `offset` |
| `GET_RX` 0x07 | IN | up to 120 bytes `struct usbmon_rx` (magic `S24R`, version 1) | state IDLE/ARMED/FAILED, committed offset, counters, last chunk's offset/length/sum |
| `RX_ABORT` 0x08 | OUT | none | end an armed transfer; nothing is committed |

Bulk OUT is USB endpoint 0x01 (physical endpoint 2), high speed, wMaxPacketSize 512.

The stream is **strictly sequential**: `RX_BEGIN` is refused (EP0 stall and a counter) unless `offset == committed`; a smaller
offset counts in `rx_dups`, a larger one in `rx_gaps`; length 0, not a multiple of 512, above the chunk limit or past the
destination size, `flags != 0`, a second `RX_BEGIN` while one is armed, and any request while an `ENDTRANSFER` or a ring
restart is pending go to `rx_rejects`/stall. A chunk is committed only if the TRB completed with status OK, residual 0 and
no short-packet or bus-error bit in the event; anything else sets FAILED, increments `rx_errors`, leaves `committed` where it
was, and restarts the endpoint (`ENDTRANSFER`, then the ring is re-initialised). A bus reset, a disconnect or
`SET_CONFIGURATION(0)` disable the endpoint (an armed transfer becomes FAILED and counts in `rx_resets`);
`SET_CONFIGURATION(1)` enables it again. `committed` survives all of that. The device cannot rewind: a chunk that was
committed with a wrong checksum is final, so the sender treats it as fatal.

Integrity: after every chunk the engine publishes `last_off`, `last_len` and `last_sum`, where
`sum = Σ word_i · (2·i + 1) mod 2^64` over the chunk's 64-bit little-endian words (`usbmon_rx_sum_step`). The weight makes the
sum order-sensitive, so swapped or shifted words are noticed, unlike a plain additive sum. It is a transport check, not a
hash: NAT-077 hashes the whole region from the kernel side with SHA-256.

Two delivery modes are built from the same source (`USBMON_RXF_DIRECT`):

* **staged** (default): the controller writes up to `USBMON_RX_STAGE_BYTES` (64 KiB) into the engine's own DMA block, which
  is a loader page below 4 GiB, the only kind of DMA target that has been observed working (the native runs from NAT-043 on), and the CPU copies it to the destination
  in 4 KiB pieces after the completion. The chunk limit is 64 KiB.
* **direct**: the controller writes into the destination itself, one TRB of up to 8 MiB. This needs the S2MPU/PMMU in front
  of the DWC3 to pass those addresses (NAT-040 item U5, unresolved), so it is off until measured. The model can lose DMA
  writes from a chosen destination offset (`set_dma_limit`) and the engine notices that through the checksum, because the
  checksum is read back from the destination, not computed from the stage.

## Design points that come from the vendor driver, and where this deviates from the registry text

The register sequence is the pinned vendor `dwc3` driver (`references/s24-linux` at `417484173abc2c4fa93e738ea82ad9f2e84911b1`,
`drivers/usb/dwc3/{core.c,core.h,ep0.c,gadget.c,gadget.h}`): `DEPSTARTCFG(2)` on EP0 at `SET_CONFIGURATION`, then `DEPCFG`
(INIT), `DEPXFERCFG(1)`, `DALEPENA`, a TRB ring ending in a link TRB with HWO set, a `STARTTRANSFER` on the empty first TRB, and
`UPDATETRANSFER` for every later TRB; completion arrives as `XferInProgress` (enabled in `DEPCFG` for non-control endpoints);
`ENDTRANSFER` carries the resource index and `CMDIOC`. Every constant is re-read from the pinned headers by
`test_dwc3_constants_match_the_pinned_vendor_headers` (and the check itself is tested with a wrong value). The engine's own
`DWC3_EVT_*` names, which the vendor does not define as constants, are the seven listed in the test, checked against the
event decode in `gadget.c`.

Deviations from the wording of the registry task (`state/lab.json` NAT-076), chosen on purpose:

1. **Receive counters live in `GET_RX`, not in `GET_INFO`.** `GET_INFO` is a fixed 112-byte structure that NAT-041's
   collector parses by length and version; extending it would break that collector. `GET_INFO` is unchanged.
2. **One TRB per chunk instead of chained TRBs of up to 16 MiB.** A chunk is one `RX_BEGIN`, one TRB, one completion, one
   checksum, one commit. Chaining adds a partial-failure state (some TRBs of a chunk done, one failed) that the resume rule
   would have to describe. The staged chunk is 64 KiB, the direct chunk at most 8 MiB; the sender picks the smaller of
   its `--chunk` and the device's `chunk_max`.
3. **The ring has 4 slots (3 data + link), not the vendor's 256.** Only one chunk is ever armed, so the ring never holds more
   than one live TRB; four slots are enough to exercise the wrap onto the link TRB, which the seeded defects target.
4. **Staged copy is the default** because of U5 (above). Choosing direct mode later is one flag, not a redesign.

## The sender (`tools/ios/root_send.py`)

`send(transport, data, base=0, chunk, write_size, max_retries, …)`:

* refuses before any I/O a file whose size, base offset, chunk size or write size are not multiples of what the device
  requires (file size and base: 16 KiB, the XNU page size NAT-075 measured; chunk and write size: 512);
* reads `GET_RX`, requires PRESENT and ENABLED, requires the file to fit in the device's capacity, aborts a leftover armed
  transfer, **resumes from the device's committed offset** (which must lie within `[base, end]`), and clamps `chunk` to the
  device's `chunk_max`;
* per chunk: `RX_BEGIN`, bulk writes of at most `write_size` bytes (a short write is a transport failure), then polls `GET_RX`
  until the state leaves ARMED and checks `committed == off + n` and `last_off/last_len/last_sum` against the host's own sum
  of that chunk; a mismatch is a `DeliveryError` that is **not** retried (the device cannot rewind);
* on a transport failure: waits `backoff · attempt`, reads the device state again (reconnecting if the ENABLED flag is clear,
  because a bus reset leaves control requests served but the endpoint disabled), aborts a still-armed transfer, accepts a chunk
  that had in fact arrived, otherwise requires `committed == off` (anything else is a `DeviceStateError`), and retries up to
  `max_retries`; a device whose committed offset went below the floor it had reached is reported as restarted;
* ends with a final `GET_RX` that must report `committed == end`, and prints the numbers **the device reports**
  (`committed`, `rx_bytes`, `rx_trbs`, `rx_errors`) next to the host's own counts. Exit status 0 only on that line.

## Tests

* `test_rx.py` (227 tests): `ProtocolTests` run in the staged and the direct variant (the base class itself also runs once with the staged defaults, so the staged scenarios count twice in the 227): enumeration, the four-slot ring wrap, sizes, a
  destination pre-filled with `0xEE` to expose wrong offsets, dirty cache lines in the destination, every refusal rule,
  capacity, short packet, bus error, TRB status error, residual-only, the three "all bytes arrive but only one failure
  indicator is reported" cases, bus reset and reconnect, abort, `SET_CONFIGURATION(0)`. `CompatibilityTests` check that the
  NAT-041 requests behave as before. `StaticTests`: vendor constants, no libc and no undefined symbols in an aarch64
  freestanding build with `-Werror`, DMA and destination accessed only through the port. `SeededDefectTests`: 38 mutations
  of the engine source, each applied to a copy, each required to be noticed by a scenario that is clean on the real engine
  (`ScenarioHealthTests`); they cover the missing `UPDATETRANSFER`/`CSP`/`IOC`, wrong TRB type, wrong packet size, missing
  endpoint-enable and `DEPSTARTCFG`, wrong resource index on `ENDTRANSFER`, ring wrap onto the link TRB, missing cache
  maintenance, the duplicate/gap/length/capacity/flags rules, each failure indicator ignored, a commit on failure, a staged
  copy at the wrong offset, a lost tail, the checksum position forgotten, a reset not failing the transfer, abort not ending
  it, `SET_CONFIGURATION(0)` keeping the endpoint.
  The endpoint-lifecycle tests (added after the first mutation runs showed which engine lines nothing observed) check what the
  controller is told, not only what the host sees: the exact command sequence at enable (`DEPSTARTCFG` start config 2,
  `DEPCFG` bulk/512/INIT, `DEPXFERCFG(1)`, `STARTTRANSFER` on the ring address), the resource index and the empty parameters
  of `UPDATETRANSFER` and `ENDTRANSFER`, `DALEPENA` before and after, the ring slots after a restart (cleared, link TRB intact),
  a controller that ended the transfer by itself (a fresh start, no `ENDTRANSFER`), a start or restart command that fails
  (the path stays disabled until the host configures again), events of a disabled endpoint, the exact `GET_RX` flag bits, dirty
  cache lines in the staging block, and that the engine's and the controller's record of "a transfer is active" agree at every
  step.
* **Also found by the mutation analysis:** an `XferComplete` event for the receive endpoint while nothing was armed left the
  endpoint enabled but with no transfer started, so the next `RX_BEGIN` would have sent `UPDATETRANSFER` to an endpoint the
  controller had already ended (the vendor kicks with `STARTTRANSFER` when `DWC3_EP_TRANSFER_STARTED` is clear). The engine now
  begins a fresh empty transfer in that case (`test_a_transfer_the_controller_ended_by_itself_while_nothing_was_armed_is_replaced_by_a_fresh_one`
  and the failing-start variant). Such an event is not expected from the real controller; the fix removes a latent hazard,
  not an observed one.
* **Found by the mutation analysis:** a bus reset that arrives while an `ENDTRANSFER` is already pending made `rx_end`
  issue a second `ENDTRANSFER`; the model flags that as `ENDTRANSFER on ep 2 with no transfer started`. The vendor
  `dwc3_stop_active_transfer` does nothing while `DWC3_EP_END_TRANSFER_PENDING` is set. `rx_end` now returns when
  `rx_end_pending` is set; the regression test is
  `test_a_reset_while_an_end_is_pending_does_not_end_the_transfer_twice_and_nothing_restarts_afterwards`.
* `tests/test_root_send.py` (93 tests): the sender drives the real engine through `ModelTransport`, with hooks for
  injected failures. Staged and direct delivery; BUSERR, TRB error and short-packet failures; host disconnect mid-transfer
  followed by reconnect and resume; a lost status read; bounded retries and the back-off schedule (0.5, 1.0, 1.5 s); a
  restarted device; a device that lies about the final count; DMA loss in direct mode; the size rules; the CLI output;
  checksum vectors (including wrap-around, with and without numpy); the structure parser; the pyusb transport against a fake
  `usb.core` (wire bytes, reconnect). The expected values in these tests are derived from the protocol (offsets, byte counts,
  device-side counters), not from the sender's own arithmetic.

## Mutation pass

`mutate_rx.py` breaks one place at a time and requires the host tests to fail.

* **Engine** (`engine/usbmon.c`): every line of the section "bulk-OUT receive (NAT-076)" plus every other line that mentions
  `rx_`, `USBMON_RX`, `out_kind` or the three new requests. Operators: comparison and boolean operator swaps, `+`/`-`, `|`/`&`,
  `%`/`*`, every integer literal changed (±1, 0↔1, shift amounts), `if` conditions forced true / false / negated, statements
  deleted, return values dropped. Comments are not mutated. A mutant must build with exactly the flags of the real model build
  (`-Wall -Wextra -Werror`, `-ftrivial-auto-var-init=pattern`, …); one that does not is *invalid*, not killed. Each valid mutant
  runs `test_rx.py` (fail-fast) in a scratch copy of the tree; any failure, error or hang kills it.
* **Sender** (`tools/ios/root_send.py`): every code line outside docstrings, with the Python equivalents of those operators
  (also `not` removed, `True`↔`False`, `in`↔`not in`, `is`↔`is not`); string contents and log calls are not mutated. A mutant
  runs `tests/test_root_send.py`, then the static checks of `test_rx.py` against the mutated sender.

Final run (`artifacts/nat-076/mutation-run5/mutation.json`, copied to `mutation.json` with one temporary-directory path in a failure message replaced by `$TMPDIR`; run 5 of 5, see below):

| | candidates | invalid | valid | killed | survived | survivors without a reason |
|---|---|---|---|---|---|---|
| `usbmon.c` | 560 | 101 | 459 | 431 (3 of them by hanging until the 240 s limit) | 28 | 0 |
| `root_send.py` | 450 | 8 | 442 | 434 (5 of them by hanging until the limit) | 8 | 0 |
| total | 1010 | 109 | 901 | 865 | 36 | 0 |

A mutant killed by a timeout means the mutated code loops forever (an index that no longer advances); it is a visible failure but
by hang, not by an assertion. "Invalid" means the mutant did not build with the real flags (C: any compiler error or warning) or did not parse (Python); the
script does not record which, so no breakdown is given. Such mutants say nothing about the tests.

**All 36 survivors were examined and judged equivalent** (`equivalent.json` gives the reason for each; the script exits
non-zero while a survivor has none). In short: flag fields that are only tested for truth (`= 2` for `= 1`), `-2` for `-1`
where the caller only tests non-zero, byte shifts inside a word that is only tested for non-zero, a `<`/`<=` on a value the
previous conjunct has already fixed, the speed-only numpy branch of the checksum, state that is reset and then always
overwritten before use (`ep_rsc` of the receive endpoint), a redundant `rx_restart` test after an invariant (ENDTRANSFER is issued
only by `rx_disable`, which clears `rx_enabled`, and `rx_restart`, which sets the flag), and initialisations whose value is never
read. Not among the survivors, because the tool does not delete single terms of a condition: the `!rx_end_pending` and `!rx_restart`
terms of the stray-completion guard imply each other (`rx_restart` is set only together with a pending end, and an end is
issued only by `rx_disable` or `rx_restart`). A manual check showed that either of them can be removed on its own without a
test failing; they are kept as defence in depth. The guard forced true, forced false, and without its `ep_started` term is
killed by the new tests (checked by hand; its `rx_enabled` term was not removed on its own).

How the pass changed the code (runs 1 to 5 are in `artifacts/nat-076/`; runs 1 and 2 were made against earlier versions and are
superseded):

* Run 2 left 63 engine survivors. Most were real gaps: nothing observed which commands and register writes the engine
  gives the controller, what the ring slots contain after a restart, or whether the engine's and the controller's idea of
  "a transfer is active" agree. The model got read-only views of those (`t_ep_started`, `t_rxtrb`, `write_trace`, `cmd_trace`),
  and `test_rx.py` got the endpoint-lifecycle tests described above.
* Triaging the survivors found two **engine defects** (both fixed, with regression tests): a bus reset during a pending
  `ENDTRANSFER` issued a second `ENDTRANSFER` (the model: "ENDTRANSFER on ep 2 with no transfer started"), and an
  `XferComplete` while nothing was armed left the endpoint enabled with no transfer started.
* Run 4 left one survivor that was not equivalent (the guard of the fresh start above, forced true); two more tests (stray
  progress event; stray completion while an end is pending) killed it, checked by hand against five variants of that
  condition, and run 5 is the full pass over the final code and tests.

Limits of the pass: it measures whether *these* tests notice a changed line, not whether the model is right. A mutant of
the model itself is not part of it, so a wrong reading of the vendor driver in `model.c` and `engine/` would pass together;
that is what the vendor-constant cross-check and, later, the hardware run are for.

## Not established

* Nothing here ran on the S24. The model is my reading of the vendor driver; the controller may differ in details that only
  hardware shows (event ordering, short-packet behaviour at the end of a TRB, `UPDATETRANSFER` while a transfer is active).
* **U5**: whether the DWC3's DMA reaches the 2.31 GiB reservation, which lies above 4 GiB, behind the S2MPU/PMMU. Only DMA
  into a loader page below 4 GiB has been observed working. Hence staged by default; the copy by the CPU relies on the
  reservation being mapped for the loader at all, which NAT-078 must check by writing a pattern and reading it back before
  trusting any count.
* The host → phone rate. 2.31 GiB inside the 120 s window the run can hold needs at least 20.6 MB/s sustained, with the
  copy cost included. NAT-078 measures it; this task did not.
* That the watchdog keeps being fed while the loader serves bulk transfers for minutes (NAT-071 is the kernel-side
  keepalive; the loader-side pet worked for 150 s in NAT-075 without USB traffic).
* That pyusb `reset()` followed by `set_configuration(1)` reaches the real device after a disconnect; the tests use a fake.
* The loader does not contain this engine yet.

## Integration steps for NAT-078 (not done here)

1. Take the loader that NAT-075 derived and replace the NAT-041 engine sources with `engine/` of this directory; keep the
   NAT-075 patches (4 GiB window, md1 reserve) unchanged.
2. Point `rx_dest` at the physical start of the md1 reserve and set `rx_size` to its length (0x93908000), which is a multiple
   of 512 and of 16 KiB; keep `rx_direct = 0`.
3. Add a staged-write self-test in the loader before the first `RX_BEGIN` is accepted: write a known pattern to the first and
   last page of the reserve and read them back, and report the result in `GET_RX`/the log.
4. Run the sender with `set_configuration(1)` (the NAT-041 collector never does; the endpoint exists only after it).
5. The run needs its own decision file, committed before the run, as for NAT-075.
