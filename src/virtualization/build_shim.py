#!/usr/bin/env python3
"""Build the selected AVF shim from pinned source with no Apple identity data."""
import argparse
import datetime
import json
from pathlib import Path
import resource
import subprocess

from host import DONOR, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"donor_commit": DONOR, "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "outcome": "fail", "commands": [], "sources": [], "tools": {},
              "guest_started": False, "pid1_observed": False}

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

    def run(argv, name):
        proc = subprocess.run([str(arg) for arg in argv], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30, preexec_fn=limits)
        (args.out / (name + ".stdout")).write_bytes(proc.stdout)
        (args.out / (name + ".stderr")).write_bytes(proc.stderr)
        report["commands"].append({"argv": [str(arg) for arg in argv], "exit_code": proc.returncode,
                                   "stdout": name + ".stdout", "stderr": name + ".stderr"})
        if proc.returncode:
            raise RuntimeError(f"{name} exited {proc.returncode}")
        return proc.stdout

    try:
        compiler = args.clang.resolve(strict=True)
        tools = {"clang": compiler}
        for name in ("ld.lld", "llvm-objcopy", "llvm-readelf"):
            tools[name] = compiler.parent / name
        for name, path in tools.items():
            report["tools"][name] = {"path": str(path), "sha256": sha256(path)}
            run([path, "--version"], name + "-version")
        files = ["avf/shim/" + file for file in
                 ("start.S", "avfboot.c", "fdtx.c", "fdtx.h", "uart.c", "uart.h",
                  "pci.c", "pci.h", "avfboot.ld", "build.sh")]
        files += ["xnuloader/mkidentity.py", "LICENSE", "LICENSE.APSL"]
        for index, file in enumerate(files):
            path = args.out / "source" / file
            path.parent.mkdir(parents=True, exist_ok=True)
            data = run(["git", "-C", args.donor, "show", DONOR + ":" + file], f"extract-{index}")
            path.write_bytes(data)
            report["sources"].append({"path": file, "sha256": sha256(path)})
        identity = args.out / "source/xnuloader/identity.h"
        identity.write_bytes(run(["python3", identity.with_name("mkidentity.py"), "--placeholder"], "placeholder"))
        report["placeholder_sha256"] = sha256(identity)
        flags = ["--target=aarch64-none-elf", "-O2", "-ffreestanding", "-fno-builtin", "-nostdlib",
                 "-fPIE", "-fvisibility=hidden", "-mgeneral-regs-only", "-mstrict-align",
                 "-fno-stack-protector", "-Wall", "-Wextra", "-I" + str(identity.parent)]
        objects = []
        for file in ("start.S", "avfboot.c", "fdtx.c", "uart.c", "pci.c"):
            source = args.out / "source/avf/shim" / file
            obj = args.out / (source.stem + ".o")
            run([compiler, *flags, "-c", source, "-o", obj], source.stem + "-compile")
            objects.append(obj)
        elf = args.out / "avfboot.elf"
        run([tools["ld.lld"], "-pie", "--no-dynamic-linker", "-z", "norelro", "--build-id=none",
             "-T", args.out / "source/avf/shim/avfboot.ld", *objects, "-o", elf], "shim-link")
        relocs = run([tools["llvm-readelf"], "-r", elf], "shim-relocations").decode()
        if any("R_AARCH64_" in line and "R_AARCH64_RELATIVE" not in line for line in relocs.splitlines()):
            raise ValueError("shim has unsupported dynamic relocations")
        image = args.out / "Image"
        run([tools["llvm-objcopy"], "-O", "binary", elf, image], "shim-image")
        with image.open("rb") as stream:
            header = stream.read(64)
        if header[56:60] != b"ARM\x64":
            raise ValueError("missing arm64 Image header")
        report["artifacts"] = [{"path": str(p.resolve()), "sha256": sha256(p), "size": p.stat().st_size}
                               for p in (elf, image)]
        report["outcome"] = "pass"
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in
                      ("outcome", "donor_commit", "guest_started", "pid1_observed")} |
                     {"report": str(args.out / "report.json"), "error": report.get("error")}, indent=2))
    return 0 if report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
