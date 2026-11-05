#!/usr/bin/env python3
"""Measure prospective admission only; never launch a subprocess/compiler/guest."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools/build"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--implementation-commit", required=True)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    ledger = json.loads((args.main / "state/lab.json").read_text())
    plan = next(entry for entry in ledger["experiments"] if entry["id"] == "AVFADMIT-001")
    if plan["task"] != "VM-008" or plan["owner"] != "codex-team-avf-kernel-headers-20261105-cd" or plan["status"] != "planned":
        raise ValueError("Require actual planned MAIN AVFADMIT-001 before probe")
    queue_path = args.main / "artifacts/team-coordination/20261106-team/resource-queue.json"
    queue = json.loads(queue_path.read_text())
    limits = queue["limits"]
    if (limits["min_mem_available_bytes"], limits["stable_samples"], limits["sample_interval_seconds"]) != (4 * 1024**3, 3, 1):
        raise ValueError("Current resource queue no longer matches the assigned 4GiB/three/one-second contract")
    policy = {"source": str(queue_path), "source_sha256": sha(queue_path), "limits": limits,
              "meaning": "Read-only policy snapshot only; no heavy/QEMU/resource lease grant"}
    (out / "resource-policy.json").write_text(json.dumps(policy, indent=2) + "\n")
    tool = ROOT / "tools/build/avf_kernel_headers.py"
    spec = importlib.util.spec_from_file_location("prospective_avf_admission", tool)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    original_admission = module.stable_admission
    floor = 4 * 1024**3
    results = []
    report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive", "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "argv": [sys.executable, *sys.argv], "implementation_commit": args.implementation_commit,
              "tool_sha256": sha(tool), "probe_sha256": sha(Path(__file__)), "registered_main_plan": plan, "resource_policy_snapshot": policy,
              "actual_subprocess_started": False, "compiler_headers_iig_matrix_or_guest_run": False, "controls": results}
    class SpawnReached(Exception):
        pass
    try:
        for name, sequence, expected in [("first-low", [floor - 1, floor, floor], False),
                                         ("middle-dip", [floor, floor - 1, floor], False),
                                         ("too-close-monotonic", [floor, floor, floor], False),
                                         ("all-good-boundary", [floor, floor + 64 * 1024**2, floor], True)]:
            values = iter(sequence); clock = {"seconds": 0.0}; sleeps = []; reads = []
            def pause(seconds):
                sleeps.append(seconds); clock["seconds"] += seconds / 2 if name == "too-close-monotonic" else seconds
            def read():
                value = next(values); reads.append(value); return value
            def admission():
                return original_admission(read_available=read, pause=pause,
                    monotonic=lambda: clock["seconds"], timestamp=lambda: "mock+" + str(clock["seconds"]))
            holder = module.Headers.__new__(module.Headers)
            holder.out = out
            holder.env = {"HAKIOS_VERSION_SUFFIX": "admission-only-mock", "GIT_CEILING_DIRECTORIES": str(out), "PATH": "/usr/bin:/bin"}
            holder.report = {"commands": []}
            attempted = []
            def no_spawn(*unused, **settings):
                proof = holder.report["commands"][-1]["admission"]
                if not proof["admitted"] or len(proof["samples"]) != 3:
                    raise AssertionError("Popen reached without three stable admission samples")
                attempted.append(True)
                raise SpawnReached()
            # admitted=False used to exempt metadata/query commands from the
            # old one-point precheck. The prospective pre-spawn guard applies
            # to those commands too; no caller can use that flag as a bypass.
            with patch.object(module, "stable_admission", side_effect=admission), patch.object(module.subprocess, "Popen", side_effect=no_spawn):
                try:
                    holder.run(["mock-never-executed"], "mock-" + name, admitted=False)
                except SpawnReached:
                    if not expected:
                        raise AssertionError("Rejected admission reached Popen")
                except RuntimeError:
                    if expected:
                        raise
            proof = holder.report["commands"][-1]["admission"]
            expected_reads = {"first-low": 1, "middle-dip": 2, "too-close-monotonic": 2, "all-good-boundary": 3}[name]
            good = proof["admitted"] is expected and bool(attempted) is expected and len(reads) == expected_reads
            good = good and proof["required_samples"] == 3 and proof["minimum_MemAvailable_bytes"] == floor and proof["interval_seconds"] == 1.0
            good = good and sleeps == [1.0] * (expected_reads - 1)
            if name == "too-close-monotonic":
                good = good and "not separated" in proof.get("rejection", "")
            if expected:
                good = good and [row["monotonic_seconds"] for row in proof["samples"]] == [0.0, 1.0, 2.0]
            results.append({"name": name, "pass": good, "admission": proof, "mock_Popen_reached": bool(attempted), "actual_child_started": False, "injected_sleeps": sleeps})
            if not good:
                raise AssertionError("Actual call-site admission behavior differs: " + name)
        children = Path("/proc/self/task") / str(os.getpid()) / "children"
        before = children.read_text().strip()
        # Real read-only observations, with the production one-second pause.
        live = module.stable_admission()
        after = children.read_text().strip()
        if live["admitted"]:
            good = len(live["samples"]) == 3 and all(row["MemAvailable_bytes"] >= floor for row in live["samples"])
            good = good and all(b["monotonic_seconds"] - a["monotonic_seconds"] >= 1.0 for a, b in zip(live["samples"], live["samples"][1:]))
        else:
            good = any(row["MemAvailable_bytes"] < floor for row in live["samples"])
        good = good and before == after == ""
        report["actual_readonly_probe"] = {"pass": good, "admission": live, "children_before": before, "children_after": after,
                                            "meaning": "Actual admission result only; no command launch even if admitted"}
        if not good:
            raise AssertionError("Actual admission probe failed its observation contract")
        usage = module.controller_usage(); report["controller_usage"] = usage
        if usage["current_image_peak_rss_bytes"] > 256 * 1024**2:
            raise RuntimeError("Admission-only controller exceeded 256MiB")
        report["outcome"] = "pass"
    except (AssertionError, OSError, RuntimeError, ValueError, StopIteration) as error:
        report["error"] = repr(error); report["outcome"] = "fail"
    report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "error": report.get("error"), "controls": len(results),
                      "actual_readonly_admitted": report.get("actual_readonly_probe", {}).get("admission", {}).get("admitted")}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
