#!/usr/bin/env python3
"""Build reviewed freestanding E1S loaders in an isolated host directory. Never flashes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import sources

ZIG_VERSION = "0.16.0"


def run(argv, cwd, log):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True, text=True, timeout=120,
                            env={**os.environ, "SOURCE_DATE_EPOCH": "0", "LC_ALL": "C", "TZ": "UTC"})
    log.append({"argv": [str(x) for x in argv], "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr})
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {argv}\n{result.stderr[-4000:]}")
    return result.stdout.strip()


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root, identifier):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", identifier) or identifier in {".", ".."}:
        raise RuntimeError("Use a simple unique run identifier")
    entries = json.loads((root / "research/sources.json").read_text())["sources"]
    source = next(s for s in entries if s["id"] == "s24-port")
    provenance = sources.verify(root, source)
    directory = root / "artifacts/e1s-build" / identifier
    if directory.resolve() != root / "artifacts/e1s-build" / identifier:
        raise RuntimeError("Build directory must not use symlink aliases")
    directory.mkdir(parents=True, exist_ok=False)
    commands = []
    report = {"schema_version": 1, "kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": provenance,
              "commands": commands, "hardware_execution": False, "apple_userland": False,
              "source_patch": {"path": "patches/e1s-boot/0001-loader-memory-validation.patch",
                               "source_task": "STR-002", "source_commit": "6a1c05d4119acd5146d56d7fc9070742584140cd",
                               "expected_sha256": "23b31c44ed9dba9c2da2e5b56ccbe97cd67fa41efff3ec032130eabca6718ae1", "applied": False},
              "display_source_patch": {"path": "patches/e1s-display/0001-loader-framebuffer-contract.patch",
                                       "source_task": "STR-005", "source_commit": "12047e095c97170036b7b8229f52ca435c880538",
                                       "expected_sha256": "0689fc94383efec7c83df44629df3b0e3e456cce48b08008e2226bc5189570d9", "applied": False},
              "kernel_build": "not-run; SDK/dependencies are a separate prerequisite"}
    try:
        version = run(["zig", "version"], root, commands)
        if version != ZIG_VERSION:
            raise RuntimeError(f"Expected Zig {ZIG_VERSION}, got {version}")
        report["toolchain"] = {"zig": version, "path": shutil.which("zig")}
        work = directory / "source"
        shutil.copytree(root / "references/s24-port", work, ignore=shutil.ignore_patterns(".git", "out", "out-qemu", "__pycache__"))
        patch = report["source_patch"]
        patch_bytes = (root / patch["path"]).read_bytes()
        patch["sha256"] = hashlib.sha256(patch_bytes).hexdigest()
        if patch["sha256"] != patch["expected_sha256"]:
            raise RuntimeError("Accepted STR-002 memory validation patch identity changed")
        snapshot = directory / "loader-memory-validation.patch"
        snapshot.write_bytes(patch_bytes)
        patch.update(snapshot=str(snapshot.relative_to(root)), applied_to=str(work.relative_to(root)))
        run(["git", "apply", "--check", snapshot], work, commands)
        run(["git", "apply", snapshot], work, commands)
        patch["applied"] = True
        display_patch = report["display_source_patch"]
        display_bytes = (root / display_patch["path"]).read_bytes()
        display_patch["sha256"] = hashlib.sha256(display_bytes).hexdigest()
        if display_patch["sha256"] != display_patch["expected_sha256"]:
            raise RuntimeError("Accepted STR-005 framebuffer contract patch identity changed")
        display_snapshot = directory / "loader-framebuffer-contract.patch"
        display_snapshot.write_bytes(display_bytes)
        display_patch.update(snapshot=str(display_snapshot.relative_to(root)), applied_to=str(work.relative_to(root)))
        run(["git", "apply", "--check", display_snapshot], work, commands)
        run(["git", "apply", display_snapshot], work, commands)
        display_patch["applied"] = True
        products = []
        for target, files, linker in [("probe", ["shim/e1s/start.S", "shim/e1s/probe.c"], "shim/e1s/loader.ld"),
                                      ("loader", ["shim/e1s-xnu/" + f for f in ["start.S", "loader.c", "ui.c", "adt_patch.c", "gic.c", "fdt.c"]], "shim/e1s-xnu/loader.ld")]:
            out = directory / target
            out.mkdir()
            objects = []
            for file in files:
                obj = out / (Path(file).name + ".o")
                flags = ["-O2", "-g0", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-pic", "-fno-zero-initialized-in-bss", "-mstrict-align", "-mgeneral-regs-only", "-Wall", "-Wextra"]
                run(["zig", "cc", "-target", "aarch64-freestanding", *flags, "-c", work / file, "-o", obj], root, commands)
                objects.append(obj)
            elf, image = out / (target + ".elf"), out / "Image"
            run(["zig", "cc", "-target", "aarch64-freestanding", "-static", "-nostdlib", "-Wl,--build-id=none", "-Wl,-T," + str(work / linker), *objects, "-o", elf], root, commands)
            run(["zig", "objcopy", "-O", "binary", elf, image], root, commands)
            run([sys.executable, work / "tools/e1s/fix_image.py", image], root, commands)
            # These are build-format fields, not a claim of firmware compatibility or bootability.
            run([sys.executable, work / "tools/e1s/mkboot.py", "--kernel", image, "--output", out / "boot.img", "--os-version", "15.0.0", "--os-patch-level", "2025-08", "--tar"], root, commands)
            for path in [elf, image, out / "boot.img", out / "boot.img.tar"]:
                products.append({"path": str(path.relative_to(root)), "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        report.update(outcome="pass", summary="Freestanding probe and XNU handoff loader built; no kernel/userland/device execution", products=products)
    except Exception as exc:
        report.update(outcome="fail", error=str(exc))
    finally:
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "report": str((directory / "report.json").relative_to(root)), "error": report.get("error")}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=TOOLS.parent)
    parser.add_argument("--run", required=True, help="New artifact directory; existing runs are never overwritten")
    args = parser.parse_args()
    return build(args.root.resolve(), args.run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, sources.SourceError) as exc:
        print(f"e1s-build: {exc}", file=sys.stderr)
        sys.exit(2)
