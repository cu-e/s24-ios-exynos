#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-097: reader v2 for the kernel-log dumps (NAT-062's `KL begin ... KL end` format) of a collector archive, including a dump whose `KL begin` record was lost in transport.

Why: in NAT-093's archive the kernel text sat in the collector's second boot, and the producer had reported two ring-overrun drops that took 83 of the 428 records, among them the
`KL begin` line. NAT-089's reader (`kl_reader.py`) needs `begin` for the announced sizes, so it reported no dump and the pre-registered ladder said A8, although 345 records with their
own offsets and the `KL end` line had arrived. docs/procedures/nat-093/posthoc_boot2.py then read them by hand, after the result. This module makes that reading a rule written before the
next run.

What `begin` carries is (why, len, head, tail, gap). Without it they are derived from what the format fixes (analyze_nat062.py, glue62_impl.h):

  * head = min(len, HEAD_MAX[why]), tail = min(len - head, TAIL_MAX[why]), gap = len - head - tail; records are RAW=96 bytes, the last one of a segment shorter;
  * the `KL end` line says recs and bytes, and bytes = head + tail;
  * so if bytes < HEAD_MAX + TAIL_MAX the dump is shorter than the cap, gap is 0 and len = bytes exactly;
  * if bytes == HEAD_MAX + TAIL_MAX the dump is capped and len is the end of the last tail record. That record is the only tail record shorter than 96 bytes (HEAD_MAX and TAIL_MAX
    are not multiples of 96: 8192 = 85*96 + 32, 32768 = 341*96 + 32), so when the record with the highest offset at or above HEAD_MAX has that final size, len = its offset + its size;
    when it has 96 bytes the final record(s) were lost and len is NOT located: the dump is refused (an ambiguity of 96*k + 32 bytes), not guessed.

An inferred geometry is accepted only if all of this holds (otherwise the group is listed under `unreadable` with the reason, and no text is made of it):
  1. the end line's recs and bytes equal the inferred geometry's expected record count and head + tail;
  2. every received record is on the inferred grid (same offset, same size);
  3. the records arrived in the order the image sends them (tail ascending, then head ascending) with no offset twice.
The merged dump is marked `begin_inferred` unless some boot of the archive carried a real `begin` with the same sizes. Dumps with a real begin go through NAT-089's merge, holes and text
unchanged. What this module cannot show: what the holes, the gap and a refused group contained."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


K = _load("nat097_kl_reader", PROC / "nat-089" / "kl_reader.py")
A62 = K.A62
RAW = K.RAW


def final_size(segment_max):
    """The size of the last record of a segment of `segment_max` bytes sent in RAW-byte records."""
    return (segment_max - 1) % RAW + 1


def begin_key(b):
    return (b["why"], b["len"], b["head"], b["tail"], b["gap"])


def groups_of(stray):
    """`stray` as parse_kl returns it ([(index, line)] outside any begin..end) -> (groups, leftover).
    group = dict(records=[(offset, bytes)], end=dict(why, recs, bytes) or None, line=index of the first line, problems=[...]); a group ends at its `KL end` line.
    The last group has end None when records came without one."""
    groups, cur = [], dict(records=[], end=None, line=None, problems=[])
    for i, line in stray:
        if cur["line"] is None:
            cur["line"] = i
        m = A62.END.match(line)
        if m:
            cur["end"] = dict(why=int(m["why"]), recs=int(m["recs"]), bytes=int(m["bytes"]))
            groups.append(cur)
            cur = dict(records=[], end=None, line=None, problems=[])
            continue
        m = A62.DATA.match(line)
        if m:
            raw = A62.unescape(m["text"])
            if raw is None:
                cur["problems"].append("a record at offset %s is not valid escaped text (treated as lost)" % m["off"])
            else:
                cur["records"].append((int(m["off"], 16), raw))
            continue
        cur["problems"].append("unparsed KL line outside a dump")
    if cur["records"] or cur["problems"]:
        groups.append(cur)
    return groups


