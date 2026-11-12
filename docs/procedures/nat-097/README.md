# NAT-097: kernel-log reader v2 (dumps that lost their `KL begin` record)

Host code, tests and a mutation pass. Evidence kind **host-test**. Nothing here ran
on the phone and nothing here measures it.

## The gap it closes

NAT-093's returned kernel text sat in the collector's second boot. The producer
had reported two ring-overrun drops that took 83 of the dump's 428 records,
including the `KL begin` line. NAT-089's `kl_reader.py` needs `begin` for the
announced sizes, so it reported no dump and the pre-registered ladder read A8,
although 345 records with their own offsets and the `KL end` line had arrived.
`docs/procedures/nat-093/posthoc_boot2.py` read them by hand after the result.
This directory turns that reading into a rule written before the next run.

## The rule (`kl_reader2.py`)

What `begin` carries is `(why, len, head, tail, gap)`. Without it:

* `head = min(len, HEAD_MAX[why])`, `tail = min(len - head, TAIL_MAX[why])`,
  `gap = len - head - tail`; records are 96 bytes, the last of a segment shorter.
* The `KL end` line says `recs` and `bytes`, and `bytes = head + tail`. If
  `bytes` is below `HEAD_MAX + TAIL_MAX` the dump is shorter than the cap and
  `len = bytes` exactly (the last record may be lost; the length is still known).
* If `bytes` equals the cap, `len` is the end of the last tail record. That is
  the only tail record shorter than 96 bytes (8192 and 32768 are 32 mod 96), so
  the record with the highest offset at or above `HEAD_MAX` must have exactly
  that final size. If it has 96 bytes the end of the tail was lost and `len` is
  **not located**: the group is refused, not guessed.
* Whatever the case, the geometry is accepted only if the end line's `recs` and
  `bytes` equal it, every received record is on its grid (same offset and size),
  and the records came in the order the image sends them (tail ascending, then
  head ascending) with no offset twice. Otherwise the group goes to
  `unreadable` with the reason and no text is made of it.

Accepted groups become dumps in `parse_kl`'s shape and go through NAT-089's own
`merge`, `holes_of` and `text_of`, so replays across boots merge by offset, lost
records are exact holes with markers, and a dump with a real `begin` is read
exactly as before (a test compares the two readers on the same fixtures). The
merged dump carries `begin_inferred`, false when some boot of the archive had a
real `begin` with the same sizes.

`analyze_nat097.py` is NAT-089's `analyze_text` (rows A1-A8, imported and
unchanged) over that text; an inferred dump is named in the result and in the
reason text, and refused groups are listed under `facts.unreadable` and in the A8
reason when no dump was read at all.

## Real archive (the check that matters)

On NAT-093's archive (`artifacts/nat-092/run-001/archive`, a local artifact) the
reader finds one inferred dump: length 170,097, head 8,192, tail 32,768, gap
129,137, 345 of 428 records, holes `[137329, 142129)` and `[145489, 148657)`
(7,968 bytes), equal to `docs/procedures/nat-093/posthoc.json` and to the bytes
the hand reader read. The analyser's row on that archive stays **A8**
(`no launchd line in the returned text`): the head ends inside rc's `vm_stat`
output and the tail is the CPU-monitor flood, so the new reader changes how the
text is obtained, not what NAT-093 showed.

## Checks

* `test_nat097.py`: 50 tests, all pass (hand-built dump layouts with literal
  offsets; refusals with exact messages for the cases above; boundary cases at
  `len = head + tail`; replay and mixed boots; the analyser compared with
  NAT-089's on the same archives; the real NAT-093 archive, skipped when the
  local artifact is absent).
* `mutate_nat097.py`: one pass over `kl_reader2.py` and `analyze_nat097.py`
  (4 jobs, 1.5 GiB per-process cap, 120 s timeout); the numbers are in
  `mutation.json` and `evidence.json`. The first pass left 22 survivors, 15 of
  which exposed missing assertions (exact refusal messages, the boundary at
  `len = head + tail`, a length-0 and a length-1 dump, boots without frames,
  producer drops, the `unreadable` list); tests were added and the pass
  repeated. The remaining survivors are explained in `equivalent.json`.

## Evidence levels

| Level | State |
| --- | --- |
| code written | yes |
| built | not applicable (Python) |
| checked in a model | tests and mutation pass, plus the real NAT-093 archive as input |
| ran on the S24 | no |
| showed real iOS UI | no |

## What it cannot show

What the holes, the unsent middle of the kernel buffer and a refused group
contained. A capped dump whose last tail record was lost is still refused; the
fallback is a hand reading labelled post hoc, as in NAT-093.

## Files

`task.json`, `kl_reader2.py`, `analyze_nat097.py`, `test_nat097.py`,
`mutate_nat097.py`, `equivalent.json`, `mutation.json`, `evidence.json`.
