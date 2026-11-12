#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-106 analyser: `--mode stage-b` (B0-B6 ladder) plus `hb`, `stage-a`, and `chain`
under NAT-106's 512 KiB return dump cap (`TAIL_MAX[2] = 524288`, `HEAD_MAX[2] = 8192`).

Reads collector archives only; never opens a device or modifies upstream analyser files.
Stage B rows (highest observed milestone first; panic / init exit always recorded in facts):
  B6 panel-pixels-changed            MiniIOMobileFramebuffer reports >0 pixels changed on the panel
  B5 fb-swaps-no-diff                MiniIOMobileFramebuffer swaps seen, no positive pixel-diff line
  B4 backboardd-alive                backboardd present and non-zombie in the last ps list (no swaps yet)
  B3 backboardd-exited               com.apple.backboardd spawned (or seen in earlier ps), exited / not alive
  B2 inject-configured-no-backboardd init library insertion or launchd seen, com.apple.backboardd never spawned
  B1 stage-b-blocked-early           why=2 text present, blocked before inject/launchd (panic, init exit, or early stop)
  B0 no-kernel-text                  no why=2 kernel-log dump with len > 0 in archive
"""
import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
TAIL_RETURN_106 = 524288
IMAGE_106 = "loader-diag-xnu-sb2-md1"
BACKBOARDD_LABEL = "com.apple.backboardd"
BACKBOARDD_PROGRAM = "/usr/libexec/backboardd"

B_ROWS = {
    0: "no-kernel-text",
    1: "stage-b-blocked-early",
    2: "inject-configured-no-backboardd",
    3: "backboardd-exited",
    4: "backboardd-alive",
    5: "fb-swaps-no-diff",
    6: "panel-pixels-changed",
}

INJECT_RE = re.compile(r"init: library insertion:\s*(.+?)\s*$", re.M)
HAKIOS_RE = re.compile(r"hakios:\s*(.+?)\s*$", re.M)
FB_DISPLAY_RE = re.compile(r"MiniIOMobileFramebuffer: display (\d+)x(\d+) on a panel of (\d+)x(\d+) \((\d+) bytes per row\)")
FB_SWAP_RE = re.compile(r"MiniIOMobileFramebuffer: swap (?:#(\d+): surfaces in layers (\S+) now \((\S+) before\)|(\d+) \(#(\d+)\): surfaces ([^,\n]+))")
FB_STATS_RE = re.compile(r"MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\)")
FB_PIXELS_RE = re.compile(r"MiniIOMobileFramebuffer: (\d+) pixels of the panel changed a frame, all within (\d+),(\d+) to (\d+),(\d+)")
FB_NOTIFY_RE = re.compile(r"MiniIOMobileFramebuffer: notification port for type (\d+)")


def _load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A104 = _load("nat106_a104", PROC / "nat-104" / "analyze_nat104.py")
A87 = A104.A87
A97 = A104.A97
A102 = A104.A102
A89 = A97.A89


@contextlib.contextmanager
def patched_tail():
    """Temporarily set NAT-104's wrapped TAIL_RETURN_104 to NAT-106's 512 KiB (524288 B)."""
    saved = A104.TAIL_RETURN_104
    A104.TAIL_RETURN_104 = TAIL_RETURN_106
    try:
        with A104.patched_tail():
            yield
    finally:
        A104.TAIL_RETURN_104 = saved


def _row_is_backboardd(row):
    first = row["cmd"].split(" ")[0]
    return first == BACKBOARDD_PROGRAM or first.split("/")[-1] == "backboardd"


def _row_alive(row):
    return not row.get("stat", "").startswith("Z")


def analyze_stage_b_text(text, jobs, hole_bytes=0, gap_bytes=0):
    """Classify reconstructed why=2 kernel text on the Stage B ladder (rows B1-B6)."""
    parsed = A102.parse(text)
    launchd_lines, labels = A89.read_launchd(text)
    bb_label = labels.get(BACKBOARDD_LABEL) or {"domains": [], "spawns": [], "exits": []}

    inject_lines = [m.group(1) for m in INJECT_RE.finditer(text)]
    hakios_lines = [m.group(1) for m in HAKIOS_RE.finditer(text)]
    panic = [m.group(1) for m in A89.PANIC.finditer(text)]
    init_exit = [
        m.group(0)
        for m in list(A89.INIT_EXIT.finditer(text)) + list(A89.INIT_EXIT_PRINTF.finditer(text))
    ]
    fb_displays = [dict(width=int(m.group(1)), height=int(m.group(2)), panel_w=int(m.group(3)), panel_h=int(m.group(4)), stride=int(m.group(5)))
                   for m in FB_DISPLAY_RE.finditer(text)]
    fb_notify = [int(m.group(1)) for m in FB_NOTIFY_RE.finditer(text)]
    fb_swaps = []
    for m in FB_SWAP_RE.finditer(text):
        if m.group(1) is not None:
            fb_swaps.append(dict(kind="layers", swap_shown=int(m.group(1)), now=m.group(2), before=m.group(3)))
        else:
            fb_swaps.append(dict(kind="swap", swap_id=int(m.group(4)), swap_shown=int(m.group(5)), surfaces=m.group(6).strip()))
    fb_stats = [dict(frames=int(m.group(1)), ms=int(m.group(2)), fps=int(m.group(3))) for m in FB_STATS_RE.finditer(text)]
    fb_pixel_diffs = [
        dict(pixels=int(m.group(1)), left=int(m.group(2)), top=int(m.group(3)), right=int(m.group(4)), bottom=int(m.group(5)))
        for m in FB_PIXELS_RE.finditer(text)
    ]

    nonempty_lists = [lst for lst in parsed["lists"] if lst["rows"]]
    complete_lists = [lst for lst in nonempty_lists if not lst["cut"]]
    eval_list = complete_lists[-1] if complete_lists else (nonempty_lists[-1] if nonempty_lists else None)

    bb_any_list = [
        dict(round=lst["round"], pids=[r["pid"] for r in lst["rows"] if _row_is_backboardd(r)])
        for lst in nonempty_lists
        if any(_row_is_backboardd(r) for r in lst["rows"])
    ]
    bb_last_rows = [r for r in (eval_list["rows"] if eval_list else []) if _row_is_backboardd(r)]
    bb_alive = any(_row_alive(r) for r in bb_last_rows)
    bb_in_jobs = any(j["label"] == BACKBOARDD_LABEL for j in jobs)

    pos_diffs = [d for d in fb_pixel_diffs if d["pixels"] > 0]
    spawns = bb_label["spawns"]
    exits = bb_label["exits"]

    if pos_diffs:
        row = 6
        reason = "%d pixel-diff report(s) > 0 on panel (max %d px/frame across %d swap line(s))" % (
            len(pos_diffs),
            max(d["pixels"] for d in pos_diffs),
            len(fb_swaps),
        )
    elif fb_swaps:
        row = 5
        reason = "%d MiniIOMobileFramebuffer swap line(s) seen, no positive pixel-diff line" % len(fb_swaps)
    elif bb_alive:
        row = 4
        reason = "backboardd alive in last %s ps list (%d hakios line(s)), no framebuffer swap line yet" % (
            "complete" if (eval_list and not eval_list["cut"]) else "trailing",
            len(hakios_lines),
        )
    elif spawns or bb_any_list or exits:
        row = 3
        first_exit = exits[0][1] if exits else "absent/zombie in last ps list"
        reason = "com.apple.backboardd spawned (%d time(s)) but not alive in last ps list (%s)" % (len(spawns), first_exit)
    elif inject_lines or launchd_lines > 0:
        row = 2
        reason = "inject (%d line(s)) / launchd (%d line(s)) observed, no com.apple.backboardd spawn" % (
            len(inject_lines),
            launchd_lines,
        )
    else:
        row = 1
        reason = "why=2 kernel text present without init library insertion or launchd lines"

    if panic:
        reason += "; kernel panic: %s" % panic[0]
    if init_exit:
        reason += "; %s" % init_exit[0]
    if hole_bytes or gap_bytes:
        reason += " (hole=%d, gap=%d)" % (hole_bytes, gap_bytes)

    facts = dict(
        hole_bytes=hole_bytes,
        gap_bytes=gap_bytes,
        backboardd_in_jobs=bb_in_jobs,
        inject_lines=inject_lines,
        hakios_lines=hakios_lines,
        launchd_console_lines=launchd_lines,
        backboardd_domains=bb_label["domains"],
        backboardd_spawns=[dict(clock=c, pid=p) for c, p in spawns],
        backboardd_exits=[dict(clock=c, text=t) for c, t in exits],
        backboardd_lists=bb_any_list,
        backboardd_last_list_rows=bb_last_rows,
        backboardd_alive_in_last_list=bb_alive,
        eval_list_round=eval_list["round"] if eval_list else None,
        eval_list_cut=eval_list["cut"] if eval_list else None,
        ps_lists_total=len(nonempty_lists),
        ps_lists_complete=len(complete_lists),
        fb_displays=fb_displays,
        fb_notify_types=fb_notify,
        fb_swaps=fb_swaps,
        fb_stats=fb_stats,
        fb_pixel_diffs=fb_pixel_diffs,
        panic=panic,
        init_exit=init_exit,
    )
    return dict(row=row, name=B_ROWS[row], reason=reason, facts=facts)


def analyze_stage_b(archive, jobs_dir):
    """Evaluate a collector archive on the Stage B ladder (rows B0-B6) under TAIL_RETURN=524288."""
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
            name=B_ROWS[0],
            reason=reason,
            facts=dict(boots=len(arch["boots"]), dumps=len(arch["dumps"]), unreadable=arch["unreadable"]),
        )
    d = max(finals, key=lambda x: len(x["bytes"]))
    r = analyze_stage_b_text(d["text"], jobs, hole_bytes=d["hole_bytes"], gap_bytes=d["begin"]["gap"])
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


def analyze_hb(archive, jobs_dir):
    with patched_tail():
        return A102.analyze(archive, jobs_dir)


def analyze_stage_a(archive, jobs_dir):
    with patched_tail():
        return A97.analyze(archive, jobs_dir)


def analyze_chain(archive, events, report, delivery, root, size, sha256, image=IMAGE_106, out=None, log_out=None, allow_synthetic=False):
    with patched_tail():
        return A104.analyze_chain(
            archive,
            events,
            report,
            delivery,
            root,
            size,
            sha256,
            image=image,
            out=out,
            log_out=log_out,
            allow_synthetic=allow_synthetic,
        )


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("stage-b", "hb", "stage-a", "chain"), default="stage-b")
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--jobs-dir", type=Path)
    p.add_argument("--events", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--delivery", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--size", type=int)
    p.add_argument("--sha256")
    p.add_argument("--image", default=IMAGE_106)
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
    if a.mode == "stage-b":
        res = analyze_stage_b(a.archive, a.jobs_dir)
        prefix = "row B%d" % res["row"]
    elif a.mode == "hb":
        res = analyze_hb(a.archive, a.jobs_dir)
        prefix = "row H%d" % res["row"]
    else:
        res = analyze_stage_a(a.archive, a.jobs_dir)
        prefix = "row A%d" % res["row"]
    text = json.dumps(res, indent=1, default=str) + "\n"
    if a.out is not None:
        a.out.write_text(text)
    print("%s %s: %s" % (prefix, res["name"], res["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
