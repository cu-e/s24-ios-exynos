#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-062: the verdict of one native run of loader-diag-xnu-run-usb, and the kernel's own console log as the host received it.

    analyze_nat062.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json [--out RUN/analysis.json] [--log-out RUN/kernel-log.txt]
                      [--allow-synthetic]

This reuses NAT-059's analyzer (analyze_nat059.py: NAT-049's integrity, T0, boot-id, provenance and USB-coverage rules, the stop notes of NAT-052's
contract, the TTBR0 rules of NAT-059) for everything the two images share, under this image's name, and replaces the one rule that no longer holds:
the last stop (C checkpoint 21) is not a hold any more. The image sends the log of the payload kernel (`KL begin/...records.../end`, glue62_impl.h)
at that stop and resumes the kernel; if the kernel hands control back by itself (reason 0: its timer `loader_return_after`, or a panic) the loader
notes the arrival (`CK n=28 ... x2=0x0`), sends the log again and holds (`HOLD ...`).

  PASS       NAT-059's PASS conditions for the notes n=1..27 (transport clean, no gap, TTBR0 evidence, no exception), then in this order: one complete
             log dump with why=1 (begin, records covering exactly the head and tail it announces, end with the same totals), the kernel's own return
             note (x2=0), one complete dump with why=2, and the HOLD record. The kernel ran after checkpoint 21 and delivered its log.
  PARTIAL    the channel works but one step of that chain is missing: no dump at the final stop (a `KL refused` record, a truncated or damaged dump),
             or NO RETURN NOTE (the kernel did not hand control back before the loader's deadline reset or the watchdog: what the final dump holds is
             then all the text there is), or a damaged return dump, or no HOLD after it. The `why` line names the step.
  EXCEPTION / FAIL / undetermined   as in NAT-059 (an early-exception note or a loader exception record; no readable record; no usable host observation).

The reconstructed text of every complete or partial dump goes to --log-out (the kernel's characters, newlines restored; a gap of bytes the loader
did not send is marked). A PASS says the log was delivered, not that the log shows a healthy kernel: read the text. Reads files only; opens no device."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A59 = _load("nat062_nat059_analyze", PROC / "nat-059" / "analyze_nat059.py")
A49, D52 = A59.A49, A59.D52

IMAGE = "loader-diag-xnu-run-usb"
VERDICTS = A59.VERDICTS
STOP_LIST = A59.STOP_LIST              # unchanged: 5 assembly stops + 22 C stops; the last note of the list is n=27 (checkpoint 21)
RAW = 96                               # log bytes per record (glue62_impl.h NAT062_RAW)
HEAD_MAX = {1: 8192, 2: 8192}
TAIL_MAX = {1: 8192, 2: 32768}
LOG_MAX = 0x180000

BEGIN = re.compile(r"^KL begin why=(?P<why>\d+) len=(?P<len>\d+) head=(?P<head>\d+) tail=(?P<tail>\d+) gap=(?P<gap>\d+) x0=(?P<x0>0x[0-9a-f]+)$")
DATA = re.compile(r"^KL (?P<off>[0-9a-f]{6}) (?P<text>.+)$")
END = re.compile(r"^KL end why=(?P<why>\d+) recs=(?P<recs>\d+) bytes=(?P<bytes>\d+)$")
REFUSED = re.compile(r"^KL refused why=(?P<why>\d+) x0=(?P<x0>0x[0-9a-f]+) x1=(?P<x1>0x[0-9a-f]+)$")
ESC = re.compile(r"\\(?:(?P<c>[\\nr])|x(?P<h>[0-9a-f]{2}))")


def unescape(s):
    """Invert glue62_impl.h's n62_esc: \\\\ -> backslash, \\n, \\r, \\xHH -> byte; any other backslash is damage (returns None)."""
    out = bytearray()
    i = 0
    while i < len(s):
        ch = s[i]
        if ch != "\\":
            if not 0x20 <= ord(ch) < 0x7f:
                return None
            out.append(ord(ch))
            i += 1
            continue
        m = ESC.match(s, i)
        if not m:
            return None
        out += {"\\": b"\\", "n": b"\n", "r": b"\r"}[m.group("c")] if m.group("c") else bytes([int(m.group("h"), 16)])
        i = m.end()
    return bytes(out)


