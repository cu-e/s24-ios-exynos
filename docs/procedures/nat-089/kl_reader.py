#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-089: the kernel-log dump (`KL begin ... KL end`, NAT-062's format) of a collector archive, read WITHOUT refusing a boot that lost bytes in transport.

Why: NAT-088's returned text sat in the second boot of the archive. That boot carried two producer-reported ring overruns (`drop` frames, 1,028 and 3,338 bytes), so
NAT-081's replay rule (the later boot must be contiguous from device sequence 0) refused it and the pre-registered ladder read R9. The text itself was fine: every `KL <offset>
<escaped bytes>` record names its own offset in the kernel buffer, so a lost record is a HOLE WITH A KNOWN RANGE, not a damaged stream. This module keeps that knowledge:

  * every boot of the archive is parsed with NAT-062's own `parse_kl` / `unescape` (imported, not copied);
  * the dumps of different boots that announce the same sizes (a replay) are merged by offset; two different byte strings at one offset are a CONFLICT, listed and never
    chosen between (the first boot's bytes are kept in the text and the conflict is reported);
  * the ranges the announced head and tail should cover, minus the records received, are the holes; the announced gap (the middle of the kernel buffer the image never sends)
    is a hole of its own kind;
  * `text` is the head, a gap marker, the tail, with a marker line at every hole, so that a regex over it can never join two lines across missing bytes.

Nothing here decides whether launchd did anything; that is the analyser's job. What it cannot show: what the holes and the gap contained."""
import importlib.util
import json
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


A62 = _load("nat089_nat062", PROC / "nat-062" / "analyze_nat062.py")
RAW = A62.RAW
HOLE_MARK = "\n[... %d bytes lost in transport ...]\n"
GAP_MARK = "\n[... %d bytes of the log were not sent ...]\n"


def boot_lines(frames_path):
    """The `log` frame texts of one boot in device-sequence order (what the image sent, as text)."""
    rows = []
    for line in Path(frames_path).read_text().splitlines():
        if not line.strip():
            continue
        f = json.loads(line)["frame"]
        if f.get("kind") == "log" and "dev_seq" in f and isinstance(f.get("text"), str):
            rows.append((f["dev_seq"], f["text"]))
    rows.sort(key=lambda r: r[0])
    return [t for _, t in rows]


def boot_drops(frames_path):
    """The producer-reported drops of one boot: [(at_offset, lost_bytes, reason)]. Their `at_offset` counts the loader's own ring, not the kernel buffer."""
    import base64
    out = []
    for line in Path(frames_path).read_text().splitlines():
        if not line.strip():
            continue
        f = json.loads(line)["frame"]
        if f.get("kind") == "drop":
            d = json.loads(base64.b64decode(f["data_b64"]))
            out.append((d["at_offset"], d["lost_bytes"], d.get("reason", f.get("reason"))))
    return out


def expected_chunks(begin):
    """The (offset, size) list a complete dump with this `begin` sends: the newest text (tail) first, then the oldest (head); the same rule as NAT-062's check_dump."""
    out = []
    for lo, hi in ((begin["len"] - begin["tail"], begin["len"]), (0, begin["head"])):
        off = lo
        while off < hi:
            out.append((off, min(RAW, hi - off)))
            off += RAW
    return out


def merge(boots):
    """`boots`: [(name, [dump, ...])] with dumps from NAT-062's parse_kl. -> [merged dump], one per distinct (why, announced sizes), in first-seen order.
    merged = dict(why, begin, bytes={offset: bytes}, boots=[names], conflicts=[offset], closed=bool, problems=[...])."""
    merged = {}
    for name, dumps in boots:
        for d in dumps:
            if d.get("begin") is None:
                continue
            b = d["begin"]
            key = (b["why"], b["len"], b["head"], b["tail"], b["gap"])
            m = merged.setdefault(key, dict(why=b["why"], begin=b, bytes={}, boots=[], conflicts=[], closed=False, problems=[]))
            m["boots"].append(name)
            m["closed"] = m["closed"] or d.get("end") is not None
            for off, raw in d["records"]:
                if off in m["bytes"] and m["bytes"][off] != raw:
                    if off not in m["conflicts"]:
                        m["conflicts"].append(off)
                    continue
                m["bytes"][off] = raw
            m["problems"] += [p for p in d["problems"] if p not in m["problems"]]
    return list(merged.values())


def holes_of(m):
    """-> (holes, extra): holes = [(lo, hi)] of the head and tail ranges the announced sizes say should have arrived and did not (merged, ascending);
    extra = offsets that were received but are not in the expected list (the dump is not what its `begin` says)."""
    b = m["begin"]
    exp = expected_chunks(b)
    want = {off: n for off, n in exp}
    miss = sorted((off, off + n) for off, n in exp if m["bytes"].get(off) is None or len(m["bytes"][off]) != n)
    holes = []
    for lo, hi in miss:
        if holes and holes[-1][1] == lo:
            holes[-1] = (holes[-1][0], hi)
        else:
            holes.append((lo, hi))
    extra = sorted(off for off in m["bytes"] if off not in want)
    return holes, extra


def text_of(m):
    """The kernel text of a merged dump: head, gap marker, tail; a marker at every hole. -> str"""
    b = m["begin"]
    parts = []
    for lo, hi in ((0, b["head"]), (b["len"] - b["tail"], b["len"])):
        off = lo
        seg = []
        while off < hi:
            n = min(RAW, hi - off)
            raw = m["bytes"].get(off)
            if raw is not None and len(raw) == n:
                seg.append(raw.decode("utf-8", "replace"))
            else:
                if seg and seg[-1].startswith("\x00HOLE"):
                    seg[-1] = "\x00HOLE%d" % (int(seg[-1][5:]) + n)
                else:
                    seg.append("\x00HOLE%d" % n)
            off += n
        parts.append("".join(HOLE_MARK % int(s[5:]) if s.startswith("\x00HOLE") else s for s in seg))
    gap = GAP_MARK % b["gap"] if b["gap"] else ""
    return parts[0] + gap + parts[1]


def read_archive(root):
    """-> dict(dumps=[merged dump with holes/text/problems], boots=[names], drops={boot name: [...]}). Raises nothing for a missing dump: an empty list says there is none."""
    root = Path(root)
    boots, drops, names = [], {}, []
    for d in sorted((root / "boots").iterdir()) if (root / "boots").is_dir() else []:
        fr = d / "frames.jsonl"
        if not fr.is_file():
            continue
        names.append(d.name)
        dumps, _stray = A62.parse_kl(boot_lines(fr))
        boots.append((d.name, dumps))
        drops[d.name] = boot_drops(fr)
    out = []
    for m in merge(boots):
        holes, extra = holes_of(m)
        m["holes"], m["extra_offsets"] = holes, extra
        m["hole_bytes"] = sum(hi - lo for lo, hi in holes)
        m["text"] = text_of(m)
        out.append(m)
    return dict(dumps=out, boots=names, drops=drops)
