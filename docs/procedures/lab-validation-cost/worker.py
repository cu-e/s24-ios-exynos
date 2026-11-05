#!/usr/bin/env python3
"""Fresh-process read-only actual-registry profile or owned output publication."""
import argparse
import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import resource
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["profile", "outputs"])
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location("measured_lab", args.module)
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    raw = args.snapshot.read_bytes()
    state = json.loads(raw)
    report = {"snapshot_sha256": hashlib.sha256(raw).hexdigest(), "mode": args.mode,
              "module_sha256": hashlib.sha256(args.module.read_bytes()).hexdigest(), "outcome": "fail"}
    if args.mode == "profile":
        before = json.dumps(state, sort_keys=True)
        profiler = cProfile.Profile()
        started = time.monotonic()
        profiler.enable()
        result = lab.validate(args.root, state)
        profiler.disable()
        report["seconds"] = time.monotonic() - started
        report["returned_full_unchanged_state"] = result == state and before == json.dumps(result, sort_keys=True)
        report["result_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        profiler.dump_stats(args.out / "profile.pstats")
        stats = pstats.Stats(profiler)
        with (args.out / "profile.txt").open("w") as stream:
            stats.stream = stream
            stats.sort_stats("cumulative").print_stats(30)
        report["calls"] = {name: sum(data[1] for (_, _, function), data in stats.stats.items() if function == name)
                           for name in ["within", "_within_resolved", "resolve", "is_file", "<built-in method posix.lstat>", "evidence", "evidence_hash"]}
    else:
        # All writes are under a new owned fixture, never args.root / MAIN.
        fixture = args.out / "fixture"
        (fixture / "state").mkdir(parents=True)
        (fixture / "state/lab.json").write_bytes(raw)
        lab.now = lambda: state["updated_at"]
        lab.publish_views(fixture, state)
        lab.check_views(fixture)
        report["generated"] = {str(p.relative_to(fixture)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(fixture.rglob("*")) if p.is_file() and p.name != ".lab.lock"}
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    report["current_image_proc_status"] = {name: status[name].strip() for name in ["VmRSS", "VmHWM"]}
    report["rusage_ru_maxrss_KiB_may_include_inherited_peak"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["outcome"] = "pass"
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
