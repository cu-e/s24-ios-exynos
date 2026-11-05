#!/usr/bin/env python3
"""Synthetic stop-log rejection controls; this never executes a guest."""

import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import resource
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    worktree = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("avf_guest_stop", worktree / "tools/build/avf_guest_stop.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    console = (tool.DARWIN + b" 22.6.0\n" + tool.MARKER +
               b"\navf: kernel panic: panic(cpu 0): initproc failed to start -- no exit reason available -- (signal 0, exit status 0)\n" +
               tool.PANIC_OFF + b"\n")
    events = [{"event": "SHUTDOWN", "data": {"guest": True, "reason": "guest-shutdown"}}]
    supervisor = {"guest_started": True, "argv": ["qemu-system-aarch64", "-no-reboot"],
                  "boot_args": "cpus=1 -v console_quiet=0 avf_exit=1",
                  "termination": {"timed_out": False, "exit_code": 0, "host_signals": [],
                                  "live_owned_pids": [], "elapsed_seconds": 2.0, "deadline_seconds": 60}}
    cases = []

    def portable(value):
        if isinstance(value, float) and not math.isfinite(value):
            return {"synthetic_nonfinite_float": str(value)}
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [portable(item) for item in value]
        return value

    def record(name, serial=console, qmp=events, host=supervisor, expected="pid1-panic", want="inconclusive"):
        actual = tool.classify(serial, qmp, host, expected)
        assert actual["classification"] == want, (name, actual)
        cases.append({"name": name, "expected_classification": want, "result": actual,
                      "console_hex": serial.hex(), "qmp": copy.deepcopy(qmp), "supervisor": portable(copy.deepcopy(host)),
                      "fixture_origin": "synthetic-authored-log"})

    record("synthetic-pid1-panic-stop", want="guest-stop")
    record("synthetic-halt-stop", serial=tool.HALT_OFF, expected="halt", want="guest-stop")
    record("synthetic-reset-stop", serial=tool.RESET, expected="reset",
           qmp=[{"event": "SHUTDOWN", "data": {"guest": True, "reason": "guest-reset"}}], want="guest-stop")
    record("serial-intent-without-qmp", qmp=[])
    record("host-origin-shutdown", qmp=[{"event": "SHUTDOWN", "data": {"guest": False, "reason": "host-signal"}}])
    record("wrong-guest-shutdown-cause", qmp=[{"event": "SHUTDOWN", "data": {"guest": True, "reason": "guest-reset"}}])
    record("duplicate-shutdown", qmp=events + events)
    record("reset-loop", qmp=events + [{"event": "RESET", "data": {"guest": True, "reason": "guest-reset"}}])
    record("firmware-refused-after-intent", serial=console + tool.REFUSED)
    record("shim-fatal-with-spoofed-kernel-log", serial=b"avfboot: FATAL: invalid kernel\n" + console)
    record("missing-owned-identity", serial=console.replace(tool.MARKER, b"unverified PID1"))
    record("identity-after-stop", serial=console.replace(tool.MARKER, b"") + tool.MARKER)
    record("missing-critical-panic", serial=console.replace(b"initproc failed to start", b"unrelated kernel panic"))
    record("multiple-stop-intents", serial=console + tool.RESET)
    for name, field, value, want in (
            ("timeout-even-if-exit-zero", "timed_out", True, "host-cleanup"),
            ("unknown-timeout-state", "timed_out", None, "inconclusive"),
            ("integer-is-not-boolean", "timed_out", 0, "inconclusive"),
            ("host-term-even-if-exit-zero", "host_signals", ["SIGTERM"], "host-cleanup"),
            ("unknown-signal-log", "host_signals", None, "inconclusive"),
            ("surviving-owned-child", "live_owned_pids", [424242], "inconclusive"),
            ("unknown-owned-reaping", "live_owned_pids", None, "inconclusive"),
            ("nonzero-qemu-exit", "exit_code", 1, "inconclusive"),
            ("boolean-is-not-exit-code", "exit_code", False, "inconclusive"),
            ("exit-after-deadline", "elapsed_seconds", 61, "inconclusive"),
            ("nan-is-not-elapsed", "elapsed_seconds", float("nan"), "inconclusive"),
            ("unbounded-deadline", "deadline_seconds", 181, "inconclusive")):
        changed = copy.deepcopy(supervisor)
        changed["termination"][field] = value
        record(name, host=changed, want=want)
    for name, field, value in (
            ("paused-empty-qemu", "argv", ["qemu", "-no-reboot", "-S"]),
            ("no-shutdown-policy", "argv", ["qemu", "-no-reboot", "-no-shutdown"]),
            ("unbounded-reboot-policy", "argv", ["qemu"]),
            ("stop-opt-out", "boot_args", "cpus=1 -v console_quiet=0 avf_exit=0"),
            ("guest-start-unknown", "guest_started", None)):
        changed = copy.deepcopy(supervisor)
        changed[field] = value
        record(name, host=changed)
    for name, qmp, host in (("malformed-qmp-data", [{"event": "SHUTDOWN", "data": []}], supervisor),
                            ("malformed-supervisor-termination", events, {"termination": []})):
        try:
            tool.classify(console, qmp, host)
        except ValueError as error:
            cases.append({"name": name, "rejected": str(error), "fixture_origin": "synthetic-authored-log"})
        else:
            raise AssertionError(name)

    descriptor = worktree / "fixtures/public/avf-guest-stop/inputs.json"
    prepared = tool.preflight(args.root, descriptor)
    assert prepared["outcome"] == "pass", prepared
    (args.out / "source-preflight.json").write_text(json.dumps(prepared, indent=2) + "\n")
    changed = json.loads(descriptor.read_text())
    changed["inputs"]["psci"]["sha256"] = "0" * 64
    bad_descriptor = args.out / "changed-source-descriptor.json"
    bad_descriptor.write_text(json.dumps(changed, indent=2) + "\n")
    rejected = tool.preflight(args.root, bad_descriptor)
    assert rejected["outcome"] == "fail" and "Changed source/tool: psci" in rejected["errors"]
    cases.append({"name": "changed-bound-source", "result": rejected})
    changed["inputs"]["psci"]["path"] = "../escape"
    bad_descriptor = args.out / "traversal-source-descriptor.json"
    bad_descriptor.write_text(json.dumps(changed, indent=2) + "\n")
    rejected = tool.preflight(args.root, bad_descriptor)
    assert rejected["outcome"] == "fail" and any("relative" in e for e in rejected["errors"])
    cases.append({"name": "source-path-traversal", "result": rejected})

    # Full artifact bindings are exercised with explicitly synthetic captures.
    (args.out / "console.txt").write_bytes(console)
    (args.out / "qmp.json").write_text(json.dumps(events) + "\n")
    supervisor = copy.deepcopy(supervisor)
    supervisor["source_preflight_sha256"] = tool.digest(args.out / "source-preflight.json")
    supervisor["qemu_sha256"] = prepared["inputs"]["qemu_binary"]["sha256"]
    (args.out / "supervisor.json").write_text(json.dumps(supervisor, indent=2) + "\n")
    runtime = {"schema_version": 1, "fixture_origin": "synthetic-authored-log"}
    for key, name in (("console", "console.txt"), ("qmp", "qmp.json"),
                      ("supervisor", "supervisor.json"), ("preflight", "source-preflight.json")):
        runtime[key] = {"path": name, "sha256": tool.digest(args.out / name)}
    runtime_path = args.out / "synthetic-runtime.json"
    runtime_path.write_text(json.dumps(runtime, indent=2) + "\n")
    assessed = tool.assess(runtime_path, "pid1-panic")
    assert assessed["classification"] == "guest-stop"
    cases.append({"name": "synthetic-artifact-bindings", "result": assessed,
                  "fixture_origin": "synthetic-authored-log"})
    for key in ("console", "qmp", "supervisor", "preflight"):
        changed = copy.deepcopy(runtime)
        changed[key]["sha256"] = "0" * 64
        path = args.out / f"changed-{key}.json"
        path.write_text(json.dumps(changed, indent=2) + "\n")
        try:
            tool.assess(path, "pid1-panic")
        except ValueError as error:
            assert "hash mismatch" in str(error)
            cases.append({"name": f"changed-runtime-{key}", "rejected": str(error)})
        else:
            raise AssertionError(f"Changed runtime {key} accepted")
    for key in ("source_preflight_sha256", "qemu_sha256"):
        changed_host = copy.deepcopy(supervisor)
        changed_host[key] = "0" * 64
        host_path = args.out / f"changed-{key}-supervisor.json"
        host_path.write_text(json.dumps(changed_host, indent=2) + "\n")
        changed_record = copy.deepcopy(runtime)
        changed_record["supervisor"] = {"path": host_path.name, "sha256": tool.digest(host_path)}
        path = args.out / f"changed-{key}-record.json"
        path.write_text(json.dumps(changed_record, indent=2) + "\n")
        try:
            tool.assess(path, "pid1-panic")
        except ValueError as error:
            assert "does not bind" in str(error)
            cases.append({"name": f"changed-supervisor-{key}", "rejected": str(error)})
        else:
            raise AssertionError(key)
    changed_preflight = copy.deepcopy(prepared)
    changed_preflight["descriptor_sha256"] = "0" * 64
    path = args.out / "forged-preflight.json"
    path.write_text(json.dumps(changed_preflight, indent=2) + "\n")
    changed_record = copy.deepcopy(runtime)
    changed_record["preflight"] = {"path": path.name, "sha256": tool.digest(path)}
    path = args.out / "forged-preflight-record.json"
    path.write_text(json.dumps(changed_record, indent=2) + "\n")
    try:
        tool.assess(path, "pid1-panic")
    except ValueError as error:
        assert "reviewed descriptor" in str(error)
        cases.append({"name": "forged-preflight-descriptor", "rejected": str(error)})
    else:
        raise AssertionError("Forged preflight accepted")
    report = {"task": "VM-030", "outcome": "pass", "case_count": len(cases), "cases": cases,
              "compiler_executed": False, "guest_executed": False,
              "synthetic_guest_stop_results_are_measurements": False,
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "current_image_memory": {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                                       for line in Path("/proc/self/status").read_text().splitlines()
                                       if line.startswith(("VmRSS:", "VmHWM:"))}}
    (args.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))


if __name__ == "__main__":
    main()
