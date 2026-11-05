#!/usr/bin/env python3
"""Exercise the real source-inspection CLI and preserve rejection diagnostics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    pin = json.loads(Path(__file__).with_name("inputs.json").read_text())
    cases = [("exact-source", None, 0, None)]
    for name, semantic in (("wrong-source-hash", False), ("changed-timer-semantic", True)):
        descriptor = json.loads(json.dumps(pin))
        item = descriptor["files"]["qemu_bsa"]
        source = (args.main / item["path"]).read_text()
        changed = source.replace("ARCH_TIMER_VIRT_IRQ        27", "ARCH_TIMER_VIRT_IRQ        30")
        if changed == source:
            raise ValueError("upstream semantic-control target changed")
        owned = args.out / (name + ".h")
        owned.write_text(changed)
        item["path"] = str(owned.resolve())
        if semantic:
            with owned.open("rb") as stream:
                item["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            item["size"] = owned.stat().st_size
        descriptor_path = args.out / (name + ".json")
        descriptor_path.write_text(json.dumps(descriptor, indent=2) + "\n")
        cases.append((name, descriptor_path, 2, "timer PPI differs" if semantic else "input identity mismatch: qemu_bsa"))
    records = []
    for name, descriptor_path, expected, error in cases:
        command = [sys.executable, "-s", str(ROOT / "tools/build/avf_guest_timer_irq.py"),
                   "--main", str(args.main), "--out", str(args.out / name), "--controls"]
        if descriptor_path:
            command += ["--inputs", str(descriptor_path)]
        start = time.monotonic()
        with (args.out / (name + ".stdout")).open("xb") as stdout, (args.out / (name + ".stderr")).open("xb") as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=35,
                                    env=dict(os.environ) | {"LC_ALL": "C", "PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        report = json.loads((args.out / name / "report.json").read_text())
        passed = result.returncode == expected and (error is None or report.get("error") == error)
        records.append({"name": name, "argv": command, "exit_code": result.returncode,
                        "expected_exit_code": expected, "elapsed_seconds": time.monotonic() - start,
                        "report": str(args.out / name / "report.json"), "pass": passed})
    passed = all(record["pass"] for record in records)
    (args.out / "checks.json").write_text(json.dumps({"outcome": "pass" if passed else "fail", "commands": records}, indent=2) + "\n")
    print(json.dumps({"outcome": "pass" if passed else "fail", "cases": len(records)}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
