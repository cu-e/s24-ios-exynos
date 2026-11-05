#!/usr/bin/env python3
"""Read-only E1S input inventory; never downloads, executes donor tools or builds XNU."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def file_observation(path: Path, executable=False):
    """A nonempty readable file is a presence observation, never an ABI verdict."""
    observation = {"path": str(path), "present": False}
    try:
        observation["present"] = path.is_file() and path.stat().st_size > 0
        if executable:
            observation["executable"] = observation["present"] and os.access(path, os.X_OK)
            observation["present"] = observation["executable"]
    except OSError as error:
        observation["error"] = str(error)
    return observation


def sdk_observation(path: Path, expected_metadata_sha256: str):
    observation = {"path": str(path), "sdk_abi_verified": False, "complete_sdk_verified": False}
    try:
        settings = path / "SDKSettings.json"
        with settings.open("rb") as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError("SDKSettings.json exceeds the metadata bound")
        metadata = json.loads(data)
        if not isinstance(metadata, dict):
            raise ValueError("SDKSettings.json must be an object")
        observation.update(metadata_sha256=hashlib.sha256(data).hexdigest(),
                           version=metadata.get("Version"), canonical_name=metadata.get("CanonicalName"),
                           display_name=metadata.get("DisplayName"))
        observation["matches_reviewed_metadata_only"] = observation["metadata_sha256"] == expected_metadata_sha256
        observation["directories"] = {name: (path / name).is_dir()
                                      for name in ["usr/include", "System/Library/Frameworks"]}
    except (OSError, ValueError) as error:
        observation["error"] = str(error)
    return observation


def tool_observation(path: Path, profile):
    observation = {"path": str(path), "pin_verified": False}
    commands = []
    try:
        # No upstream script, hook, fsmonitor or build program is executed.
        for args in [("rev-parse", "--show-toplevel"), ("rev-parse", "HEAD"),
                     ("remote", "get-url", "origin"), ("status", "--porcelain", "--untracked-files=all")]:
            argv = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(path), *args]
            run = subprocess.run(argv, capture_output=True, text=True, timeout=20,
                                 env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
            commands.append({"argv": argv, "exit_code": run.returncode})
            if run.returncode:
                raise ValueError("Local tool checkout could not be verified")
            commands[-1]["result"] = run.stdout.strip()
        top, pin, origin, dirty = [c["result"] for c in commands]
        observation.update(revision=pin, origin=origin, clean=not dirty)
        if Path(top).resolve() != path.resolve() or pin != profile["tool_revision"] or dirty:
            raise ValueError("Tool checkout root, pin or cleanliness differs from reviewed E1S tools")
        if origin.removesuffix(".git") != profile["tool_url"]:
            raise ValueError("Tool origin differs from reviewed source")
        hashes = {}
        for name, expected in profile["tool_file_sha256"].items():
            hashes[name] = hashlib.sha256((path / name).read_bytes()).hexdigest()
            if hashes[name] != expected:
                raise ValueError("Reviewed tool bytes differ: " + name)
        observation.update(pin_verified=True, file_sha256=hashes)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        observation["error"] = str(error)
    observation["commands"] = commands
    return observation


def describe(args, profile):
    missing = []
    tools = tool_observation(args.tools, profile)
    if not tools["pin_verified"]:
        missing.append("Verified embedded-era HakiOS tool checkout")
    sdk = sdk_observation(args.sdk, profile["theos_metadata_sha256"]) if args.sdk else None
    if sdk is None or "error" in sdk or not all(sdk.get("directories", {}).values()):
        missing.append("Explicit complete local base SDK with provenance; metadata alone is insufficient")
    host = {name: shutil.which(name) for name in profile["host_commands"]}
    missing += ["Host command: " + name for name, path in host.items() if path is None]
    compiler = {name: file_observation(Path(name), executable=True)
                for name in profile["wrapper_absolute_compilers"]}
    missing += ["Donor absolute compiler: " + name for name, item in compiler.items() if not item["present"]]
    cctools = {name: file_observation(args.theos / "toolchain/linux/iphone/bin" / name, executable=True)
               for name in profile["cctools"]}
    missing += ["Theos cctool: " + name for name, item in cctools.items() if not item["present"]]
    generated_host = {name: file_observation(args.tools / "xnu-deps/host/bin" / name, executable=True)
                      for name in profile["generated_host_tools"]}
    missing += ["Generated host tool: " + name for name, item in generated_host.items() if not item["present"]]
    overlay = {name: file_observation(args.overlay / name) for name in profile["overlay_files"]} if args.overlay else {}
    if not overlay:
        missing.append("Explicit generated kernel SDK overlay")
    missing += ["Kernel SDK overlay: " + name for name, item in overlay.items() if not item["present"]]
    headers = {name: file_observation(args.driverkit_headers / "DriverKit" / (name + ".h"))
               for name in profile["driverkit_interfaces"]} if args.driverkit_headers else {}
    if not headers:
        missing.append("Explicit matching Kernel.framework/Headers for the partial iig adapter")
    missing += ["Pre-generated DriverKit header: " + name for name, item in headers.items() if not item["present"]]
    prepared = {"source_preparation_verified": False, "kernel_compiled": False}
    if args.prepared_run:
        try:
            report = json.loads((args.prepared_run / "report.json").read_text())
            pins = {item["id"]: item["revision"] for item in report["provenance"]}
            if report.get("outcome") != "pass" or any(pins.get(k) != v for k, v in profile["kernel_source_pins"].items()):
                raise ValueError("Prepared source report outcome or exact pins differ")
            files = report["required_files"]
            for name, digest in files.items():
                if hashlib.sha256((args.prepared_run / "xnu" / name).read_bytes()).hexdigest() != digest:
                    raise ValueError("Prepared source bytes changed: " + name)
            required = ["config/MASTER.arm64.e1s", "pexpert/pexpert/arm64/E1S.h"]
            if not all(name in files for name in required):
                raise ValueError("Prepared source does not identify E1S machine/board files")
            prepared.update(source_preparation_verified=True, path=str(args.prepared_run),
                            required_file_sha256=files, report_sha256=hashlib.sha256((args.prepared_run / "report.json").read_bytes()).hexdigest())
        except (OSError, ValueError, KeyError, TypeError) as error:
            prepared["error"] = str(error)
    if not prepared["source_preparation_verified"]:
        missing.append("Verified E1S prepared source run; this still does not establish a kernel build")
    # Deliberate unresolved source gates: a directory/full metadata match cannot clear them.
    followups = profile["unresolved_source_gates"]
    return {"kind": "source-review", "origin": "local-host", "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outcome": "blocked" if missing or followups else "inputs-present-unvalidated",
            "target_runtime": profile["target_runtime"], "machine": profile["machine"],
            "kernel_compiled": False, "device_executed": False, "upstream_setup_executed": False,
            "sdk_version_is_not_an_abi_gate": True, "base_sdk": sdk, "tools": tools, "host_commands": host,
            "absolute_compilers": compiler, "cctools": cctools, "generated_host_tools": generated_host,
            "kernel_sdk_overlay": overlay, "driverkit_headers": headers, "prepared_source": prepared,
            "missing_inputs": missing, "unresolved_source_gates": followups,
            "limits": ["Presence and metadata are not provenance for an entire SDK, binary architecture or link-ABI verification",
                       "Read-only inventory does not authorize SDK downloads, dependency setup, a native boot or editing another owner's claim",
                       "Do not treat a linked kernel with failed export checks or unsupported DriverKit RPC stubs as complete native support"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sdk", type=Path, default=os.environ.get("S24_IOS_SDK"))
    p.add_argument("--tools", type=Path, default=ROOT / "references/hakios-e1s-tools")
    p.add_argument("--theos", type=Path, default=os.environ.get("THEOS", str(Path.home() / "theos")))
    p.add_argument("--overlay", type=Path)
    p.add_argument("--driverkit-headers", type=Path)
    p.add_argument("--prepared-run", type=Path)
    args = p.parse_args()
    profile = json.loads((ROOT / "fixtures/public/xnu-build-inputs/profile.json").read_text())
    report = describe(args, profile)
    print(json.dumps(report, indent=2))
    return 2 if report["outcome"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