def infer(group):
    """-> (dump, None) with a dump in parse_kl's shape (begin inferred, begin_inferred True), or (None, reason)."""
    e = group["end"]
    recs = group["records"]
    if e is None:
        return None, ("records without a `KL end` line: the dump's size cannot be checked" if recs else "unparseable KL lines and no end line")
    why = e["why"]
    if why not in A62.HEAD_MAX:
        return None, "the end line's why=%d is not one this image sends" % why
    if not recs:
        return None, "no record of the dump arrived"
    hm, tm = A62.HEAD_MAX[why], A62.TAIL_MAX[why]
    cap = hm + tm
    if e["bytes"] > cap:
        return None, "the end line says %d bytes, more than head + tail can hold (%d)" % (e["bytes"], cap)
    if e["bytes"] < cap:
        length = e["bytes"]
    else:
        fin = final_size(tm)
        tails = [(o, r) for o, r in recs if o >= hm]
        if not tails:
            return None, "capped dump and no tail record arrived: its length is not located"
        o, r = max(tails, key=lambda t: t[0])
        if fin == RAW or len(r) != fin:
            return None, "capped dump and the last received tail record (offset 0x%x) has %d bytes, not the final record's %d: the end of the tail was lost and the length is not located" % (
                o, len(r), fin)
        length = o + len(r)
        if length < cap:
            return None, "the length found from the last tail record (%d) is below head + tail (%d)" % (length, cap)
    head = min(length, hm)
    tail = min(length - head, tm)
    begin = dict(why=why, len=length, head=head, tail=tail, gap=length - head - tail, x0=None)
    exp = K.expected_chunks(begin)
    if e["recs"] != len(exp) or e["bytes"] != head + tail:
        return None, "the end line says %d records / %d bytes; the inferred geometry (len %d, head %d, tail %d) needs %d / %d" % (e["recs"], e["bytes"], length, head, tail, len(exp), head + tail)
    pos = {off: (k, n) for k, (off, n) in enumerate(exp)}
    last = -1
    for off, raw in recs:
        p = pos.get(off)
        if p is None or p[1] != len(raw):
            return None, "the record at offset 0x%x (%d bytes) is not on the inferred grid" % (off, len(raw))
        if p[0] <= last:
            return None, "the record at offset 0x%x is out of the order the image sends or repeated" % off
        last = p[0]
    return dict(why=why, status="inferred", begin=begin, records=list(recs), end=e, refused=None, problems=list(group["problems"]), line=group["line"], end_line=None,
                begin_inferred=True), None


def read_archive2(root):
    """-> dict(dumps=[merged dump with holes/text/problems/begin_inferred], boots=[names], drops={boot: [...]}, unreadable=[dict(boot, reason, records, end, line)])."""
    root = Path(root)
    boots, drops, names, unreadable, real = [], {}, [], [], set()
    for d in sorted((root / "boots").iterdir()) if (root / "boots").is_dir() else []:
        fr = d / "frames.jsonl"
        if not fr.is_file():
            continue
        names.append(d.name)
        dumps, stray = A62.parse_kl(K.boot_lines(fr))
        real |= {begin_key(x["begin"]) for x in dumps if x.get("begin")}
        found = []
        for g in groups_of(stray):
            x, why = infer(g)
            if x is None:
                unreadable.append(dict(boot=d.name, reason=why, records=len(g["records"]), end=g["end"], line=g["line"]))
            else:
                found.append(x)
        boots.append((d.name, sorted(dumps + found, key=lambda x: x["line"])))
        drops[d.name] = K.boot_drops(fr)
    out = []
    for m in K.merge(boots):
        holes, extra = K.holes_of(m)
        m["holes"], m["extra_offsets"] = holes, extra
        m["hole_bytes"] = sum(hi - lo for lo, hi in holes)
        m["text"] = K.text_of(m)
        m["begin_inferred"] = begin_key(m["begin"]) not in real
        out.append(m)
    return dict(dumps=out, boots=names, drops=drops, unreadable=unreadable)