def parse_kl(lines):
    """-> (dumps, stray). Each dump: dict(why, status, begin, records=[(off, bytes)], end, refused, problems, line=index of `begin`, end_line).
    `stray` lists KL lines outside any begin..end (index, line)."""
    dumps, cur, stray = [], None, []
    for i, line in enumerate(lines):
        if not line.startswith("KL "):
            continue
        m = BEGIN.match(line)
        if m:
            if cur is not None:
                cur["problems"].append("a new `KL begin` arrived before the end of this dump")
                cur["status"] = "truncated"
                dumps.append(cur)
            cur = dict(why=int(m["why"]), begin={k: int(v, 16) if k == "x0" else int(v) for k, v in m.groupdict().items()}, records=[], end=None,
                       refused=None, problems=[], status="open", line=i, end_line=None)
            continue
        m = REFUSED.match(line)
        if m:
            if cur is not None:
                cur["problems"].append("a `KL refused` record arrived inside a dump")
            dumps.append(dict(why=int(m["why"]), status="refused", begin=None, records=[], end=None, problems=[], line=i, end_line=i,
                              refused=dict(x0=int(m["x0"], 16), x1=int(m["x1"], 16))))
            continue
        m = END.match(line)
        if m:
            if cur is None:
                stray.append((i, line))
                continue
            cur["end"] = dict(why=int(m["why"]), recs=int(m["recs"]), bytes=int(m["bytes"]))
            cur["end_line"] = i
            cur["status"] = "closed"
            dumps.append(cur)
            cur = None
            continue
        m = DATA.match(line)
        if m and cur is not None:
            raw = unescape(m["text"])
            if raw is None:
                cur["problems"].append("a record at offset %s is not valid escaped text" % m["off"])
                raw = b""
            cur["records"].append((int(m["off"], 16), raw))
            continue
        (cur["problems"] if cur is not None else stray).append("unparsed KL line" if cur is not None else (i, line))
    if cur is not None:
        cur["problems"].append("the dump has no `KL end` record (the stream stopped inside it)")
        cur["status"] = "truncated"
        dumps.append(cur)
    for d in dumps:
        if d["status"] == "closed":
            check_dump(d)
    return dumps, stray


def check_dump(d):
    """Is the dump complete: the records cover exactly the head and tail the begin record announces, in order, and the end record agrees."""
    b, e, why = d["begin"], d["end"], d["problems"]
    if e["why"] != b["why"]:
        why.append("end record why=%d does not match begin why=%d" % (e["why"], b["why"]))
    if b["head"] + b["tail"] + b["gap"] != b["len"]:
        why.append("head+tail+gap (%d) is not len (%d)" % (b["head"] + b["tail"] + b["gap"], b["len"]))
    if b["why"] not in HEAD_MAX or b["len"] > LOG_MAX:
        why.append("the announced sizes are outside what the image can send (why %d, len %d)" % (b["why"], b["len"]))
    else:
        head = min(b["len"], HEAD_MAX[b["why"]])
        tail = min(b["len"] - head, TAIL_MAX[b["why"]])
        if (b["head"], b["tail"]) != (head, tail):
            why.append("the dump does not send the head and tail this image sends (len %d: expected head %d tail %d, announced %d and %d)" % (b["len"], head, tail, b["head"], b["tail"]))
    expect = []
    for lo, hi in ((b["len"] - b["tail"], b["len"]), (0, b["head"])):        # the newest text first, then the oldest
        off = lo
        while off < hi:
            expect.append((off, min(RAW, hi - off)))
            off += RAW
    got = [(off, len(raw)) for off, raw in d["records"]]
    if got != expect:
        why.append("the records do not cover the announced ranges: %d received, %d expected%s" % (
            len(got), len(expect), "" if len(got) != len(expect) else " (offsets or sizes differ)"))
    if e["recs"] != len(d["records"]) or e["bytes"] != sum(len(r) for _, r in d["records"]):
        why.append("the end record says %d records / %d bytes, received %d / %d" % (e["recs"], e["bytes"], len(d["records"]), sum(len(r) for _, r in d["records"])))
    d["status"] = "complete" if not why else "damaged"


def dump_text(d):
    """The kernel text a dump carries: head, a marker for the bytes not sent, tail (what was received, in log order)."""
    if d["begin"] is None:
        return ""
    b = d["begin"]
    head = b"".join(r for off, r in sorted(d["records"]) if off < b["head"])
    tail = b"".join(r for off, r in sorted(d["records"]) if off >= b["len"] - b["tail"] and off >= b["head"])
    gap = b"" if not b["gap"] else ("\n[... %d bytes of the log were not sent ...]\n" % b["gap"]).encode()
    return (head + gap + tail).decode("utf-8", "replace")


