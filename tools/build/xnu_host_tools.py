#!/usr/bin/env python3
"""Build pinned MIG/unifdef/tcsh in artifacts; no SDK, installer or device selection."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sources

PINS = {"xnu-mig": "f337e600741638896fb6056ce87c6479f74b89a3",
        "xnu-unifdef": "08d12cd3059fe072929ea001ad9833f5487fd355",
        "xnu-tcsh": "b7db07931546178c4cb2542b5fc850c483628ed5"}
MIG_C = ["error", "global", "header", "mig", "routine", "server", "statement", "string", "type", "user", "utils", "parser", "lexxer"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--cc", type=Path, required=True)
    p.add_argument("--preprocessor", type=Path, required=True)
    p.add_argument("--termcap-library", type=Path, help="Explicit installed versioned tinfo/termcap library when development symlinks are absent")
    p.add_argument("--jobs", type=int, default=2)
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Invalid unique run name")
    if not 1 <= args.jobs <= 4:
        raise ValueError("Use1..4 build jobs")
    for tool in [args.cc, args.preprocessor]:
        if not tool.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./+-]+", str(tool)) or not tool.is_file() or not os.access(tool, os.X_OK):
            raise ValueError("Supply explicit installed compiler/preprocessor executable paths")
    if args.termcap_library and (not args.termcap_library.is_absolute() or
            not re.fullmatch(r"/[A-Za-z0-9_./+-]+", str(args.termcap_library)) or not args.termcap_library.is_file()):
        raise ValueError("Supply an explicit installed termcap library file")
    entries = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    provenance = []
    for identifier, pin in PINS.items():
        entry = next(e for e in entries if e["id"] == identifier)
        if entry["revision"] != pin:
            raise ValueError("Build recipe requires its reviewed source pin: " + identifier)
        provenance.append(sources.verify(ROOT, entry))
    out = ROOT / "artifacts/xnu-host-tools" / args.run
    if out.resolve() != out:
        raise ValueError("Run directory cannot use symlinks")
    out.mkdir(parents=True, exist_ok=False)
    prefix = out / "prefix"
    bindir = prefix / "bin"
    bindir.mkdir(parents=True)
    logs = out / "logs"
    logs.mkdir()
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provenance": provenance,
              "commands": [], "sdk_used": False, "device_executed": False, "global_install": False,
              "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "prefix": str(prefix.relative_to(ROOT)), "coverage": {},
              "remaining": ["Full cctools/TAPI and XNU linker-option/symbolset compatibility",
                            "Generated MIG code compile/link/IPC against actual selected SDK/kernel headers",
                            "Actual E1S dependency archives and full kernel build"]}
    env = {**os.environ, "CC": str(args.cc), "CFLAGS": "-O2 -std=gnu11", "CONFIG_SITE": "/dev/null", "MAKEFLAGS": "",
           "MIGCC": str(args.preprocessor), "MIGCOM": str(bindir / "migcom"), "SDKROOT": "", "TMPDIR": str(out / "tmp")}
    Path(env["TMPDIR"]).mkdir()
    if args.termcap_library:
        env["LIBS"] = str(args.termcap_library)
        report["termcap_library"] = {"path": str(args.termcap_library.resolve()),
                                      "sha256": hashlib.sha256(args.termcap_library.read_bytes()).hexdigest()}
    deadline = time.monotonic() + 600

    def run(argv, cwd=out, expected=(0,), timeout=300):
        index = len(report["commands"])
        record = {"argv": list(map(str, argv)), "cwd": str(cwd), "expected_exit_codes": list(expected)}
        report["commands"].append(record)
        print(json.dumps({"command": index, "program": record["argv"][0]}), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Host build command budget exhausted")
        x = subprocess.run(record["argv"], cwd=cwd, env=env, capture_output=True, text=True, timeout=min(timeout, remaining))
        stdout = logs / f"{index:02d}.stdout.txt"
        stderr = logs / f"{index:02d}.stderr.txt"
        stdout.write_text(x.stdout)
        stderr.write_text(x.stderr)
        record.update(exit_code=x.returncode, stdout=str(stdout.relative_to(ROOT)), stderr=str(stderr.relative_to(ROOT)))
        if x.returncode not in expected:
            raise RuntimeError(f"Command{index} exited{x.returncode}; see {stderr.relative_to(ROOT)}")
        return x

    try:
        report["compiler"] = run([args.cc, "--version"]).stdout.splitlines()[0]
        report["preprocessor"] = run([args.preprocessor, "--version"]).stdout.splitlines()[0]
        work = {}
        for identifier in PINS:
            source = ROOT / "references" / identifier
            for f in source.rglob("*"):
                if ".git" in f.relative_to(source).parts:
                    continue
                if f.is_symlink() and not f.resolve().is_relative_to(source.resolve()):
                    raise ValueError("Source symlink escapes its pinned checkout")
            target = out / identifier
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"), symlinks=True)
            work[identifier] = target
            hashes = {str(f.relative_to(target)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in target.rglob("*") if f.is_file()}
            (out / (identifier + "-source-files.json")).write_text(json.dumps(hashes, indent=2) + "\n")
        # This direct recipe follows the exact Makefile.am/configure.ac source
        # list and non-Apple includes; no missing Autotools install is hidden.
        mig = work["xnu-mig"]
        patch = ROOT / "patches/build-tools/0001-mig-propagate-preprocessor-failure.patch"
        report["mig_patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
        run(["git", "-c", "core.hooksPath=/dev/null", "init", "--quiet"], cwd=mig)
        run(["git", "-c", "core.hooksPath=/dev/null", "apply", "--check", patch], cwd=mig)
        run(["git", "-c", "core.hooksPath=/dev/null", "apply", patch], cwd=mig)
        src = mig / "migcom.tproj"
        run(["bison", "-y", "-d", "--defines=parser.h", "-o", "parser.c", "parser.y"], cwd=src)
        run(["flex", "-o", "lexxer.c", "lexxer.l"], cwd=src)
        run([args.cc, "-std=gnu11", "-O2", '-DMIG_VERSION="bootstrap_cmds-138"', "-I../compat/non_apple", "-I.",
             *[name + ".c" for name in MIG_C], "-o", bindir / "migcom"], cwd=src)
        shutil.copyfile(src / "mig.sh", bindir / "mig")
        (bindir / "mig").chmod(0o755)
        fixture = out / "fixtures"
        fixture.mkdir()
        defs = "subsystem s24_host 2400;\ntype s24_word_t = MACH_MSG_TYPE_INTEGER_32;\ntype s24_port_t = MACH_MSG_TYPE_COPY_SEND;\nroutine s24_echo(server: s24_port_t; input: s24_word_t; out output: s24_word_t);\n"
        (fixture / "s24.defs").write_text(defs)
        run([bindir / "mig", "-target", "arm64-apple-ios16.5", "-header", "s24.h", "-user", "s24User.c",
             "-server", "s24Server.c", "s24.defs"], cwd=fixture)
        generated = [fixture / name for name in ["s24.h", "s24User.c", "s24Server.c"]]
        if not all(f.is_file() and "s24_echo" in f.read_text() for f in generated):
            raise RuntimeError("Actual MIG interface generation not established")
        (fixture / "invalid.defs").write_text(defs + "#error s24_expected_preprocessor_failure\n")
        run([bindir / "mig", "-target", "arm64-apple-ios16.5", "-header", "invalid.h", "-user", "invalidUser.c",
             "-server", "invalidServer.c", "invalid.defs"], cwd=fixture, expected=(1,))
        report["coverage"]["mig"] = "actual client/server/header generation and preprocessor failure propagation; no generated ABI/IPC execution"
        unifdef = work["xnu-unifdef"]
        (unifdef / "version.h").write_text('"@(#) $Version: unifdef-2.12 pinned08d12cd $\\n"\n')
        run([args.cc, "-std=gnu11", "-O2", "-o", bindir / "unifdef", "unifdef.c"], cwd=unifdef)
        condition = fixture / "conditional.h"
        condition.write_text("#if ENABLE\nint s24_selected = 2400;\n#else\nint s24_selected = 0;\n#endif\n")
        for value in [1, 0]:
            actual = run([bindir / "unifdef", "-DENABLE=" + str(value), condition], expected=(1,))
            expected = "int s24_selected = " + ("2400" if value else "0") + ";\n"
            if actual.stdout != expected:
                raise RuntimeError("Actual unifdef branch output differs")
        report["coverage"]["unifdef"] = "actual enabled/disabled conditional output and documented modification exit1"
        tcsh = work["xnu-tcsh"]
        run(["sh", "configure", "--prefix=" + str(prefix), "--disable-nls", "--disable-nls-catalogs"], cwd=tcsh)
        run(["make", "-j" + str(args.jobs), "tcsh"], cwd=tcsh)
        shutil.copyfile(tcsh / "tcsh", bindir / "tcsh")
        (bindir / "tcsh").chmod(0o755)
        (bindir / "csh").symlink_to("tcsh")
        (fixture / "shell.csh").write_text("set total = 0\nforeach value (1 2 3 4)\n@ total += $value\nend\nif ($total != 10) exit 7\necho s24-shell-$total\n")
        actual = run([bindir / "csh", "-f", fixture / "shell.csh"])
        if actual.stdout.strip() != "s24-shell-10":
            raise RuntimeError("Actual csh control-flow result differs")
        report["coverage"]["tcsh"] = "actual csh foreach/arithmetic/conditional fixture with startup files disabled"
        for identifier, names in {"xnu-mig": ["APPLE_LICENSE", "migcom.tproj/mig.sh"],
                                  "xnu-unifdef": ["COPYING"], "xnu-tcsh": ["Copyright", "BUILDING"]}.items():
            license_dir = prefix / "share/licenses" / identifier
            license_dir.mkdir(parents=True)
            for name in names:
                shutil.copyfile(work[identifier] / name, license_dir / Path(name).name)
        report["binary_sha256"] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in bindir.iterdir() if f.is_file()}
        report.update(outcome="pass", summary="Pinned MIG/unifdef/tcsh built and genuine host fixtures pass; full Mach-O/XNU compatibility remains separate")
    except Exception as error:
        report.update(outcome="fail", error=str(error), summary="Host-generator build retained its actual partial/failure result")
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["outcome", "summary", "coverage"]}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sources.SourceError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
