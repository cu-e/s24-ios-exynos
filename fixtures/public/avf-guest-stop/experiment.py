#!/usr/bin/env python3
"""VMSTOP-001: finite offline negative CLI observations, no guest execution."""

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    args.out.mkdir(parents=True, exist_ok=False)
    tool = Path(__file__).resolve().parents[3] / "tools/build/avf_guest_stop.py"
    base = {name: (args.controls / name).read_bytes() for name in
            ("console.txt", "qmp.json", "supervisor.json", "source-preflight.json")}
    commands = []
    for case in ("timeout", "host-origin", "malformed-qmp", "unreviewed-preflight"):
        folder = args.out / case
        folder.mkdir()
        content = copy.deepcopy(base)
        if case == "timeout":
            host = json.loads(content["supervisor.json"])
            host["termination"]["timed_out"] = True
            content["supervisor.json"] = (json.dumps(host, indent=2) + "\n").encode()
        if case == "host-origin":
            content["qmp.json"] = json.dumps([{"event": "SHUTDOWN", "data": {"guest": False, "reason": "host-signal"}}]).encode()
        if case == "malformed-qmp":
            content["qmp.json"] = b'[{"event":"SHUTDOWN","data":[]}]\n'
        if case == "unreviewed-preflight":
            prepared = json.loads(content["source-preflight.json"])
            prepared["descriptor_sha256"] = "0" * 64
            content["source-preflight.json"] = (json.dumps(prepared, indent=2) + "\n").encode()
        runtime = {"schema_version": 1, "fixture_origin": "synthetic-authored-log"}
        for key, name in (("console", "console.txt"), ("qmp", "qmp.json"),
                          ("supervisor", "supervisor.json"), ("preflight", "source-preflight.json")):
            (folder / name).write_bytes(content[name])
            runtime[key] = {"path": name, "sha256": digest(folder / name)}
        record = folder / "runtime.json"
        record.write_text(json.dumps(runtime, indent=2) + "\n")
        output = folder / "assessment.json"
        argv = [sys.executable, "-s", str(tool), "--out", str(output), "assess", "--record", str(record)]
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        start = time.monotonic()
        with (folder / "stdout.txt").open("xb") as stdout, (folder / "stderr.txt").open("xb") as stderr:
            proc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                  timeout=5, start_new_session=True)
        elapsed = round(time.monotonic() - start, 6)
        result = json.loads(output.read_text())
        assert proc.returncode == 2, (case, result)
        if case == "timeout":
            assert result["classification"] == "host-cleanup", result
        elif case == "host-origin":
            assert result["classification"] == "inconclusive", result
        else:
            assert result["outcome"] == "fail", result
        commands.append({"case": case, "argv": argv, "cwd": str(Path.cwd()),
                         "started_at": timestamp, "elapsed_seconds": elapsed, "exit_code": proc.returncode,
                         "assessment": result, "python_sha256": digest(Path(sys.executable)),
                         "tool_sha256": digest(tool), "address_space_cap_bytes": 256 * 1024 * 1024})
    files = [{"path": str(path.relative_to(args.out)), "sha256": digest(path), "size": path.stat().st_size}
             for path in sorted(args.out.rglob("*")) if path.is_file()]
    result = {"experiment": "VMSTOP-001", "task": "VM-030", "outcome": "pass",
              "fixture_origin": "synthetic-authored-log", "guest_executed": False, "compiler_executed": False,
              "commands": commands, "files": files,
              "environment": {name: os.environ.get(name) for name in
                              ("LC_ALL", "PYTHONUTF8", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")}}
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"outcome": "pass", "cases": len(commands), "guest_executed": False}))


if __name__ == "__main__":
    main()
