#!/usr/bin/env python3
"""Write a hash-bound GPU-012 compile/control plan. Never execute a compiler."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

MANIFEST_SHA = "afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd"
COMPILER_SHA = "7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82"
COMPOSITION_SHA = "3c04c89c13f1d2c00fc8d101de4481063acf247d4cc793b71f2ef79aa5a2bdd4"
GPU011_SHA = "93d6d8b223bd0a9c560d527a8b3eb28eaccce9bb258f59392208486591586977"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pin(path, expected=None):
    actual = digest(path)
    if expected is not None and actual != expected:
        raise ValueError("Hash mismatch: " + str(path))
    return {"path": str(path), "sha256": actual}


def prepare(main, owned, output, report, control):
    h = main / "worktrees/vm-008-20261105/artifacts/avf-kernel-headers"
    manifest = h / "handoff-1/next-full-object-manifest.json"
    report["inputs"].append(pin(manifest, MANIFEST_SHA))
    rows = json.loads(manifest.read_text())
    selected = [row for row in rows if row["component"] == "iokit"]
    if len(selected) != 104: raise ValueError("Expected actual104 iokit recipe context")
    cpp = next(row for row in selected if row["id"] == "iokit/IOUserClient.cpo")
    c = next(row for row in selected if row["id"] == "iokit/IOStringFuncs.o")
    if control == "wrong-target": cpp["next_owned_compile_argv_template"][cpp["next_owned_compile_argv_template"].index("-target") + 1] = "arm64-apple-ios17.0"
    if control == "source-hash": cpp["bound_source_sha256"] = "0" * 64
    for row in [cpp, c]:
        argv = row["next_owned_compile_argv_template"]
        if argv[argv.index("-target") + 1] != "arm64-apple-ios16.5" or "-DXNU_NO_TYPE_BUILTINS=0" not in argv:
            raise ValueError("Selected guest target/builtin contract changed")
        report["inputs"].append(pin(row["bound_source"], row["bound_source_sha256"]))
        report["inputs"].append(pin(row["configuration"], row["configuration_sha256"]))
    report["inputs"].append(pin(cpp["next_owned_compile_argv_template"][0], COMPILER_SHA))
    composition = main / "worktrees/vm-007-20261105/artifacts/avf-kernel-source/compose-final-ed9fdbf/composition-manifest.json"
    report["inputs"].append(pin(composition, COMPOSITION_SHA))
    composition_rows = {row["path"]: row for row in json.loads(composition.read_text())["profiles"]["qemu"]["files"]}
    report["genuine_declarations"] = []
    for relative in ["iokit/IOKit/IOUserClient.h", "iokit/IOKit/IOService.h", "iokit/IOKit/IOLocks.h", "iokit/IOKit/IOLib.h",
                     "iokit/IOKit/IOKitKeys.h", "libkern/libkern/c++/OSBoolean.h", "osfmk/kern/task.h", "osfmk/kern/task_ref.h",
                     "EXTERNAL_HEADERS/stdint.h", "EXTERNAL_HEADERS/stddef.h"]:
        row = composition_rows[relative]
        report["genuine_declarations"].append({**pin(h / "prepare-2/source/xnu" / relative, row["sha256"]),
                                                "canonical_git_blob_sha1": row["oid"]})
    evidence = main / "state/evidence/GPU-011.json"
    report["inputs"].append(pin(evidence, GPU011_SHA))
    gpu011 = json.loads(evidence.read_text())
    for relative in ["src/platform/gpu/abi/sgpu_abi.c", "src/platform/gpu/abi/sgpu_abi.h"]:
        report["inputs"].append(pin(owned / relative, gpu011["sha256"][relative]))
    report["owned_sources"] = [pin(path) for directory in [owned / "src/platform/gpu/native/userclient", owned / "fixtures/public/gpu-userclient"]
                               for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix in {".cpp", ".hpp", ".py"}]
    report["genuine_recipe_bindings"] = [cpp, c]
    report["owned_output_directories"] = [str(output / name) for name in ["objects", "dependencies", "work", "host"]]
    for directory in report["owned_output_directories"]:
        Path(directory).mkdir()
    target_commands = []
    for row, source, name in [(cpp, owned / "src/platform/gpu/native/userclient/SGPUUserClient.cpp", "adapter"),
                              (cpp, owned / "src/platform/gpu/native/userclient/Policy.cpp", "policy"),
                              (c, owned / "src/platform/gpu/abi/sgpu_abi.c", "dispatcher")]:
        argv = list(row["next_owned_compile_argv_template"])
        argv[argv.index(str(row["bound_source"]))] = str(source)
        argv[argv.index("-o") + 1] = str(output / "objects" / (name + ".o"))
        argv[argv.index("-MF") + 1] = str(output / "dependencies" / (name + ".d"))
        argv = ["-I" + row["cwd"] if arg == "-I." else arg for arg in argv]
        if name == "dispatcher" and not any(arg.startswith("-std=") for arg in argv): argv.insert(1, "-std=gnu11")
        target_commands.append({"name": name, "argv": argv, "cwd": str(output / "work"),
            "derived_from": row["id"], "output": str(output / "objects" / (name + ".o")),
            "timeout_seconds": 120, "max_owned_rss_bytes": 268435456,
            "execution_status": "unmeasured; root lease required"})
    report["target_compile_plan"] = target_commands
    cc, cxx = Path("/usr/bin/cc"), Path("/usr/bin/c++")
    report["host_tool_pins"] = [pin(cc.resolve()), pin(cxx.resolve())]
    flags = ["-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    host_object = output / "host/dispatcher.o"
    report["host_controls_plan"] = [
        {"argv": [str(cc), "-std=c11", *flags, "-c", str(owned / "src/platform/gpu/abi/sgpu_abi.c"), "-o", str(host_object)]},
        {"argv": [str(cxx), "-std=c++17", *flags, str(owned / "src/platform/gpu/native/userclient/Policy.cpp"),
            str(owned / "fixtures/public/gpu-userclient/policy_controls.cpp"), str(host_object), "-o", str(output / "host/policy-controls")]},
        {"argv": [str(output / "host/policy-controls")], "environment": {"ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"}}
    ]
    for command in report["host_controls_plan"]:
        command.update(timeout_seconds=120, max_owned_rss_bytes=268435456,
                       execution_status="unmeasured; root lease required")
    report["post_compile_inspection_plan"] = {"argv": [sys.executable, "-s", str(owned / "src/platform/gpu/native/userclient/inspect_objects.py"),
        "--directory", str(output / "objects"), "--output", str(output / "object-inspection.json")],
        "checks": ["ARM64 MH_OBJECT for all3 objects", "real IOUserClient override/provider emitted symbols",
                   "nonzero actual adapter allocator metadata", "C sgpu_dispatch symbol", "all actual unresolved imports retained; no stubs/link claim"]}
    report["unmeasured_gates"] = ["C++ typed kernel adapter compilation", "host policy controls and ASan/UBSan execution",
        "actual emitted symbols/imports/allocator metadata", "IOConnect runtime/task-credential behavior",
        "genuine Xclipse provider, GPU backing/VM/IRQ/cache/submit/retirement", "quiescence/drain and asynchronous session-hold release"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New owned plan directory; no execution")
    parser.add_argument("--control", choices=["source-hash", "wrong-target"])
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "source-review", "origin": "local-host", "task": "GPU-012", "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "argv": [sys.executable, *sys.argv], "inputs": [], "control": args.control, "execution_authorized": False,
        "compiler_executed": False, "host_controls_executed": False, "guest_executed": False,
        "resource_admission": {"root_lease_required": True, "shared_budget_review_required": True, "compiler_jobs_max": 2,
            "new_owned_rss_max_bytes": 2147483648, "compiler_rss_limit_bytes": 268435456, "minimum_stable_available_bytes": 4294967296}}
    started = time.monotonic()
    code = 0
    try:
        prepare(args.main.resolve(), Path(__file__).resolve().parents[5], args.output, report, args.control)
        if args.control: raise ValueError("Control unexpectedly passed")
        report["outcome"] = "pass"
    except (OSError, ValueError, KeyError, StopIteration) as error:
        report["outcome"] = "rejected" if args.control else "fail"
        report["error"] = str(error)
        code = 2 if args.control else 1
    report["exit_code"] = code
    report["elapsed_seconds"] = time.monotonic() - started
    report["proc_status"] = [line for line in Path("/proc/self/status").read_text().splitlines() if line.startswith(("VmHWM:", "VmRSS:"))]
    (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "exit_code": code, "error": report.get("error"), "plan": str(args.output / "plan.json")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