def chain_problems(lines):
    """The NAT-062 chain after the stop notes: final dump, return note, return dump, HOLD. -> (problems, summary)."""
    dumps, stray = parse_kl(lines)
    notes = [(i, D52.parse_note(l)) for i, l in enumerate(lines)]
    notes = [(i, n) for i, n in notes if n is not None]
    last_stop = max((i for i, n in notes if n["x2"] != 0 and n["last"] == STOP_LIST[-1]), default=None)
    returns = [(i, n) for i, n in notes if n["x2"] == 0]
    hold = max((i for i, l in enumerate(lines) if D52.HOLD.match(l)), default=None)
    why = []
    summary = dict(dumps=[dict(why=d["why"], status=d["status"], problems=d["problems"], line=d["line"], len=(d["begin"] or {}).get("len"),
                               head=(d["begin"] or {}).get("head"), tail=(d["begin"] or {}).get("tail"), gap=(d["begin"] or {}).get("gap"),
                               recs=(d["end"] or {}).get("recs"), bytes=(d["end"] or {}).get("bytes"), refused=d["refused"]) for d in dumps],
                   stray=stray, return_notes=[n["n"] for _, n in returns], return_x3=[hex(n["x3"]) for _, n in returns],
                   hold=None if hold is None else D52.HOLD.match(lines[hold]).groupdict())
    if stray:
        why.append("%d KL line(s) outside any dump" % len(stray))
    final = [d for d in dumps if d["why"] == 1]
    ret = [d for d in dumps if d["why"] == 2]
    if last_stop is None:
        return why, summary, dumps          # the notes rule (note_problems) names that; nothing to say about what follows
    if len(final) != 1:
        why.append("%d log dump(s) with why=1 (the final stop's), expected exactly one" % len(final))
    for d in final:
        if d["status"] != "complete":
            why.append("the dump at the final stop is %s%s" % (d["status"], (": " + "; ".join(d["problems"])) if d["problems"] else (
                " (x0=%s x1=%s: the stop's registers were not the kernel's log)" % (hex(d["refused"]["x0"]), hex(d["refused"]["x1"])) if d["refused"] else "")))
        elif d["line"] < last_stop:
            why.append("the final dump arrived before the n=27 note")
    if not returns:
        why.append("NO RETURN: the kernel did not hand control back after checkpoint 21 (no reason-0 arrival before the stream ended): the final dump is all the text there is")
        return why, summary, dumps
    if len(returns) != 1:
        why.append("%d reason-0 notes, expected one" % len(returns))
    ri = returns[0][0]
    after = [d for d in ret if d["line"] > ri]
    if len(ret) != 1 or len(after) != 1:
        why.append("%d dump(s) with why=2, %d after the return note, expected exactly one" % (len(ret), len(after)))
    for d in ret:
        if d["status"] != "complete":
            why.append("the dump at the kernel's return is %s%s" % (d["status"], (": " + "; ".join(d["problems"])) if d["problems"] else (
                " (x0=%s x1=%s)" % (hex(d["refused"]["x0"]), hex(d["refused"]["x1"])) if d["refused"] else "")))
    if hold is None:
        why.append("no HOLD record after the kernel's return")
    elif ret and any(d["end_line"] is not None and hold < d["end_line"] for d in ret):
        why.append("the HOLD record arrived before the end of the return dump")
    return why, summary, dumps


_note_problems59 = A59.note_problems
_progress52 = D52.progress


def progress62(lines):
    """NAT-052's progress() with the reason-0 arrival (the kernel's own return, x2=0) taken out of the stop list: `stops` are the arrivals that
    the stub resumes (n=1..27), `return_notes` the others. The raw lines stay for the chain check (dumps, return, HOLD)."""
    p = _progress52(lines)
    stops = [n for n in p["stops"] if n["x2"] != 0]
    p["return_notes"] = [n for n in p["stops"] if n["x2"] == 0]
    p["stops"] = stops
    p["gaps"] = [(a["n"], b["n"]) for a, b in zip(stops, stops[1:]) if b["n"] != a["n"] + 1]
    p["reached_final"] = bool(stops and stops[-1]["mask"] & D52.MASK_FINAL)
    p["last"] = stops[-1]["last"] if stops else None
    p["lines"] = list(lines)
    return p


