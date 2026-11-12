#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-104 analyser: wraps analyze_nat087.py (chain), analyze_nat097.py (Stage A), and analyze_nat102.py (heartbeat H0-H5)
under NAT-104's return dump cap (`TAIL_MAX[2] = 262144`, `HEAD_MAX[2] = 8192`).

Reads collector archives only; never opens a device or modifies upstream analyser files."""
import argparse
import contextlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
TAIL_RETURN_104 = 262144
IMAGE_104 = "loader-diag-xnu-hb2-md1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A87 = _load("nat104_a87", PROC / "nat-087" / "analyze_nat087.py")
A97 = _load("nat104_a97", PROC / "nat-097" / "analyze_nat097.py")
A102 = _load("nat104_a102", PROC / "nat-102" / "analyze_nat102.py")


@contextlib.contextmanager
def patched_tail():
    """Temporarily raise TAIL_MAX[2] across all imported analyze_nat062 instances and restore cleanly on exit."""
    modules = [A87.A65.A62, A97.R2.A62, A102.R2.A62]
    saved = [(m, m.TAIL_MAX[2]) for m in modules]
    try:
        for m, _ in saved:
            m.TAIL_MAX[2] = TAIL_RETURN_104
        yield
    finally:
        for m, old in saved:
            m.TAIL_MAX[2] = old


def analyze_hb(archive, jobs_dir):
    with patched_tail():
        return A102.analyze(archive, jobs_dir)


def analyze_stage_a(archive, jobs_dir):
    with patched_tail():
        return A97.analyze(archive, jobs_dir)


def analyze_chain(archive, events, report, delivery, root, size, sha256, image=IMAGE_104, out=None, log_out=None, allow_synthetic=False):
    import io
    with patched_tail():
        saved_argv = sys.argv
        try:
            argv = [
                str(PROC / "nat-087" / "analyze_nat087.py"),
                "--archive", str(archive),
                "--events", str(events),
                "--report", str(report),
                "--delivery", str(delivery),
                "--root", str(root),
                "--size", str(size),
                "--sha256", str(sha256),
                "--image", image,
            ]
            if out is not None:
                argv += ["--out", str(out)]
            if log_out is not None:
                argv += ["--log-out", str(log_out)]
            if allow_synthetic:
                argv.append("--allow-synthetic")
            sys.argv = argv
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = A87.main()
            raw = buf.getvalue().strip()
            res = json.loads(raw) if raw else {}
            res["_exit_code"] = rc
            return res
        finally:
            sys.argv = saved_argv


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("hb", "stage-a", "chain"), default="hb")
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--jobs-dir", type=Path)
    p.add_argument("--events", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--delivery", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--size", type=int)
    p.add_argument("--sha256")
    p.add_argument("--image", default=IMAGE_104)
    p.add_argument("--log-out", type=Path)
    p.add_argument("--allow-synthetic", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if a.mode == "chain":
        for req in ("events", "report", "delivery", "root", "size", "sha256"):
            if getattr(a, req) is None:
                p.error("--mode chain requires --%s" % req)
        res = analyze_chain(a.archive, a.events, a.report, a.delivery, a.root, a.size, a.sha256,
                            image=a.image, out=a.out, log_out=a.log_out, allow_synthetic=a.allow_synthetic)
        print(json.dumps({k: v for k, v in res.items() if k != "_exit_code"}, indent=1))
        return res["_exit_code"]
    if a.jobs_dir is None:
        p.error("--mode %s requires --jobs-dir" % a.mode)
    res = analyze_hb(a.archive, a.jobs_dir) if a.mode == "hb" else analyze_stage_a(a.archive, a.jobs_dir)
    text = json.dumps(res, indent=1) + "\n"
    if a.out is not None:
        a.out.write_text(text)
    if a.mode == "hb":
        hb_lines = (res.get("facts") or {}).get("marks") or []
        print("row H%d %s: %s (hb_marks=%d, lists=%d, gap=%s, hole=%s)" % (
            res["row"], res["name"], res["reason"], len(hb_lines),
            len((res.get("facts") or {}).get("lists") or []),
            (res.get("facts") or {}).get("gap_bytes"),
            (res.get("facts") or {}).get("hole_bytes"),
        ))
    else:
        print("row A%d %s: %s" % (res["row"], res["name"], res["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
