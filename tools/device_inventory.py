#!/usr/bin/env python3
"""Collect a narrow, serial-free Android inventory. No su, writes, reboot or pairing."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

PROPERTIES = ["ro.product.model", "ro.product.device", "ro.soc.model", "ro.board.platform",
              "ro.build.version.release", "ro.build.version.sdk", "ro.build.version.oneui",
              "ro.build.version.incremental", "ro.boot.flash.locked", "ro.boot.verifiedbootstate",
              "ro.boot.slot_suffix"]


def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=12, check=True).stdout.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", help="Explicit ADB endpoint; never saved in the inventory")
    p.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "devices/local.json")
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new output name; previous observations are immutable")
    rows = [line.split() for line in run(["adb", "devices"]).splitlines()[1:] if line.strip()]
    if args.device:
        rows = [row for row in rows if row[0] == args.device]
    if len(rows) != 1 or len(rows[0]) < 2 or rows[0][1] != "device":
        raise RuntimeError("Exactly one authorized ADB device is required; no pairing or connection changes were attempted")
    endpoint = rows[0][0]
    base = ["adb", "-s", endpoint, "shell"]
    props = {key: run(base + ["getprop", key]) for key in PROPERTIES}
    model, device = props["ro.product.model"], props["ro.product.device"]
    data = {"schema_version": 1, "origin": "local-device", "observed_at": datetime.now(timezone.utc).isoformat(),
            "properties": props, "adb_shell_identity": run(base + ["id"]),
            "kernel_release": run(base + ["uname", "-r"]),
            "screen_size": run(base + ["wm", "size"]), "screen_density": run(base + ["wm", "density"]),
            "matches_reference_target": model == "SM-S921B" and device == "e1s",
            "root_access": "not tested; bootloader unlock does not establish root",
            "limitations": "Read-only observations in Android; no native XNU compatibility is established. No hardware identifiers collected."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Keep inventories private and immutable: choose a new output name for another observation.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {args.output}; reference target match: {data['matches_reference_target']}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        # Never echo an ADB command with its serial number through exception text.
        print(f"inventory: {type(exc).__name__}; collection failed, no phone settings were changed", file=sys.stderr)
        sys.exit(2)
