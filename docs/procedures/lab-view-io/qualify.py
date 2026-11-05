#!/usr/bin/env python3
"""Bounded real-filesystem qualification; never benchmark the primary registry."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch

BASE = "bf14600d5a2d6f70c33899634d463db49b47a6f6"
OWNER = "codex-team-lab-view-io-20261105-ch"
STAMP = "2026-11-05T12:00:00+00:00"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def memory_status():
    return {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
            for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith(("VmSize:", "VmRSS:", "VmHWM:", "VmPeak:"))}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic(count):
    return {"schema_version": 1, "updated_at": STAMP,
            "project": {"phase": "synthetic I/O qualification", "permissions":
                        {"host": True, "android-readonly": False, "android-app": False, "native": False}},
            "tasks": [{"id": f"IO-{i:04d}", "title": f"Synthetic task {i} café",
                       "status": "pending", "owner": None, "scope": "host",
                       "evidence_kind": "host-test", "depends_on": [],
                       "paths": [f"synthetic/{i}.py"], "acceptance": ["Synthetic fixture only"],
                       "sources": []} for i in range(count)], "experiments": [], "events": []}


def publish_locked(module, root, state):
    with (root / "state/.lab.lock").open("a") as lock:
        module.fcntl.flock(lock, module.fcntl.LOCK_EX)
        module.publish_views(root, state)


def measure(module, root, operation, stamp):
    counts = {"atomic_text": 0, "atomic_json": 0, "fsync": 0, "replace": 0}
    writes = []
    text, json_write, sync, replace = module.atomic_text, module.atomic_json, os.fsync, os.replace
    def text_write(path, value):
        counts["atomic_text"] += 1
        writes.append(path.relative_to(root).as_posix())
        return text(path, value)
    def json_writer(path, value):
        counts["atomic_json"] += 1
        writes.append(path.relative_to(root).as_posix())
        return json_write(path, value)
    def fsync(fd):
        counts["fsync"] += 1
        return sync(fd)
    def replacement(source, target):
        counts["replace"] += 1
        return replace(source, target)
    with patch.object(module, "now", return_value=stamp), patch.object(module, "atomic_text", text_write), patch.object(module, "atomic_json", json_writer), patch.object(os, "fsync", fsync), patch.object(os, "replace", replacement):
        started = time.perf_counter()
        operation()
        elapsed = time.perf_counter() - started
    module.check_views(root)
    manifest = {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*")
                if p.is_file() and p.name != ".lab.lock"}
    return {"counts": counts, "elapsed_seconds": elapsed, "writes_in_order": writes,
            "output_sha256": manifest}


def benchmark(module, count, out):
    with tempfile.TemporaryDirectory(prefix=f"io-{count}-", dir=out) as temporary:
        root = Path(temporary)
        (root / "state").mkdir()
        (root / "research").mkdir()
        state = synthetic(count)
        module.atomic_json(root / "research/sources.json", {"sources": []})
        module.atomic_json(root / "state/lab.json", state)
        with patch.object(module, "now", return_value=STAMP):
            publish_locked(module, root, state)
        repeated = measure(module, root, lambda: publish_locked(module, root, state), STAMP)
        progress = {"identical_snapshot": repeated}
        progress_path = out / f"benchmark-{module.__name__}-{count}.json"
        progress_path.write_text(json.dumps(progress, indent=2) + "\n")
        advancing = measure(module, root, lambda: publish_locked(module, root, state), "2026-11-05T12:00:01+00:00")
        progress["advancing_snapshot"] = advancing
        progress_path.write_text(json.dumps(progress, indent=2) + "\n")
        def change_task():
            with module.transaction(root, "benchmark.title", "synthetic-fixture") as changed:
                changed["tasks"][0]["title"] = "Changed synthetic title"
        changed = measure(module, root, change_task, "2026-11-05T12:00:02+00:00")
        progress["task_transaction"] = changed
        progress_path.write_text(json.dumps(progress, indent=2) + "\n")
        return progress


def main():
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--reuse-focused", help="Reuse hash-verified passing focused tests from a prior local run")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run):
        parser.error("Use a plain fresh run name")
    if args.reuse_focused and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.reuse_focused):
        parser.error("Use a plain prior run name")
    worktree = Path(__file__).resolve().parents[3]
    primary = worktree.parents[1]
    if worktree.parent != primary / "worktrees":
        raise ValueError("A separate worktree is required")
    out = worktree / "artifacts/lab-view-io" / args.run
    out.mkdir(parents=True, exist_ok=False)
    report = {"kind": "host-test", "origin": "synthetic", "baseline_commit": BASE,
              "python": sys.version, "executable": sys.executable,
              "address_space_limit_bytes": resource.getrlimit(resource.RLIMIT_AS)[0],
              "command": sys.orig_argv, "python_no_user_site": os.environ.get("PYTHONNOUSERSITE"),
              "locale": os.environ.get("LC_ALL"), "python_utf8": os.environ.get("PYTHONUTF8"),
              "memory_before": memory_status(),
              "commands": [], "outcome": "fail"}
    try:
        ledger_bytes = (primary / "state/lab.json").read_bytes()
        ledger = json.loads(ledger_bytes)
        planned = next(e for e in ledger["experiments"] if e["id"] == "LABVIEW-001")
        expected_procedure = "worktrees/lab-002-20261105/docs/procedures/lab-view-io/README.md"
        assert (planned["task"], planned["owner"], planned["status"], planned["procedure"]) == ("LAB-002", OWNER, "planned", expected_procedure)
        assert "100/500-task" in planned["hypothesis"]
        current_task = next(t for t in ledger["tasks"] if t["id"] == "LAB-002")
        assert (current_task["owner"], current_task["status"]) == (OWNER, "in_progress")
        report["prospective_plan"] = planned
        report["prospective_registry_sha256"] = hashlib.sha256(ledger_bytes).hexdigest()
        (out / "prospective-plan.json").write_text(json.dumps(planned, indent=2) + "\n")
        env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
        command = ["git", "show", BASE + ":tools/lab.py"]
        baseline = subprocess.run(command, cwd=worktree, env=env, capture_output=True, timeout=15)
        report["commands"].append({"argv": command, "exit_code": baseline.returncode})
        (out / "baseline-git-stderr.txt").write_bytes(baseline.stderr)
        baseline.check_returncode()
        baseline_path = out / "baseline-lab.py"
        baseline_path.write_bytes(baseline.stdout)
        source = worktree / "tools/lab.py"
        report["input_sha256"] = {str(p.relative_to(worktree)): digest(p) for p in
                                  [source, worktree / "tests/test_lab.py", worktree / "tests/test_planning.py", Path(__file__), Path(__file__).with_name("README.md"), baseline_path]}
        report["python_executable_sha256"] = digest(Path(sys.executable).resolve())
        baseline_module = load("baseline_lab_io", baseline_path)
        patched_module = load("patched_lab_io", source)
        if args.reuse_focused:
            prior_path = out.parent / args.reuse_focused / "report.json"
            prior = json.loads(prior_path.read_bytes())
            for name in ["tools/lab.py", "tests/test_lab.py", "tests/test_planning.py"]:
                assert prior["input_sha256"][name] == report["input_sha256"][name], (name, "Prior tests used different source")
            assert prior["focused_tests"]["failures"] == prior["focused_tests"]["errors"] == 0
            assert prior["focused_tests"]["tests_run"] == 36
            assert prior["baseline_negative_control"] == {"tests_run": 1, "failures": 1, "errors": 0}
            report["reused_focused_report"] = {"path": str(prior_path.relative_to(worktree)), "sha256": digest(prior_path)}
            report["focused_tests"] = prior["focused_tests"]
            report["baseline_negative_control"] = prior["baseline_negative_control"]
        else:
            sys.path.insert(0, str(worktree / "tests"))
            import test_lab
            control_stream = io.StringIO()
            with patch.object(test_lab, "lab", baseline_module):
                control = unittest.TextTestRunner(stream=control_stream, verbosity=2).run(
                    unittest.TestSuite([test_lab.ViewPublicationTests("test_identical_publication_preserves_files_and_only_syncs_index")]))
            (out / "baseline-negative-control.txt").write_text(control_stream.getvalue())
            report["baseline_negative_control"] = {"tests_run": control.testsRun, "failures": len(control.failures), "errors": len(control.errors)}
            assert len(control.failures) == 1 and not control.errors, "Baseline must fail the avoided-write assertion"
            suite = unittest.TestSuite()
            for pattern in ["test_lab.py", "test_planning.py"]:
                suite.addTests(unittest.defaultTestLoader.discover(str(worktree / "tests"), pattern=pattern))
            stream = io.StringIO()
            started = time.perf_counter()
            results = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            (out / "focused-tests.txt").write_text(stream.getvalue())
            report["focused_tests"] = {"tests_run": results.testsRun, "failures": len(results.failures), "errors": len(results.errors), "elapsed_seconds": time.perf_counter() - started}
            assert results.wasSuccessful(), "Focused tests failed; see focused-tests.txt"
        report["measurements"] = {}
        for count in [100, 500]:
            original = benchmark(baseline_module, count, out)
            patched = benchmark(patched_module, count, out)
            for phase in original:
                assert original[phase]["output_sha256"] == patched[phase]["output_sha256"], (count, phase, "Different output bytes")
            report["measurements"][str(count)] = {"baseline": original, "patched": patched}
        report["outcome"] = "pass"
    except Exception:
        report["error"] = traceback.format_exc()
        (out / "failure.txt").write_text(report["error"])
    finally:
        report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["peak_child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        report["rusage_note"] = "ru_maxrss may include a pre-exec maximum; actual current process counters are recorded separately."
        report["memory_after"] = memory_status()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "report": str(out / "report.json"), "focused_tests": report.get("focused_tests"), "error": report.get("error")}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
