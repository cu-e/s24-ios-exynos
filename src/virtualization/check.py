#!/usr/bin/env python3
"""Check actual owned Mach-O bytes and host deadline mechanics, without a VM."""
import argparse
import json
from pathlib import Path
import signal
import struct
import sys

import host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid1", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    checks = []
    structure = host.macho(args.pid1)
    checks.append({"check": "actual linked arm64 static PID1", "structure": structure})
    original = args.pid1.read_bytes()
    cases = {"pid1-is-not-kernel": original,
             "truncated-header": original[:31],
             "truncated-commands": original[:48],
             "source-is-not-executable": Path(__file__).with_name("pid1.c").read_bytes()}
    for name, offset, value in [("wrong-cpu", 4, 0x01000007),
                                ("wrong-filetype", 12, 1),
                                ("unbounded-command-count", 16, 0xFFFFFFFF),
                                ("unbounded-command-size", 20, 0xFFFFFFFF),
                                ("zero-command-length", 36, 0),
                                ("overflow-command-length", 36, 0xFFFFFFF8)]:
        changed = bytearray(original)
        struct.pack_into("<I", changed, offset, value)
        cases[name] = changed
    for name, data in cases.items():
        path = args.out / (name + ".bin")
        path.write_bytes(data)
        try:
            host.macho(path, kernel=name == "pid1-is-not-kernel")
        except ValueError as error:
            checks.append({"check": name, "result": "rejected", "reason": str(error)})
        else:
            raise AssertionError(f"Malformed/non-kernel input accepted: {name}")
    deadline = host.bounded([sys.executable, "-c",
        "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('host timeout control',flush=True);time.sleep(30)"],
        args.out / "deadline-console.txt", 1)
    assert deadline["timed_out"] and deadline["exit_code"] == -signal.SIGKILL
    assert deadline["elapsed_seconds"] < 5
    checks.append({"check": "owned child ignores SIGTERM and is killed within bound", **deadline})
    report = {"outcome": "pass", "kind": "host-test", "checks": checks,
              "guest_started": False, "pid1_observed": False,
              "limitation": "Parser and process termination controls do not execute XNU."}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
