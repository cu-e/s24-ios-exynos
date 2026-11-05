#!/usr/bin/env python3
"""Prove selected contract and rejection controls on preserved actual capture bytes."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("device_tree", ROOT / "tools/build/avf_guest_device_tree.py")
dt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"kind": "host-test", "origin": "local-host", "task": "VM-027", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(), "argv": sys.argv, "controls": [],
              "capture_report": str(args.capture_report), "capture_report_sha256": dt.sha256(args.capture_report),
              "controls_sha256": dt.sha256(__file__), "parser_sha256": dt.sha256(ROOT / "tools/build/avf_guest_device_tree.py"),
              "compiler_executed": False, "guest_executed_by_this_command": False,
              "xnu_executed": False, "pid1_executed": False}
    try:
        capture = json.loads(args.capture_report.read_text())
        if capture["outcome"] != "pass" or capture["exit_code"] != 0 or capture["after"]["owned_processes"]:
            raise ValueError("Capture has not established successful quit and empty owned session")
        tree_path = args.capture_report.parent / "apple-tree.adt"
        raw, nodes = dt.read_tree(tree_path)
        if len(raw) != capture["dynamic_extent"]["length"] or dt.sha256(tree_path) != capture["capture_sha256"]:
            raise ValueError("Actual bytes do not match captured dynamic extent/hash")
        qmp_sent = [row["sent"] for row in capture["qmp"] if "sent" in row]
        if [row["execute"] for row in qmp_sent] != ["qmp_capabilities", "stop", "query-status", "pmemsave", "quit"]:
            raise ValueError("Unexpected capture QMP operation sequence")
        expected = {"val": capture["dynamic_extent"]["address"], "size": len(raw), "filename": str(tree_path)}
        if qmp_sent[3]["arguments"] != expected:
            raise ValueError("QMP capture arguments disagree with preserved data")
        # Bind the exact files independently after the already bounded capture.
        report["input_bindings"] = []
        for name, row in capture["plan"]["pins"].items():
            if dt.sha256(row["path"]) != row["sha256"]:
                raise ValueError("Input changed after capture: " + name)
            report["input_bindings"].append({"name": name, **row})
        report["actual_preflight"] = dt.preflight(nodes, require_pci=True)
        report.update(actual_serialized_shim_data_verified=True, capture_sha256=capture["capture_sha256"],
                      capture_size=len(raw), dynamic_extent=capture["dynamic_extent"])

        def reject(name, data):
            path = args.out / (name + ".adt")
            path.write_bytes(data)
            try:
                dt.preflight(dt.parse(data), require_pci=True)
            except dt.TreeError as error:
                report["controls"].append({"name": name, "pass": True, "rejection": str(error),
                                           "path": str(path), "sha256": dt.sha256(path), "size": len(data)})
            else:
                report["controls"].append({"name": name, "pass": False, "path": str(path)})

        # Renaming exactly one preserved header makes a real property absent,
        # without rebuilding the original tree or changing its layout.
        for name, path, prop in (("missing-gic-reg", "/arm-io/gic", "reg"),
                                  ("missing-psci-method", "/chosen", "psci-method"),
                                  ("missing-uart-compatible", "/arm-io/uart0", "compatible"),
                                  ("missing-cpu-state", "/cpus/cpu0", "state"),
                                  ("missing-pci-ecam", "/pci0", "ecam")):
            changed = bytearray(raw)
            header = nodes[path]["value_offsets"][prop] - 36
            changed[header:header + 32] = b"vm027-missing" + bytes(19)
            reject(name, changed)
        changed = bytearray(raw)
        offset = nodes["/arm-io/gic"]["value_offsets"]["virtual-timer-intid"]
        changed[offset:offset + 4] = (26).to_bytes(4, "little")
        reject("actual-timer-consumer-mismatch", changed)
        changed = bytearray(raw)
        offset = nodes["/arm-io/uart0"]["value_offsets"]["compatible"]
        changed[offset + len(nodes["/arm-io/uart0"]["properties"]["compatible"]) - 1] = ord("x")
        reject("unterminated-actual-uart-compatible", changed)
        reject("truncated-actual-tree", raw[:-1])
        changed = bytearray(raw)
        offset = nodes["/arm-io/gic"]["value_offsets"]["reg"] - 4
        changed[offset:offset + 4] = (0xffffffff).to_bytes(4, "little")
        reject("malformed-actual-gic-length", changed)
        report["outcome"] = "pass" if all(row["pass"] for row in report["controls"]) else "fail"
    except Exception as error:
        report["error"] = repr(error)
    with open("/proc/self/status", encoding="ascii") as stream:
        report["current_image_VmHWM_bytes"] = next(int(line.split()[1]) * 1024 for line in stream if line.startswith("VmHWM:"))
    report["elapsed_seconds"] = time.monotonic() - started
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report.get(key) for key in ("outcome", "error", "capture_size", "current_image_VmHWM_bytes")}))
    return 0 if report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
