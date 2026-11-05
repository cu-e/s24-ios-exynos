#!/usr/bin/env python3
"""Only the two root-requested capture guard regression controls; no guest."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal

spec = importlib.util.spec_from_file_location("capture", Path(__file__).with_name("capture.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    records = []
    limit = 4 * 1024**3
    capture.enforce_running_floor({"MemAvailable_bytes": limit}, True)
    records.append({"name": "post-spawn-exact-floor-admitted", "pass": True})
    try:
        capture.enforce_running_floor({"MemAvailable_bytes": limit - 1}, True)
    except MemoryError:
        records.append({"name": "post-spawn-below-floor-stops", "pass": True})
    else:
        records.append({"name": "post-spawn-below-floor-stops", "pass": False})
    cleaned, escaped = False, False
    previous = signal.signal(signal.SIGTERM, capture.interrupt_for_cleanup)
    try:
        try:
            try:
                signal.raise_signal(signal.SIGTERM)
            except OSError:
                pass  # Models the accepted /proc helper's narrow error handling.
        finally:
            cleaned = True
    except KeyboardInterrupt:
        escaped = True
    finally:
        signal.signal(signal.SIGTERM, previous)
    records.append({"name": "SIGTERM-BaseException-escapes-OSError-and-runs-finally", "pass": cleaned and escaped})
    records.append({"name": "SIGTERM-handler-restored", "pass": signal.getsignal(signal.SIGTERM) == previous})
    result = {"outcome": "pass" if all(row["pass"] for row in records) else "fail", "controls": records,
              "capture_script_sha256": capture.digest(capture.__file__), "controls_sha256": capture.digest(__file__),
              "guest_executed": False, "compiler_executed": False}
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"outcome": result["outcome"], "controls": len(records)}))
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