def note_problems62(prog):
    """NAT-059's rules for the stop notes n=1..27 (a HOLD is not required there: with no return the loader never regains control, so the chain
    below decides about it), then the NAT-062 chain after them."""
    why = _note_problems59(dict(prog, held=True))
    if prog["return_notes"] and not prog["stops"]:
        why.append("the only notes are reason-0 arrivals: the kernel returned before the first stop")
    if prog["stops"] and not why:
        extra, _, _ = chain_problems(prog["lines"])
        why += extra
    elif prog["stops"]:
        # the stop notes already fail: still say what the chain after them shows (one line), without piling reasons
        _, summary, _ = chain_problems(prog["lines"])
        done = [d for d in summary["dumps"] if d["status"] == "complete"]
        if done:
            why.append("%d complete log dump(s) did arrive (why=%s)" % (len(done), ",".join(str(d["why"]) for d in done)))
    return why


PASS59 = re.compile(r"one boot of \S+: (?P<records>\d+) records, \d+ stop notes \(n=1\.\.\d+, final checkpoint \d+\), the hold announced, no drop, nothing unread, no exception")


def pass_text(m, summary):
    """What a PASS of this image says (replaces NAT-059's sentence, which is about a hold at the last stop)."""
    by = {d["why"]: d for d in summary["dumps"] if d["status"] == "complete"}
    f, r = by[1], by[2]
    return ("one boot of %s: %s records, the 27 stop notes (n=1..27, final checkpoint %d), the kernel's log at the last stop (%d bytes long: %d + %d sent in %d records, %d not sent), "
            "the kernel's own return (reason-0 note n=%s, x3=%s), its log (%d bytes long: %d + %d sent in %d records, %d not sent), then HOLD; no drop, nothing unread, no exception" % (
                IMAGE, m["records"], STOP_LIST[-1], f["len"], f["head"], f["tail"], f["recs"], f["gap"], ",".join(map(str, summary["return_notes"])), ",".join(summary["return_x3"]),
                r["len"], r["head"], r["tail"], r["recs"], r["gap"]))


def analyze(root, events, report, allow_synthetic=False, deadline=A59.DEADLINE_S, wdt=A59.WDT_S):
    """NAT-059's analysis under this image's name, with this image's rules for what follows the stop notes; adds `kernel_log`."""
    A59.IMAGE = IMAGE
    A59.note_problems = note_problems62
    D52.progress = progress62
    try:
        out = A59.analyze(root, events, report, allow_synthetic, deadline, wdt)
    finally:
        A59.note_problems = _note_problems59
        D52.progress = _progress52
        A59.IMAGE = "loader-diag-xnu-ckpt4-usb"
    out["image"] = IMAGE
    boot = out.get("boot")
    out["kernel_log"] = None
    if boot:
        lines = A59.boot_texts(root, boot["name"])
        _, summary, dumps = chain_problems(lines)
        out["kernel_log"] = dict(summary, texts={str(d["why"]) + ("" if d["status"] == "complete" else "-" + d["status"]): dump_text(d) for d in dumps if d["begin"]})
        m = PASS59.search(out.get("why") or "")
        if m and out["verdict"] in ("PASS", "simulated-PASS", "undetermined"):
            out["why"] = out["why"][:m.start()] + pass_text(m, summary) + out["why"][m.end():]
    return out


def write_log(out, path):
    """The reconstructed texts, one section per dump (nothing is invented: only what arrived)."""
    kl = out.get("kernel_log")
    parts = []
    for key, text in sorted((kl or {}).get("texts", {}).items()):
        parts.append("===== dump %s (why=1: at the last stop, before the kernel resumed; why=2: at the kernel's own return) =====\n%s\n" % (key, text))
    with open(path, "w", encoding="utf-8", newline="") as fh:        # newline="": the kernel text has CR LF and must be written as received
        fh.write("".join(parts))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--events", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out")
    ap.add_argument("--log-out")
    ap.add_argument("--allow-synthetic", action="store_true", help="host tests: label the verdict simulated-* instead of refusing it")
    a = ap.parse_args(argv)
    events, _ = A49.read_jsonl(a.events)
    report = A49.read_json(a.report) or {}
    res = analyze(a.archive, events, report, a.allow_synthetic)
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")
    if a.log_out:
        write_log(res, a.log_out)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
