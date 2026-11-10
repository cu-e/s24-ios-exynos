# NAT-013: stock restore tooling for one session per Download Mode entry, 2026-11-10

Evidence category: host-test, built on NAT-012 device records. NAT-013 wrote nothing to the phone,
and nothing here authorizes a write. Running `restore_stock.py restore` writes RECOVERY and needs its
own owner decision, as decision 0005 was for NAT-012.

Inputs (local, not committed): `artifacts/recovery-rescue-20261110-01/` (NAT-012 run directory) and
`artifacts/recovery-qualification/attempt-001/` (Antigravity odin4 logs).

## 1. S-Boot async worker lifetime (S921BXXS9BYH3)

**Source-review** (NAT-012 disassembly of the owner's `epbl.bin`, SHA-256 `4144ee0f…`, Capstone 5.0.9,
`session-lifecycle-analysis.json` and `session-lifecycle-disassembly.txt`):
- the async initializer 0x2839b0 has one direct caller, Download Mode initialization at 0x282af4;
- BeginSession (0x2db8c8) allocates and resets protocol buffers but does not call it;
- EndSession reaches 0x283980 → 0x2dd32c, sets the worker stop flag 0x931804, and a stopped worker
  with an empty queue ends in the permanent loop 0x2dd89c. The second write worker is stopped
  through 0x283600 → 0x2dcbdc.

So a later session in the same Download Mode entry can receive and acknowledge data with no live
worker to commit it. This is a reading of the binary, not a trace.

**Device records** (NAT-012, one row per Download Mode entry):

| USB entry | First session | Second session | Result |
|---|---|---|---|
| bus 5 dev 20 | `pit-read-001`: Heimdall `download-pit --no-reboot`, EndSession answered, exit 0 | `stock-flash-001`: Heimdall `flash --resume`, upload acknowledged, EndSession timed out (libusb -7), exit 1 | the boot loop remained after a forced restart (owner report); `android-check-001` saw no ADB |
| bus 5 dev 23 | `probe-run-001`: read-only session, EndSession answered, exit 0 | `stock-flash-002` (`restore-002/trace.json`): all 96 data parts and 4 sequence ends answered with 0, EndSession no reply for 120 s, exit 1 | no reboot sent |
| bus 5 dev 24 | `stock-flash-003` (`restore-003/trace.json`): PIT, 4 sequences, EndSession 0, reboot 0, exit 0 | none | Android booted; full RECOVERY readback = `96620b8b…` |

Both second sessions failed at EndSession after every acknowledgement came back zero. The only
first-session write succeeded. The 32 commands of `restore-002` equal the first 32 of `restore-003`
(the 33rd is the reboot, which `restore-002` never reached), so the session order is the only
difference found. That is three entries, consistent
with the disassembly; it is not an exhaustive test.

Supported-path rule: **one Odin session per physical Download Mode entry**. No standalone PIT read,
probe, Heimdall `--resume`, or second tool before the write in the same entry. A failed session
is never resumed; the next attempt needs a physical re-entry (a new USB enumeration) and a new
decision.

## 2. Modified odin4: PIT validation and command flags

`references/odin4-nat008` is pinned at `338fde4569ee3b0743098714199361835f96015b`. Its working tree
holds uncommitted Antigravity changes, saved as `artifacts/recovery-rescue-20261110-01/prior-odin.diff`.
`pit_audit.py` applies the original and modified PIT rules, plus odin4's archive-member match loop,
to the PIT read from the phone (`device.pit`, SHA-256 `a169ae2c…`, 49 entries).
Run: `artifacts/nat-013/pit-audit-001/report.json`.

Result on the real table:
- no entry has an empty or invalid name, identifier 0 or a duplicate identifier;
- the **original** rules accept the PIT, and `recovery.img` matches exactly one entry: index 24,
  RECOVERY, binary type 0, UFS (8), identifier 18, start block 75152, 24576 × 4096-byte blocks
  (96 MiB);
- the modified rules accept the same table with no warnings and select the same entry.

So none of the weakened PIT checks was needed for this phone. They only remove fail-closed
behaviour:

