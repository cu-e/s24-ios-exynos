#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-089: analyser for the next native run, Stage A (Apple's daemons under restore-mode launchd). Pre-registered BEFORE any run of that image; host-only.

Question of the run: with launchd in restore mode (NAT-088: 20 of 23 boot tasks skipped, the job respawned) and the donor's job set minus wifid, backboardd and SpringBoard
(19 Apple plists) plus the NAT-085 `ps -A` heartbeat, which of Apple's daemons are running at the last `ps -A` list of the returned text, which died, and with what reason?
Observables (all from the returned kernel-log dump, read by kl_reader.py with its holes marked): launchd's boot-task lines (kernel `[System Event]` form and console form),
launchd's per-label lines (`xpcproxy spawned with pid`, `exited ...`), the heartbeat's `ps -A` lists, panic and PID 1 exit lines.

Rows (first that applies, top to bottom of the evaluation order; the number is the name, not the order):
  A8  not evaluated   no why=2 dump, no launchd line, or no complete `ps -A` list in the text, or a hole/gap that makes a negative claim unsupported
  A7  launchd stopped a PID 1 exit line (initproc exited / pid 1 exited)
  A6  kernel panic    a `panic(cpu N caller ...)` line
  A5  control failed  boot-task lines were read and the tasks that ran are not exactly the three of NAT-088 (commit-boot-mode, init-with-data-volume, restore-datapartition)
  A4  no daemon spawned   launchd lines read, a complete last ps list and no `xpcproxy spawned` line for any Apple label, and the text has no hole
  A3  all spawned died    at least one Apple label spawned and none of the 19 programs is in the last complete ps list
  A2  some alive          some, not all, of the SELF-STARTING jobs (RunAtLoad true or KeepAlive true in their plist, and not disabled by a `Disabled` key: syslogd's stock plist says `Disabled: true`) are in the last complete ps list
  A1  base daemons alive  every self-starting job is in the last complete ps list, and no stop (A5-A7) applies

The per-label table (spawn count, exits with launchd's wording, alive in the last list) is produced for every row; the decision after the run is made from it: A1 -> Stage B
adds backboardd; A2/A3 -> fix the earliest exit's cause first (launchd's clock orders them); A4 -> the launchd domain (persona type 6, `user/501` domain) before any daemon;
A5-A7 -> that stop first. A pass of this ladder says only that the daemons were running at the last ps list of a window of at most 63 s; it does not say they work.
What it cannot show: anything inside a hole or the announced gap; that a program in the ps list is healthy; anything about display, input, GPU or SpringBoard."""
import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kl_reader  # noqa: E402

ALLOWED_TASKS = ("commit-boot-mode", "init-with-data-volume", "restore-datapartition")
SYSEVENT = re.compile(r"^\[\s*(?P<k>\d+\.\d+)\]: \[System Event\] \[\d+\] \[\w+\] \[Subsystem: launchd\] \[Event: (?P<ev>[^\]]+)\] (?P<what>\S.*?)\s*$", re.M)
TASK_CONSOLE = re.compile(r"\((?P<task>[^()\s]+)\) <Notice>: Doing boot task")
LAUNCHD = re.compile(r"^com\.apple\.xpc\.launchd\|(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) (?:\((?P<dom>system|user/\d+|pid/\d+|gui/\d+|login/\d+)/(?P<label>[^\s()\[\]]+)"
                     r"(?: \[(?P<pid>\d+)\])?\) )?<(?P<lvl>\w+)>: (?P<msg>.*?)\s*$", re.M)
SPAWNED = re.compile(r"^xpcproxy spawned with pid (\d+)$")
PS_HEADER = re.compile(r"^[ \t]*PID[ \t]+TTY[ \t]+TIME[ \t]+CMD[ \t]*$")
PS_ROW = re.compile(r"^[ \t]*(\d+)[ \t]+(\S+)[ \t]+([\d:.]+)[ \t]+(.+?)[ \t]*$")
PANIC = re.compile(r"^panic\(cpu \d+ caller 0x[0-9a-f]+\): (.*?)\r?$", re.M)
INIT_EXIT = re.compile(r"initproc (exited|failed to start) -- no exit reason available -- \(signal (\d+), exit status (\d+)")
INIT_EXIT_PRINTF = re.compile(r"pid (\d+) exited -- no exit reason available -- \(signal (\d+), exit (\d+)\)")
HOLE_LINE = re.compile(r"^\[\.\.\. \d+ bytes (lost in transport|of the log were not sent) \.\.\.\]$")
HEARTBEAT = "com.nat085.ps"
ROWS = {1: "base-daemons-alive", 2: "some-daemons-alive", 3: "all-spawned-daemons-died", 4: "no-daemon-spawned", 5: "boot-task-control-failed",
        6: "kernel-panic", 7: "launchd-stopped", 8: "not-evaluated"}


def read_jobs(directory):
    """The labels of a built LaunchDaemons directory: [dict(label, program, self_start, heartbeat, file, disabled, limit_session)], read from the plists themselves.
    self_start: RunAtLoad or KeepAlive is true AND the job is not disabled (a `Disabled` key that is true or a feature-flag conditional keeps launchd from starting it by itself: com.apple.syslogd
    is `Disabled: true` in the stock plist). `disabled` and `limit_session` are the raw plist values (None when absent): LimitLoadToSessionType decides which launchd domain may load the job."""
    out = []
    for f in sorted(Path(directory).glob("*.plist")):
        d = plistlib.loads(f.read_bytes())
        prog = d.get("Program") or (d.get("ProgramArguments") or [None])[0]
        out.append(dict(label=d["Label"], program=prog, file=f.name, heartbeat=d["Label"] == HEARTBEAT, disabled=d.get("Disabled"), limit_session=d.get("LimitLoadToSessionType"),
                        self_start=bool((d.get("RunAtLoad") is True or d.get("KeepAlive") is True) and d.get("Disabled", False) is False)))
    return out


def launchd_clock(ts):
    """'1970-01-01 00:03:44.159344' -> 224.159344 (launchd's clock is seconds since its epoch; only differences are meant)."""
    h, m, s = ts.split(" ")[1].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def read_tasks(text):
    ran, skipped, early = [], [], None
    for m in SYSEVENT.finditer(text):
        what = m["what"]
        if what == "Doing boot task" and m["ev"] not in ran:
            ran.append(m["ev"])
        elif what == "Skipping boot-task" and m["ev"] not in skipped:
            skipped.append(m["ev"])
        elif what.startswith("Early boot complete") and early is None:
            early = float(m["k"])
    for m in TASK_CONSOLE.finditer(text):
        if m["task"] not in ran:
            ran.append(m["task"])
    return dict(ran=ran, skipped=skipped, early_boot_complete_kernel_s=early)


def read_launchd(text):
    """-> (lines, labels): the number of launchd lines and {label: dict(domains, spawns=[(clock, pid)], exits=[(clock, text)], other=n)}."""
    labels, n = {}, 0
    for m in LAUNCHD.finditer(text):
        n += 1
        if not m["label"]:
            continue
        e = labels.setdefault(m["label"], dict(domains=[], spawns=[], exits=[], other=0))
        if m["dom"] not in e["domains"]:
            e["domains"].append(m["dom"])
        msg, clock = m["msg"], launchd_clock(m["ts"])
        sp = SPAWNED.match(msg)
        if sp:
            e["spawns"].append((clock, int(sp.group(1))))
        elif msg.startswith("exited") or msg.startswith("Service exited"):
            e["exits"].append((clock, msg))
        else:
            e["other"] += 1
    return n, labels


def read_ps_lists(text):
    """-> [dict(rows=[(pid, tty, time, cmd)], cut=bool)] in text order. A list is a header and the consecutive rows after it; it is `cut` when a hole/gap marker or the end of
    the text follows it directly (rows may be missing from the end)."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if PS_HEADER.match(lines[i]):
            rows, j = [], i + 1
            while j < len(lines):
                m = PS_ROW.match(lines[j])
                if not m or PS_HEADER.match(lines[j]):
                    break
                rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4)))
                j += 1
            k = j
            while k < len(lines) and lines[k] == "":          # a hole marker starts with a newline: skip the empty lines to see what follows
                k += 1
            nxt = lines[k] if k < len(lines) else None
            out.append(dict(rows=rows, cut=nxt is None or bool(HOLE_LINE.match(nxt)), line=i))
            i = j
        else:
            i += 1
    return out


def in_list(program, plist):
    return any(cmd.split(" ")[0] == program for _, _, _, cmd in plist["rows"])


def analyze_text(text, jobs, hole_bytes=0, gap_bytes=0):
    """The pure part: kernel text (with kl_reader's markers) + the jobs of the built LaunchDaemons -> dict(row, name, reason, facts, table)."""
    tasks = read_tasks(text)
    nl, labels = read_launchd(text)
    lists = read_ps_lists(text)
    last = lists[-1] if lists else None
    complete = last is not None and not last["cut"]
    apple = [j for j in jobs if not j["heartbeat"]]
    table = []
    for j in jobs:
        e = labels.get(j["label"], dict(domains=[], spawns=[], exits=[], other=0))
        table.append(dict(label=j["label"], program=j["program"], self_start=j["self_start"], heartbeat=j["heartbeat"], disabled=j.get("disabled"), limit_session=j.get("limit_session"),
                          domains=e["domains"],
                          spawns=len(e["spawns"]), first_spawn_clock=e["spawns"][0][0] if e["spawns"] else None,
                          exits=[dict(clock=c, text=t) for c, t in e["exits"]], alive_in_last_list=in_list(j["program"], last) if last else None))
    alive = [t["label"] for t in table if not t["heartbeat"] and t["alive_in_last_list"]]
    self_start = [j["label"] for j in apple if j["self_start"]]
    spawned = [t["label"] for t in table if not t["heartbeat"] and t["spawns"]]
    ie, ip, pn = INIT_EXIT.search(text), INIT_EXIT_PRINTF.search(text), PANIC.search(text)
    facts = dict(boot_tasks=tasks, launchd_lines=nl, ps_lists=len(lists), last_list_rows=len(last["rows"]) if last else None, last_list_cut=last["cut"] if last else None,
                 alive=alive, self_start=self_start, spawned_apple=spawned, hole_bytes=hole_bytes, gap_bytes=gap_bytes,
                 panic=pn.group(1) if pn else None,
                 pid1_exit=dict(how=ie.group(1), signal=int(ie.group(2)), status=int(ie.group(3))) if ie else dict(pid=int(ip.group(1)), signal=int(ip.group(2)), status=int(ip.group(3))) if ip else None)

    def done(row, reason):
        return dict(row=row, name=ROWS[row], reason=reason, facts=facts, table=table)

    if nl == 0:
        return done(8, "no launchd line in the returned text")
    if facts["pid1_exit"]:
        return done(7, "PID 1 exit line: %s" % (facts["pid1_exit"],))
    if pn:
        return done(6, "kernel panic: %s" % pn.group(1))
    if tasks["ran"] and sorted(tasks["ran"]) != sorted(ALLOWED_TASKS):
        return done(5, "boot tasks that ran: %s (NAT-088: exactly %s)" % (tasks["ran"], list(ALLOWED_TASKS)))
    if not complete:
        return done(8, "no complete `ps -A` list in the text (%d lists, last %s): the alive set is not established" % (len(lists), "cut" if last else "absent"))
    if not spawned:
        if hole_bytes or gap_bytes:
            return done(8, "no `xpcproxy spawned` line for an Apple label, but %d bytes are holes and %d are the announced gap: spawning is not excluded" % (hole_bytes, gap_bytes))
        return done(4, "launchd lines read, a complete last ps list, no Apple label spawned")
    if not alive:
        return done(3, "%d Apple label(s) spawned, none of the 19 programs is in the last complete ps list" % len(spawned))
    missing = [s for s in self_start if s not in alive]
    if missing:
        return done(2, "alive %d of %d self-starting jobs; not in the last list: %s" % (len([s for s in self_start if s in alive]), len(self_start), missing))
    return done(1, "all %d self-starting jobs are in the last complete ps list; alive in total: %d" % (len(self_start), len(alive)))


def analyze(archive, jobs_dir):
    jobs = read_jobs(jobs_dir)
    arch = kl_reader.read_archive(archive)
    finals = [d for d in arch["dumps"] if d["why"] == 2 and d["begin"]["len"] > 0]
    if not finals:
        return dict(row=8, name=ROWS[8], reason="no why=2 kernel-log dump with text in the archive", facts=dict(boots=len(arch["boots"]), dumps=len(arch["dumps"])), table=[])
    d = max(finals, key=lambda x: len(x["bytes"]))
    r = analyze_text(d["text"], jobs, hole_bytes=d["hole_bytes"], gap_bytes=d["begin"]["gap"])
    r["dump"] = dict(boots=[b[:6] for b in d["boots"]], records=len(d["bytes"]), closed=d["closed"], holes=d["holes"], conflicts=d["conflicts"], problems=d["problems"],
                     begin=d["begin"])
    if d["conflicts"]:
        r["reason"] += "; WARNING: %d offsets have different bytes in different boots" % len(d["conflicts"])
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--jobs-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    r = analyze(a.archive, a.jobs_dir)
    a.out.write_text(json.dumps(r, indent=1, default=str) + "\n")
    print("row A%d %s: %s" % (r["row"], r["name"], r["reason"]))
    for t in r["table"]:
        print("  %-48s spawns %d alive %s exits %d" % (t["label"], t["spawns"], t["alive_in_last_list"], len(t["exits"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
