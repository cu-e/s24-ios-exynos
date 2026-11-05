#!/usr/bin/env python3
"""Read-only AVF stop source preflight and offline QEMU stop classification.

Never starts QEMU, a compiler, a child process, or a physical device operation.
Classification consumes observations; synthetic controls are not guest evidence.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys


MARKER = b"VM002: pid=1 ostype=Darwin owned-entry=v1"
DARWIN = b"Darwin Kernel Version"
PANIC_OFF = b"avf: powering off (PSCI SYSTEM_OFF)"
HALT_OFF = b"avf: halt (PSCI SYSTEM_OFF)"
RESET = b"avf: reboot (PSCI SYSTEM_RESET)"
REFUSED = b"avf: the firmware refused to end the machine"
MAX_JSON = 16 * 1024 * 1024
MAX_CONSOLE = 16 * 1024 * 1024
DESCRIPTOR = Path(__file__).resolve().parents[2] / "fixtures/public/avf-guest-stop/inputs.json"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    if path.stat().st_size > MAX_JSON:
        raise ValueError(f"JSON input exceeds {MAX_JSON} bytes: {path}")
    with path.open(encoding="utf-8") as stream:
        def reject_constant(value):
            raise ValueError(f"Nonfinite JSON number: {value}")
        return json.load(stream, parse_constant=reject_constant)


def relative(root, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Input path must be relative and stay inside the specified root")
    target = (root / path).resolve(strict=True)
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Input symlink escapes the specified root")
    return target


def preflight(root, descriptor):
    result = {"schema_version": 1, "task": "VM-030", "kind": "source-review",
              "outcome": "fail", "inputs": {}, "errors": [],
              "descriptor_sha256": digest(descriptor), "guest_executed": False,
              "compiler_executed": False, "kernel_image_qualified": False}
    data = read_json(descriptor)
    if data.get("schema_version") != 1 or data.get("task") != "VM-030":
        raise ValueError("Unexpected source descriptor identity")
    for key, item in data["inputs"].items():
        try:
            path = relative(root, item["path"])
            observed = {"path": item["path"], "sha256": digest(path),
                        "size": path.stat().st_size}
            result["inputs"][key] = observed
            if any(observed[field] != item[field] for field in ("sha256", "size")):
                result["errors"].append(f"Changed source/tool: {key}")
        except (OSError, ValueError) as error:
            result["errors"].append(f"{key}: {error}")
    result["source_pins"] = data["source_pins"]
    if not result["errors"]:
        sources = read_json(relative(root, data["inputs"]["sources"]["path"]))
        composition = read_json(relative(root, data["inputs"]["composition"]["path"]))
        for repo in ("scion", "xnu"):
            if sources[repo]["commit"] != data["source_pins"][repo]:
                result["errors"].append(f"Unexpected canonical source commit: {repo}")
        if composition["source_manifest_sha256"] != data["inputs"]["sources"]["sha256"]:
            result["errors"].append("Composition does not bind the canonical source manifest")
        composed = {row["path"]: row for row in composition["common_source_files"]}
        for key, item in data["inputs"].items():
            member = item.get("composition_member")
            if member and (composed.get(member["path"]) != member or
                           member["sha256"] != item["sha256"] or member["size"] != item["size"]):
                result["errors"].append(f"Canonical composed member mismatch: {key}")
            member = item.get("source_member")
            if member:
                canonical = {row["path"]: row for row in sources[item["source_repo"]]["files"]}
                if (canonical.get(member["path"]) != member or member["sha256"] != item["sha256"]
                        or member["size"] != item["size"]):
                    result["errors"].append(f"Canonical upstream member mismatch: {key}")
    result["outcome"] = "pass" if not result["errors"] else "fail"
    return result


def classify(console, events, supervisor, expected="pid1-panic"):
    """Classify supplied observations; source and artifact binding is done by assess.

    A serial string before a PSCI call proves intent only. QMP and the owned
    supervisor must independently record a guest-origin stop and complete reaping.
    """
    if (not isinstance(console, bytes) or not isinstance(events, list)
            or any(not isinstance(event, dict) or not isinstance(event.get("data", {}), dict) for event in events)
            or not isinstance(supervisor, dict) or not isinstance(supervisor.get("termination", {}), dict)):
        raise ValueError("Malformed console, QMP event or supervisor record")
    facts = {"identity_marker": MARKER in console and DARWIN in console,
             "firmware_refused": REFUSED in console,
             "guest_stop_observed": False, "pid1_panic_stop_observed": False}
    reasons = []
    termination = supervisor.get("termination", {})
    # Identity checks deliberately use `is`: 0 and 1 are not JSON booleans here.
    if supervisor.get("guest_started") is not True:
        reasons.append("Guest start is not recorded")
    if termination.get("timed_out") is not False:
        reasons.append("Deadline expired or its state is unknown")
    if termination.get("host_signals") != []:
        reasons.append("Host signals were used or are not exhaustively recorded")
    if termination.get("live_owned_pids") != []:
        reasons.append("Owned process reaping is incomplete or unknown")
    if type(termination.get("exit_code")) is not int or termination["exit_code"] != 0:
        reasons.append("QEMU did not exit with status zero")
    elapsed = termination.get("elapsed_seconds")
    deadline = termination.get("deadline_seconds")
    if (type(elapsed) not in (int, float) or type(deadline) not in (int, float)
            or not 0 <= elapsed < deadline <= 180):
        reasons.append("Finite in-deadline termination is not established")
    argv = supervisor.get("argv", [])
    if not isinstance(argv, list) or "-no-reboot" not in argv or "-S" in argv or "-no-shutdown" in argv:
        reasons.append("Expected running, terminating -no-reboot QEMU policy is absent")
    if supervisor.get("boot_args") != "cpus=1 -v console_quiet=0 avf_exit=1":
        reasons.append("Exact stop-enabled boot arguments are not bound")
    shutdowns = [event for event in events if event.get("event") == "SHUTDOWN"]
    expected_reason = "guest-reset" if expected == "reset" else "guest-shutdown"
    if (len(shutdowns) != 1 or shutdowns[0].get("data", {}).get("guest") is not True
            or shutdowns[0].get("data", {}).get("reason") != expected_reason):
        reasons.append("Exactly one matching guest-origin QMP SHUTDOWN is required")
    if any(event.get("event") in {"RESET", "GUEST_PANICKED"} for event in events):
        reasons.append("Unexpected reset or paravirtual panic event needs review")
    if facts["firmware_refused"]:
        reasons.append("Kernel records firmware refusing the PSCI request")
    wanted = {"pid1-panic": PANIC_OFF, "halt": HALT_OFF, "reset": RESET}[expected]
    positions = [console.find(token) for token in (PANIC_OFF, HALT_OFF, RESET)]
    if console.count(wanted) != 1 or sum(pos >= 0 for pos in positions) != 1:
        reasons.append("Exactly one expected kernel PSCI intent line is required")
    if b"avfboot: FATAL:" in console:
        reasons.append("Shim failure is not a genuine kernel stop")
    if expected == "pid1-panic":
        panic_at = console.find(b"avf: kernel panic: panic(")
        critical = min((pos for pos in (console.find(b"initproc failed to start"),
                                       console.find(b"initproc exited")) if pos >= 0), default=-1)
        marker_at = console.find(MARKER)
        if not (facts["identity_marker"] and 0 <= console.find(DARWIN) < marker_at < panic_at <= critical < console.find(PANIC_OFF)):
            reasons.append("Owned PID1 identity, critical-exit panic and poweroff intent are not ordered")
    facts["guest_stop_observed"] = not reasons
    facts["pid1_panic_stop_observed"] = not reasons and expected == "pid1-panic"
    forced = termination.get("timed_out") is True or bool(termination.get("host_signals"))
    return {"classification": "guest-stop" if not reasons else "host-cleanup" if forced else "inconclusive",
            "expected": expected, "facts": facts, "reasons": reasons,
            "psci_call_observed": False,
            "limitations": ["QMP guest origin plus serial intent is consistent with the bound PSCI path; it is not an instruction trace.",
                            "This does not qualify a complete kernel, source-to-image linkage, or S24 support."]}


def assess(record_path, expected):
    record = read_json(record_path)
    if record.get("schema_version") != 1:
        raise ValueError("Unexpected runtime record schema")
    root = record_path.parent.resolve()
    inputs = {}
    paths = {}
    for key in ("console", "qmp", "supervisor", "preflight"):
        item = record[key]
        path = relative(root, item["path"])
        actual = digest(path)
        if actual != item["sha256"]:
            raise ValueError(f"Runtime input hash mismatch: {key}")
        inputs[key] = {"path": str(path), "sha256": actual}
        paths[key] = path
    prepared = read_json(paths["preflight"])
    if prepared.get("task") != "VM-030" or prepared.get("outcome") != "pass":
        raise ValueError("Passing source preflight required")
    bound = read_json(DESCRIPTOR)
    if prepared.get("descriptor_sha256") != digest(DESCRIPTOR):
        raise ValueError("Source preflight does not bind the reviewed descriptor")
    for key, item in bound["inputs"].items():
        if any(prepared.get("inputs", {}).get(key, {}).get(field) != item[field]
               for field in ("path", "sha256", "size")):
            raise ValueError(f"Source preflight has a missing or changed input: {key}")
    supervisor = read_json(paths["supervisor"])
    if supervisor.get("source_preflight_sha256") != inputs["preflight"]["sha256"]:
        raise ValueError("Runtime supervisor does not bind the source preflight")
    qemu = prepared.get("inputs", {}).get("qemu_binary", {}).get("sha256")
    if not qemu or supervisor.get("qemu_sha256") != qemu:
        raise ValueError("Runtime supervisor does not bind the pinned QEMU tool")
    if paths["console"].stat().st_size > MAX_CONSOLE:
        raise ValueError("Console exceeds the bounded offline inspection limit")
    events = read_json(paths["qmp"])
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("QMP capture must be a JSON array of event objects")
    result = classify(paths["console"].read_bytes(), events, supervisor, expected)
    result.update({"kind": "offline-observation-assessment", "inputs": inputs,
                   "record_sha256": digest(record_path), "guest_executed_by_this_tool": False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    source = sub.add_parser("preflight")
    source.add_argument("--root", type=Path, required=True)
    source.add_argument("--descriptor", type=Path, default=DESCRIPTOR)
    runtime = sub.add_parser("assess")
    runtime.add_argument("--record", type=Path, required=True)
    runtime.add_argument("--expected", choices=("pid1-panic", "halt", "reset"), default="pid1-panic")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output must be new; preserve previous attempts")
    try:
        result = preflight(args.root, args.descriptor) if args.action == "preflight" else assess(args.record, args.expected)
        code = 0 if result.get("outcome") == "pass" or result.get("classification") == "guest-stop" else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        result, code = {"outcome": "fail", "error": str(error)}, 2
    result["recorded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    status = Path("/proc/self/status")
    if status.is_file():
        result["current_image_memory"] = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                                          for line in status.read_text().splitlines()
                                          if line.startswith(("VmRSS:", "VmHWM:"))}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