| Change | Effect | Verdict |
|---|---|---|
| Skip entries with empty or invalid names instead of rejecting the PIT | a corrupted or zero-filled read drops entries silently | not supported |
| Accept identifier 0 and duplicate identifiers | the on-wire identifier stops being unique | not supported |
| Accept PIT chunk replies of 1 byte or more (was 8), `rsp.empty()` check | a short reply leaves zeros in the PIT copy; together with skipping, entries can disappear | not supported; the real chunks are 500 bytes and a final 192 bytes |
| Remove the device-type query (0x64/1) before BeginSession | supported by NAT-012's disassembly: a 0x64 subcommand before BeginSession reaches "prb is null!" and the loop at 0x2da700. The 09:03:53Z odin4 run sent that query and then timed out | correct direction |
| BeginSession version 0x7fffffff → 5, ZLP off | not measured. The patched odin4 timed out at BeginSession (09:38:56Z, bus 5 dev 19); the cause is unknown. Heimdall and NAT-012 use 4 and get 0x38000 | unqualified |

Conclusion: the modified odin4 is **retired** for this phone. The local Odin-protocol tool below is
the supported path. Restoring the original odin4 checks in `references/` is outside this task's
paths. That working tree is left as found and documented here.

## 3. The supported tool: `restore_stock.py`

It derives from NAT-012's `restore_stock.py`, which produced `restore-003`. Its fixed inputs are
the same: image hash `96620b8b…`, PIT hash `a169ae2c…`, target (0, 8, 18), bounds 75152/24576 and
the 30 MiB / 1 MiB sequence and part sizes. It adds:
- **Enumeration ledger.** `artifacts/nat-013/sessions.jsonl` is keyed by host boot id, bus and
  device number. The key is written before any USB I/O, and a repeated key is refused.
- **Forward-only state machine.** Each command is accepted only in its protocol state. A second
  handshake or BeginSession is refused, and after EndSession only the normal reboot is accepted.
  A refused command is never written to USB.
- **No concurrent flasher.** The tool scans `/proc/*/fd` and refuses to start while another
  process holds the device node open.
- **Strict PIT checks.** The exact hash plus the original odin4 structural rules: names valid,
  identifiers non-zero and unique, exactly one RECOVERY with the measured target and bounds.
- **Separate report stages.** `report.json` records `pit_validated`, `upload_acknowledged`,
  `session_end_confirmed` and `reboot_confirmed` separately. Its outcome is one of
  `aborted-before-write`, `upload-incomplete`, `acknowledged-not-flushed`,
  `flushed-reboot-unconfirmed` or `awaiting-readback`. It is never `pass`.
- **Readback assessment.** `assess --report R --readback C` combines the restore report with
  `docs/procedures/nat-012/check_android.py` output. It returns `pass` only when Android booted
  and the full RECOVERY hash matches. Any stage before `awaiting-readback` returns `fail` even if
  the hash matches, because the bytes on the partition then came from somewhere else.

Host tests: `python3 -I docs/procedures/nat-013/test_restore.py -v` (16 tests). `FakeSBoot` models
the recorded device behaviour; it is not derived from the tool. The tests check that:
- the command sequence equals the real `restore-003` trace command for command;
- a second session in one entry reproduces `restore-002`: everything is acknowledged, EndSession
  times out, nothing is committed, no reboot is sent, and the report says
  `acknowledged-not-flushed`;
- a short PIT chunk stops the run before any write command;
- the strict PIT rules hold on synthetic tables and on the real table, and the real table passes
  both the original and the modified odin4 rules;
- the ledger and the device-node scan work;
- `assess` grades NAT-012's saved readbacks: `android-check-002` is inconclusive (boot animation
  still running), `android-check-003` passes.

## 4. Fresh single-session procedure (for a future decision; not run by NAT-013)

1. The owner enters Download Mode with the keys. Confirm `04e8:685d` with iProduct "SAMSUNG USB",
   not "SEC_UPLOAD".
2. Run nothing else against that enumeration: no odin4, no Heimdall, no probe.
3. `python3 -I docs/procedures/nat-013/restore_stock.py restore --bus B --address D --out RUN`
   (needs pyusb, as the NAT-012 venv).
4. If the outcome is anything but `awaiting-readback`, stop. Do not resume or retry. Record the
   report and hand over to the owner.
5. After Android starts: `python3 docs/procedures/nat-012/check_android.py RUN/readback.json`,
   then `restore_stock.py assess --report RUN/report.json --readback RUN/readback.json`.

## 5. Limits and open questions

- The worker explanation rests on one binary reading and three entries. A fourth entry with two
  sessions would test it further, but it would need a write and a decision, and it is not planned.
- Why the patched odin4 BeginSession timed out at 09:38:56Z is unknown.
- The first boot after `stock-flash-003` went through RECOVERY (NAT-012 saw the ADB `recovery`
  state; Claude's 10:15Z read showed `ro.boot.bootreason=recovery`). NAT-014 reviews this.
- Upload acknowledgements show only that S-Boot received the data. Only a full readback from
  Android shows what is on the partition.
