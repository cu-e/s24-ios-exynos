#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-110 archive analyzer for `loader-diag-xnu-sc2-md1` (Stage C2 + hb + quiet launchd).

Extends NAT-108's `analyze_nat108.py` with three fixes identified during NAT-109 host diagnosis:
  1. Matches truncated BSD `ps -A` `SpringBoard` process names (`SpringBoa`, `SpringBoar`,
     `SpringBoard`, exact or basename prefix of length >= 8);
  2. Counts Apple `launchd` `service spawned with pid <N>` lines alongside `xpcproxy spawned
     with pid <N>` when spawning without `xpcproxy`;
  3. Supports quiet `launchd` (`etc/quiet`: `launchd_console_lines == 0`) across `stage-c`,
     `stage-b`, `hb`, and `chain` without masking `SpringBoard`, `backboardd`, or framebuffer swaps,
     recording `facts["etc_quiet_active"]`.
"""
import argparse
import contextlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent

IMAGE_110 = "loader-diag-xnu-sc2-md1"
SPAWNED_110 = re.compile(r"^(?:xpcproxy|service) spawned with pid (\d+)$")
MODE_PREFIX = {"stage-c": "C", "stage-b": "B", "hb": "H", "stage-a": "A"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A108 = _load("nat110_analyze108", PROC / "nat-108" / "analyze_nat108.py")
TAIL_RETURN_110 = A108.TAIL_RETURN_108


def _row_is_springboard(row):
    """True when a parsed `ps -A` row executes `SpringBoard`, including truncated `SpringBoa*`."""
    words = (row.get("cmd") or "").split()
    if not words:
        return False
    base = words[0].split("/")[-1]
    return len(base) >= 8 and "SpringBoard".startswith(base)


@contextlib.contextmanager
def patched_analyzers():
    """Temporarily apply Stage C2 `ps -A` and `launchd` spawn matchers to NAT-108's analyzers."""
    saved_sb = A108._row_is_springboard
    saved_spawned = A108.A89.SPAWNED
    A108._row_is_springboard = _row_is_springboard
    A108.A89.SPAWNED = SPAWNED_110
    try:
        yield
    finally:
        A108._row_is_springboard = saved_sb
        A108.A89.SPAWNED = saved_spawned


def _annotate_quiet(res):
    """Record `etc_quiet_active` on Stage C facts when `launchd_console_lines` was measured."""
    facts = res.get("facts")
    if isinstance(facts, dict) and "launchd_console_lines" in facts:
        facts["etc_quiet_active"] = facts["launchd_console_lines"] == 0
    return res


def analyze_stage_c_text(text, jobs, hole_bytes=0, gap_bytes=0):
    """Classify decoded kernel-log text on the Stage C0-C7 ladder."""
    with patched_analyzers():
        res = A108.analyze_stage_c_text(text, jobs, hole_bytes=hole_bytes, gap_bytes=gap_bytes)
    return _annotate_quiet(res)


def analyze_stage_c(archive, jobs_dir):
    """Evaluate a collector archive on the Stage C0-C7 ladder."""
    with patched_analyzers():
        res = A108.analyze_stage_c(archive, jobs_dir)
    return _annotate_quiet(res)


def analyze_stage_b(archive, jobs_dir):
    """Evaluate a collector archive on the Stage B0-B6 ladder."""
    with patched_analyzers():
        return A108.analyze_stage_b(archive, jobs_dir)


def analyze_hb(archive, jobs_dir):
    """Evaluate heartbeat `ps -A` cadence on the archive."""
    with patched_analyzers():
        return A108.analyze_hb(archive, jobs_dir)


def analyze_stage_a(archive, jobs_dir):
    """Evaluate Stage A launchd/ps rows on the archive (reports `A8` when `etc/quiet` zeroes launchd)."""
    with patched_analyzers():
        return A108.analyze_stage_a(archive, jobs_dir)


def analyze_chain(
    archive,
    events,
    report,
    delivery,
    root,
    size,
    sha256,
    image=IMAGE_110,
    out=None,
    log_out=None,
    allow_synthetic=False,
):
    """Run the full NAT-110 post-session chain analysis (events + delivery + Stage C/B/hb/A)."""
    with patched_analyzers():
        res = A108.analyze_chain(
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
    if isinstance(res.get("stage_c"), dict):
        _annotate_quiet(res["stage_c"])
    return res


def main(argv=None):
    """CLI entrypoint supporting `--mode {stage-c,stage-b,hb,stage-a,chain}`."""
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
    p.add_argument("--image", default=IMAGE_110)
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
    handlers = {
        "stage-c": analyze_stage_c,
        "stage-b": analyze_stage_b,
        "hb": analyze_hb,
        "stage-a": analyze_stage_a,
    }
    res = handlers[a.mode](a.archive, a.jobs_dir)
    if a.out is not None:
        a.out.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print("row %s%d %s: %s" % (MODE_PREFIX[a.mode], res["row"], res["name"], res["reason"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
