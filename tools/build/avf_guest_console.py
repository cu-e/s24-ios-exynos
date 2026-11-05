#!/usr/bin/env python3
"""Read-only source preflight and conservative AVF console diagnostics.

This module never launches a compiler or guest. Console text is untrusted input:
even all expected strings cannot establish that a genuine kernel executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "fixtures/public/avf-guest-console/inputs.json"
DEFAULT_ARGS = "debug=0x8 serial=3 -enable_kprintf_spam console_quiet=0 disable-uart-irq=1"
MAX_LOG = 64 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def boot_args(value):
    tokens = value.split()
    values = {}
    for token in tokens:
        key, _, val = token.partition("=")
        if key in values:
            raise ValueError("duplicate boot argument: " + key)
        values[key] = val
    for key, expected in (("debug", 8), ("serial", 3), ("console_quiet", 0),
                          ("disable-uart-irq", 1)):
        try:
            actual = int(values[key], 0)
        except (KeyError, ValueError) as exc:
            raise ValueError("missing or invalid diagnostic boot argument: " + key) from exc
        if actual != expected:
            raise ValueError("unexpected diagnostic boot argument: " + key)
    if values.get("-enable_kprintf_spam") != "":
        raise ValueError("DEVELOPMENT kprintf requires -enable_kprintf_spam")
    return tokens


def preflight(main, arguments=DEFAULT_ARGS, pins_path=PINS):
    pins = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    parents = []
    for row in pins["parent_manifests"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("non-relative parent binding")
        actual = sha256(Path(main) / relative)
        if actual != row["sha256"]:
            raise ValueError("parent manifest hash mismatch")
        parents.append({"path": row["path"], "sha256": actual})
    verified = []
    for row in pins["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("non-relative source binding")
        path = Path(main) / relative
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("source input exceeds bounded text limit")
        actual = sha256(path)
        if actual != row["sha256"]:
            raise ValueError("source hash mismatch: " + row["id"])
        lines = path.read_text(encoding="utf-8").splitlines()
        for fact in row["facts"]:
            if lines[fact["line"] - 1].strip() != fact["text"]:
                raise ValueError("source fact mismatch: " + row["id"])
        verified.append({"id": row["id"], "path": str(path), "sha256": actual,
                         "facts": row["facts"]})
    graph_path = Path(main) / pins["parent_manifests"][0]["path"]
    with graph_path.open(encoding="utf-8") as stream:
        graph = {row["id"]: row for row in json.load(stream)}
    bound_objects = []
    for object_id, source_id in pins["console_objects"].items():
        row = graph[object_id]
        source = next(item for item in verified if item["id"] == source_id)
        if (Path(row["bound_source"]).resolve() != Path(source["path"]).resolve()
                or row["bound_source_sha256"] != source["sha256"]):
            raise ValueError("console object/source graph mismatch: " + object_id)
        bound_objects.append(object_id)
    return {"schema": 1, "kind": "source-only-console-preflight", "outcome": "pass",
            "files": verified, "parent_manifests": parents, "pins_sha256": sha256(pins_path),
            "console_objects": bound_objects,
            "boot_args": boot_args(arguments), "kernel_execution": "unmeasured",
            "compile_authorized": False, "qemu_authorized": False,
            "native_phone": False}


def diagnose(log):
    log = Path(log)
    if log.stat().st_size > MAX_LOG:
        raise ValueError("console exceeds 64 MiB diagnostic limit")
    patterns = {
        "shim_start": re.compile(r"^avfboot: HakiOS XNU boot for crosvm/AVF and QEMU virt$"),
        "shim_jump": re.compile(r"^avfboot: jumping to XNU at 0x[0-9a-fA-F]+$"),
        "kernel_kprintf": re.compile(r"^kprintf initialized$"),
        "kernel_serial": re.compile(r"^Serial mode specified: 00000003$"),
        "kernel_version": re.compile(r"^Darwin Kernel Version 22\.5\.0: .+"),
    }
    observed = {}
    rejected = []
    failures = []
    consumed = 0
    log_digest = hashlib.sha256()
    synthetic_count = failure_count = 0
    with log.open("rb") as stream:
        line_number = 0
        while raw := stream.readline(65537):
            line_number += 1
            consumed += len(raw)
            log_digest.update(raw)
            if consumed > MAX_LOG:
                raise ValueError("console grew beyond diagnostic limit")
            if len(raw) > 65536:
                raise ValueError("console line exceeds 64 KiB diagnostic limit")
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            lower = line.lower()
            if any(marker in lower for marker in ("synthetic", "vm005_cookie=", "owned-synthetic")):
                synthetic_count += 1
                if len(rejected) < 32:
                    rejected.append(line_number)
            if line.startswith(("avfboot: FATAL:", "avfboot: exception slot=", "panic(cpu")):
                failure_count += 1
                if len(failures) < 32:
                    failures.append(line_number)
            for name, pattern in patterns.items():
                if pattern.fullmatch(line):
                    observed.setdefault(name, line_number)
    order = [observed[name] for name in patterns if name in observed]
    ordered = order == sorted(order) and len(order) == len(set(order))
    if rejected:
        classification = "rejected-synthetic-input"
    elif failures:
        classification = "failure-observed"
    elif not ordered:
        classification = "inconsistent-marker-order"
    elif "kernel_version" in observed:
        classification = "kernel-like-text-observed-unverified"
    elif "kernel_kprintf" in observed:
        classification = "early-kernel-like-text-observed-unverified"
    elif "shim_jump" in observed:
        classification = "shim-handoff-text-only"
    elif "shim_start" in observed:
        classification = "shim-text-only"
    else:
        classification = "no-recognized-console-markers"
    return {"schema": 1, "kind": "untrusted-console-diagnostic",
            "log_sha256": log_digest.hexdigest(), "log_hashed_bytes": consumed,
            "classification": classification,
            "observed_lines": observed, "synthetic_lines": rejected,
            "failure_lines": failures, "marker_order_consistent": ordered,
            "synthetic_count": synthetic_count, "failure_count": failure_count,
            "genuine_kernel_success": False, "pid1_success": False,
            "natural_stop_verified": False, "native_phone": False,
            "required_independent_evidence": ["accepted source/object/link/image lineage",
                "accepted runner invocation bound to actual payload and console",
                "independent review of genuine kernel execution"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("preflight")
    source.add_argument("--main", type=Path, required=True)
    source.add_argument("--boot-args", default=DEFAULT_ARGS)
    diagnostic = commands.add_parser("diagnose")
    diagnostic.add_argument("--log", type=Path, required=True)
    for command in (source, diagnostic):
        command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (preflight(args.main, args.boot_args) if args.command == "preflight"
                  else diagnose(args.log))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        if result.get("classification") in ("rejected-synthetic-input", "failure-observed",
                                            "inconsistent-marker-order"):
            return 2
        return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print("console diagnostic rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
