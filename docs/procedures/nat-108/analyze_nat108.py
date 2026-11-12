#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-108 analyser: `--mode stage-c` (C0-C7 ladder) plus `stage-b`, `hb`, `stage-a`, and `chain`
under NAT-108's 512 KiB return dump cap (`TAIL_MAX[2] = 524288`, `HEAD_MAX[2] = 8192`).

Reads collector archives only; never opens a device or modifies upstream analyser files.
Stage C rows (highest observed milestone first; panic / init exit always recorded in facts):
  C7 panel-pixels-changed             SpringBoard spawned/alive and MiniIOMobileFramebuffer reports >0 pixels changed
  C6 fb-swaps-no-diff                 SpringBoard alive in last ps list and MiniIOMobileFramebuffer swaps seen, no positive diff
  C5 springboard-alive                SpringBoard present and non-zombie in the last ps list (no swaps yet)
  C4 springboard-exited               com.apple.SpringBoard spawned or seen in earlier ps, exited / not alive
  C3 backboardd-alive-no-springboard  backboardd alive in last ps list, com.apple.SpringBoard never spawned
  C2 inject-configured-no-backboardd  init library insertion or launchd seen, neither backboardd nor SpringBoard spawned
  C1 stage-c-blocked-early            why=2 text present without inject or launchd lines
  C0 no-kernel-text                   no why=2 kernel-log dump with len > 0 in archive
