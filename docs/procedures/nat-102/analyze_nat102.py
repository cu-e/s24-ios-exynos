#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102: the heartbeat ladder (rows H0-H5) over the kernel text that NAT-097's reader v2 returns, for the image whose rc starts NAT-101's `hb` before launchd.

    analyze_nat102.py --archive ARCHIVE --jobs-dir DIR --out FILE.json

`hb` (docs/procedures/nat-101/src/hb.c) writes `SWEET hb:` lines and runs Apple's /bin/ps with its output on the console, independent of launchd, logd and the job plists. The rows say
how far that got into the text the project can send back, highest row first (the first row whose condition holds is the result):

  H5 hb-ps-lists         at least one complete `ps` list after an `hb` round marker (the console path works after launchd started; the lists name the processes that exist: blocker B7)
  H3 hb-rounds-no-list   at least one round marker, but no recognisable ps list (hb ran; its ps did not print, was cut, or the lists are in the unsent part)
  H2 hb-start-only       the `start` line only (hb started, no round marker in the text)
  H1 no-hb-line          no `SWEET hb:` line in the text
  H0 no-kernel-text      no why=2 kernel-log dump with text in the archive (nothing to read)

Facts for every row: the round markers and ps status lines seen (with raw wait status and elapsed ms), hb's pid/ppid, the lists (both formats: `ps -A` = PID TTY TIME CMD, `ps -Ao pid,ppid,stat,comm` =
PID PPID STAT COMM), the processes of the last list, which self-starting Apple jobs of the image's job table are in it, zombie and state counts, pid growth between the first and last list, the lists
that are NOT preceded by an hb marker (the com.nat085.ps job's output, i.e. launchd's own routing), launchd console-form lines (NAT-089's reader), and the hole/gap numbers of the dump.

What it cannot show: what the holes and the unsent middle of the kernel buffer contained, why a line is missing (hb not started / console write lost / outside the window), and nothing about display or
UI. It reads text, it does not touch a device."""
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
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A89 = _load("nat102_analyze89", PROC / "nat-089" / "analyze_nat089.py")
R2 = _load("nat102_reader2", PROC / "nat-097" / "kl_reader2.py")

ROWS = {0: "no-kernel-text", 1: "no-hb-line", 2: "hb-start-only", 3: "hb-rounds-no-list", 5: "hb-ps-lists"}
HB_START = re.compile(r"SWEET hb: start pid=(\d+) ppid=(\d+) period=(\d+)s rounds=(\d+) ps_timeout=(\d+)s\s*$")
HB_MARK = re.compile(r"SWEET hb: n=(\d+) pid=(\d+) ppid=(\d+) up=(\d+)\s*$")
HB_PS = re.compile(r"SWEET hb: n=(\d+) ps pid=(-?\d+) status=(-?\d+) ms=(-?\d+)( timeout-killed)?\s*$")
HB_DONE = re.compile(r"SWEET hb: done rounds=(\d+)\s*$")
HB_ANY = re.compile(r"SWEET hb: ")
HEAD_A = A89.PS_HEADER
HEAD_O = re.compile(r"^[ \t]*PID[ \t]+PPID[ \t]+STAT[ \t]+COMM[ \t]*$")
ROW_O = re.compile(r"^[ \t]*(\d+)[ \t]+(\d+)[ \t]+(\S+)[ \t]+(.+?)[ \t]*$")
HOLE = A89.HOLE_LINE
LOGD_PROGRAM = "/usr/libexec/logd"       # a list that names it was printed while Apple's logd existed, i.e. after launchd started it


def parse(text):
    """-> dict(start, marks, ps_status, done, lists, unknown_hb) from the kernel text. A list = dict(kind 'A'|'O', rows, line, round (the n of the marker directly before it, else None), cut)."""
    lines = text.split("\n")
    start, marks, status, done, lists, unknown = None, [], [], None, [], []
    last_mark = None            # (n, line index) of the latest marker not yet claimed by a list
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = HB_START.search(ln)
        if m:
            start = dict(pid=int(m.group(1)), ppid=int(m.group(2)), period=int(m.group(3)), rounds=int(m.group(4)), ps_timeout=int(m.group(5)), line=i)
            i += 1
            continue
        m = HB_MARK.search(ln)
        if m:
            marks.append(dict(n=int(m.group(1)), pid=int(m.group(2)), ppid=int(m.group(3)), up=int(m.group(4)), line=i))
            last_mark = (int(m.group(1)), i)
            i += 1
            continue
        m = HB_PS.search(ln)
        if m:
            status.append(dict(n=int(m.group(1)), ps_pid=int(m.group(2)), status=int(m.group(3)), ms=int(m.group(4)), timeout_killed=bool(m.group(5)), line=i))
            last_mark = None
            i += 1
            continue
        m = HB_DONE.search(ln)
        if m:
            done = dict(rounds=int(m.group(1)), line=i)
            i += 1
            continue
        if HB_ANY.search(ln):
            unknown.append(ln)
            i += 1
            continue
        kind = "A" if HEAD_A.match(ln) else "O" if HEAD_O.match(ln) else None
        if kind:
            rows, j = [], i + 1
            while j < len(lines):
                if HEAD_A.match(lines[j]) or HEAD_O.match(lines[j]):
                    break
                if kind == "A":
                    r = A89.PS_ROW.match(lines[j])
                    if not r:
                        break
                    rows.append(dict(pid=int(r.group(1)), tty=r.group(2), time=r.group(3), cmd=r.group(4)))
                else:
                    r = ROW_O.match(lines[j])
                    if not r or HB_ANY.search(lines[j]):
                        break
                    rows.append(dict(pid=int(r.group(1)), ppid=int(r.group(2)), stat=r.group(3), cmd=r.group(4)))
                j += 1
            k = j
            while k < len(lines) and lines[k] == "":
                k += 1
            nxt = lines[k] if k < len(lines) else None
            # a list is cut when the text or a hole marker follows it directly; an hb status line or an hb marker after it means it was printed whole
            lists.append(dict(kind=kind, rows=rows, line=i, round=last_mark[0] if last_mark and i - last_mark[1] <= 3 else None,
                              cut=nxt is None or bool(HOLE.match(nxt))))
            i = j
            continue
        i += 1
    return dict(start=start, marks=marks, ps_status=status, done=done, lists=lists, unknown_hb=unknown)


def program_in_list(program, rows):
    """A job's program (full path) against a list's rows: the default format shows the command (the first word may be a path or a name), the -o format shows comm."""
    base = program.rsplit("/", 1)[-1]
    for r in rows:
        first = r["cmd"].split(" ")[0]
        if first == program or first.rsplit("/", 1)[-1] == base:
            return True
    return False


def analyze_text(text, jobs, hole_bytes=0, gap_bytes=0):
    p = parse(text)
    launchd_lines, launchd_labels = A89.read_launchd(text)
    facts = dict(hole_bytes=hole_bytes, gap_bytes=gap_bytes, start=p["start"], marks=p["marks"], ps_status=p["ps_status"], done=p["done"], unknown_hb_lines=p["unknown_hb"],
                 lists=[dict(kind=x["kind"], round=x["round"], rows=len(x["rows"]), cut=x["cut"], line=x["line"]) for x in p["lists"]],
                 launchd_console_lines=launchd_lines, launchd_labels=sorted(launchd_labels), table=[])
    hb_lines = (1 if p["start"] else 0) + len(p["marks"]) + len(p["ps_status"]) + (1 if p["done"] else 0) + len(p["unknown_hb"])
    complete = [x for x in p["lists"] if x["rows"] and x["round"] is not None]
    facts["lists_after_hb_marker"] = len(complete)
    facts["lists_not_from_hb"] = len([x for x in p["lists"] if x["round"] is None])
    facts["console_after_logd"] = None
    if complete:
        row = 5
        last = complete[-1]
        names = [r["cmd"] for r in last["rows"]]
        facts["last_list"] = dict(round=last["round"], kind=last["kind"], cut=last["cut"], processes=names, pids=[r["pid"] for r in last["rows"]])
        facts["pid1_in_last_list"] = any(r["pid"] == 1 for r in last["rows"])
        if last["kind"] == "O":
            facts["states_in_last_list"] = {}
            for r in last["rows"]:
                s = r["stat"][:1]
                facts["states_in_last_list"][s] = facts["states_in_last_list"].get(s, 0) + 1
            facts["zombies_in_last_list"] = [r["pid"] for r in last["rows"] if r["stat"].startswith("Z")]
        # hb's first rounds run before launchd exists (it is started from rc), so a list proves "the console works after launchd/logd started" only when logd is in it
        facts["rounds_with_logd"] = [x["round"] for x in complete if program_in_list(LOGD_PROGRAM, x["rows"])]
        facts["console_after_logd"] = bool(facts["rounds_with_logd"])
        facts["pid1_commands"] = sorted({next(r["cmd"].split(" ")[0] for r in x["rows"] if r["pid"] == 1) for x in complete if any(r["pid"] == 1 for r in x["rows"])})
        first = complete[0]
        facts["max_pid_first_list"] = max(r["pid"] for r in first["rows"])
        facts["max_pid_last_list"] = max(r["pid"] for r in last["rows"])
        facts["table"] = [dict(label=j["label"], program=j["program"], self_start=j["self_start"], in_last_list=program_in_list(j["program"], last["rows"]))
                          for j in jobs if j["program"]]
        alive_self = [t["label"] for t in facts["table"] if t["self_start"] and t["in_last_list"] and not t["label"] == A89.HEARTBEAT]
        facts["self_starting_jobs_in_last_list"] = alive_self
        reason = "%d ps list(s) after hb round markers (rounds %s); the last (round %d, %s format, %d processes%s) names: %s; self-starting Apple jobs of the table in it: %s" % (
            len(complete), [x["round"] for x in complete], last["round"], last["kind"], len(last["rows"]), ", cut at its end" if last["cut"] else "",
            ", ".join(names) or "(none)", ", ".join(alive_self) or "none")
        reason += "; lists that name logd (printed after launchd started it): rounds %s" % (facts["rounds_with_logd"] or "none, so every list may predate launchd")
    elif p["marks"]:
        row, reason = 3, "%d hb round marker(s) (n=%s), %d ps status line(s), no recognisable ps list after a marker" % (len(p["marks"]), [m["n"] for m in p["marks"]], len(p["ps_status"]))
    elif p["start"]:
        row, reason = 2, "the hb start line (pid %d, ppid %d) is in the text, no round marker" % (p["start"]["pid"], p["start"]["ppid"])
    else:
        row, reason = 1, "no `SWEET hb:` line in the kernel text%s" % (" (%d unrecognised hb line(s))" % hb_lines if hb_lines else "")
    return dict(row=row, name=ROWS[row], reason=reason, facts=facts)


def select_dump(arch):
    finals = [d for d in arch["dumps"] if d["why"] == 2 and d["begin"]["len"] > 0]
    return max(finals, key=lambda x: len(x["bytes"])) if finals else None


def analyze(archive, jobs_dir):
    jobs = A89.read_jobs(jobs_dir)
    arch = R2.read_archive2(archive)
    d = select_dump(arch)
    if d is None:
        reason = "no why=2 kernel-log dump with text in the archive"
        if arch["unreadable"]:
            reason += "; %d group(s) of records without a begin could not be inferred: %s" % (len(arch["unreadable"]), "; ".join(u["reason"] for u in arch["unreadable"]))
        return dict(row=0, name=ROWS[0], reason=reason, facts=dict(boots=len(arch["boots"]), dumps=len(arch["dumps"]), unreadable=arch["unreadable"]))
    r = analyze_text(d["text"], jobs, hole_bytes=d["hole_bytes"], gap_bytes=d["begin"]["gap"])
    r["dump"] = dict(boots=[b[:6] for b in d["boots"]], records=len(d["bytes"]), closed=d["closed"], holes=d["holes"], conflicts=d["conflicts"], problems=d["problems"],
                     begin=d["begin"], begin_inferred=d["begin_inferred"])
    r["facts"]["unreadable"] = arch["unreadable"]
    if d["begin_inferred"]:
        r["reason"] += "; the dump's begin record was lost and its geometry was inferred (NAT-097 rules)"
    if d["conflicts"]:
        r["reason"] += "; WARNING: %d offsets have different bytes in different boots" % len(d["conflicts"])
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--jobs-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit("--out exists: %s" % a.out)
    r = analyze(a.archive, a.jobs_dir)
    a.out.write_text(json.dumps(r, indent=1, default=str) + "\n")
    print("row H%d %s: %s" % (r["row"], r["name"], r["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