"""
import argparse
import contextlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
TAIL_RETURN_108 = 524288
IMAGE_108 = "loader-diag-xnu-sc1-md1"
SPRINGBOARD_LABEL = "com.apple.SpringBoard"
SPRINGBOARD_PROGRAM = "/System/Library/CoreServices/SpringBoard.app/SpringBoard"
LSD_LABEL = "com.apple.lsd"

C_ROWS = {
    0: "no-kernel-text",
    1: "stage-c-blocked-early",
    2: "inject-configured-no-backboardd",
    3: "backboardd-alive-no-springboard",
    4: "springboard-exited",
    5: "springboard-alive",
    6: "fb-swaps-no-diff",
    7: "panel-pixels-changed",
}

CPU_MONITOR_RE = re.compile(r"denied attempt to escape CPU monitor")
FAILED_LOOKUP_RE = re.compile(r"failed lookup: name = ([^,\s]+)")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A106 = _load("nat108_a106", PROC / "nat-106" / "analyze_nat106.py")
A102 = A106.A102
A97 = A106.A97
A89 = A106.A89


@contextlib.contextmanager
def patched_tail():
    """Temporarily set NAT-106's wrapped TAIL_RETURN_106 to NAT-108's 512 KiB (524288 B)."""
    saved = A106.TAIL_RETURN_106
    A106.TAIL_RETURN_106 = TAIL_RETURN_108
    try:
        with A106.patched_tail():
            yield
    finally:
        A106.TAIL_RETURN_106 = saved


def _row_is_springboard(row):
    first = row["cmd"].split(" ")[0]
    return first == SPRINGBOARD_PROGRAM or first.split("/")[-1] == "SpringBoard"


def analyze_stage_c_text(text, jobs, hole_bytes=0, gap_bytes=0):
    """Classify reconstructed why=2 kernel text on the Stage C ladder (rows C1-C7)."""
    stage_b = A106.analyze_stage_b_text(text, jobs, hole_bytes=hole_bytes, gap_bytes=gap_bytes)
    b_facts = stage_b["facts"]
    parsed = A102.parse(text)
    launchd_lines, labels = A89.read_launchd(text)

    sb_label = labels.get(SPRINGBOARD_LABEL) or {"domains": [], "spawns": [], "exits": []}
    lsd_label = labels.get(LSD_LABEL) or {"domains": [], "spawns": [], "exits": []}

    nonempty_lists = [lst for lst in parsed["lists"] if lst["rows"]]
    complete_lists = [lst for lst in nonempty_lists if not lst["cut"]]
    eval_list = complete_lists[-1] if complete_lists else (nonempty_lists[-1] if nonempty_lists else None)

    sb_any_list = [
        dict(round=lst["round"], pids=[r["pid"] for r in lst["rows"] if _row_is_springboard(r)])
        for lst in nonempty_lists
        if any(_row_is_springboard(r) for r in lst["rows"])
    ]
    sb_last_rows = [r for r in (eval_list["rows"] if eval_list else []) if _row_is_springboard(r)]
    sb_alive = any(A106._row_alive(r) for r in sb_last_rows)
    sb_in_jobs = any(j["label"] == SPRINGBOARD_LABEL for j in jobs)

    fb_swaps = b_facts["fb_swaps"]
    fb_pixel_diffs = b_facts["fb_pixel_diffs"]
    pos_diffs = [d for d in fb_pixel_diffs if d["pixels"] > 0]
    hakios_lines = b_facts["hakios_lines"]
    sb_hakios = [l for l in hakios_lines if any(k in l.lower() for k in ("springboard", "activation", "setup", "unlock", "poster", "vibrancy", "snapshot", "buddy"))]

    spawns = sb_label["spawns"]
    exits = sb_label["exits"]
    sb_seen = bool(spawns or sb_any_list or exits or sb_hakios)
    bb_alive = stage_b["row"] >= 4

    if pos_diffs and sb_seen:
        row = 7
        reason = "%d pixel-diff report(s) > 0 on panel (max %d px/frame, %d swap(s)); SpringBoard %s" % (
            len(pos_diffs),
            max(d["pixels"] for d in pos_diffs),
            len(fb_swaps),
            "alive" if sb_alive else "seen",
        )
    elif sb_alive and fb_swaps:
        row = 6
        reason = "SpringBoard alive in last %s ps list with %d swap(s), no positive pixel-diff line yet" % (
            "trailing" if eval_list["cut"] else "complete",
            len(fb_swaps),
        )
    elif sb_alive:
        row = 5
        reason = "SpringBoard alive in last %s ps list (%d hakios line(s)), no framebuffer swap yet" % (
            "trailing" if eval_list["cut"] else "complete",
            len(hakios_lines),
        )
    elif sb_seen:
        row = 4
        first_exit = exits[0][1] if exits else "absent/zombie in last ps list"
        reason = "com.apple.SpringBoard spawned (%d time(s)) but not alive in last ps list (%s)" % (
            len(spawns),
            first_exit,
        )
    elif bb_alive:
        row = 3
        reason = "backboardd alive / Stage B=%s (swaps=%d), com.apple.SpringBoard never seen" % (
            stage_b["name"],
            len(fb_swaps),
        )
    elif b_facts["inject_lines"] or launchd_lines > 0:
        row = 2
        reason = "inject (%d line(s)) / launchd (%d line(s)) observed, neither backboardd nor SpringBoard spawned" % (
            len(b_facts["inject_lines"]),
            launchd_lines,
        )
    else:
        row = 1
        reason = "why=2 kernel text present without init library insertion or launchd lines"

    if b_facts["panic"]:
        reason += "; kernel panic: %s" % b_facts["panic"][0]
    if b_facts["init_exit"]:
        reason += "; %s" % b_facts["init_exit"][0]
    if hole_bytes or gap_bytes:
        reason += " (hole=%d, gap=%d)" % (hole_bytes, gap_bytes)

    failed_lookups = Counter(FAILED_LOOKUP_RE.findall(text))
    facts = dict(
        b_facts,
        stage_b_row=stage_b["row"],
        stage_b_name=stage_b["name"],
        springboard_in_jobs=sb_in_jobs,
        springboard_domains=sb_label["domains"],
        springboard_spawns=[dict(clock=c, pid=p) for c, p in spawns],
        springboard_exits=[dict(clock=c, text=t) for c, t in exits],
        springboard_lists=sb_any_list,
        springboard_last_list_rows=sb_last_rows,
        springboard_alive_in_last_list=sb_alive,
        springboard_hakios_lines=sb_hakios,
        lsd_spawns=[dict(clock=c, pid=p) for c, p in lsd_label["spawns"]],
        lsd_cpu_monitor_denials=len(CPU_MONITOR_RE.findall(text)),
        top_failed_lookups=failed_lookups.most_common(15),
    )
    return dict(row=row, name=C_ROWS[row], reason=reason, facts=facts)


def analyze_stage_c(archive, jobs_dir):
    """Evaluate a collector archive on the Stage C ladder (rows C0-C7) under TAIL_RETURN=524288."""
    jobs = A89.read_jobs(jobs_dir)
    with patched_tail():
        arch = A97.R2.read_archive2(archive)
    finals = [d for d in arch["dumps"] if d["why"] == 2 and d["begin"]["len"] > 0]
    if not finals:
        reason = "no why=2 kernel-log dump with text in the archive"
        if arch["unreadable"]:
            reason += "; %d unreadable group(s)" % len(arch["unreadable"])
        return dict(
            row=0,
            name=C_ROWS[0],
            reason=reason,
            facts=dict(boots=len(arch["boots"]), dumps=len(arch["dumps"]), unreadable=arch["unreadable"]),
        )
    d = max(finals, key=lambda x: len(x["bytes"]))
    r = analyze_stage_c_text(d["text"], jobs, hole_bytes=d["hole_bytes"], gap_bytes=d["begin"]["gap"])
    r["dump"] = dict(
        boots=[b[:6] for b in d["boots"]],
        records=len(d["bytes"]),
        closed=d["closed"],
        holes=d["holes"],
        conflicts=d["conflicts"],
        problems=d["problems"],
        begin=d["begin"],
        begin_inferred=d["begin_inferred"],
    )
    r["facts"]["unreadable"] = arch["unreadable"]
    if d["begin_inferred"]:
        r["reason"] += "; dump begin inferred"
    if d["conflicts"]:
        r["reason"] += "; WARNING: %d boot conflict offset(s)" % len(d["conflicts"])
    return r


def analyze_stage_b(archive, jobs_dir):
    with patched_tail():
        return A106.analyze_stage_b(archive, jobs_dir)


def analyze_hb(archive, jobs_dir):
    with patched_tail():
        return A106.analyze_hb(archive, jobs_dir)


def analyze_stage_a(archive, jobs_dir):
    with patched_tail():
        return A106.analyze_stage_a(archive, jobs_dir)


def analyze_chain(archive, events, report, delivery, root, size, sha256, image=IMAGE_108, out=None, log_out=None, allow_synthetic=False):
    with patched_tail():
        return A106.analyze_chain(
            archive, events, report, delivery, root, size, sha256,
            image=image, out=out, log_out=log_out, allow_synthetic=allow_synthetic,
        )


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("stage-c", "stage-b", "hb", "stage-a", "chain"), default="stage-c")
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--jobs-dir", type=Path)
    p.add_argument("--events", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--delivery", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--size", type=int)
    p.add_argument("--sha256")
    p.add_argument("--image", default=IMAGE_108)
    p.add_argument("--log-out", type=Path)
    p.add_argument("--allow-synthetic", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if a.mode == "chain":
        for req in ("events", "report", "delivery", "root", "size", "sha256"):
            if getattr(a, req) is None:
                p.error("--mode chain requires --%s" % req)
        res = analyze_chain(
            a.archive,
            a.events,
            a.report,
            a.delivery,
            a.root,
            a.size,
            a.sha256,
            image=a.image,
            out=a.out,
            log_out=a.log_out,
            allow_synthetic=a.allow_synthetic,
        )
        print(json.dumps({k: v for k, v in res.items() if k != "_exit_code"}, indent=1))
        return res["_exit_code"]
    if a.jobs_dir is None:
        p.error("--mode %s requires --jobs-dir" % a.mode)
    dispatch = {
        "stage-c": (analyze_stage_c, "C"),
        "stage-b": (analyze_stage_b, "B"),
        "hb": (analyze_hb, "H"),
        "stage-a": (analyze_stage_a, "A"),
    }
    fn, letter = dispatch[a.mode]
    res = fn(a.archive, a.jobs_dir)
    prefix = "row %s%d" % (letter, res["row"])
    text = json.dumps(res, indent=1, default=str) + "\n"
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    print("%s %s: %s" % (prefix, res["name"], res["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
