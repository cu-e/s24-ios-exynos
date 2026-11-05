#!/usr/bin/env python3
"""Measure pinned open header/IIG candidates without substituting an Apple SDK."""
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/build"))
import sources
from xnu_macho_tools import macho

PINS = {"puredarwin-build-inputs": "6982ddbfca1047c86680ec7c66da152789746efd",
        "puredarwin-iig": "28010c688caab7eb5400b9c98faa5b1e538e0108",
        "apple-carbon-headers": "214a9ae7ab3c0c78ddb50328ca226e6313c4c782",
        "xnu-kernel-pthread": "a6c70ca0e544347a0377babf748f831577ec24f9",
        "hakios-e1s-tools": "d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--host-cxx", type=Path, required=True)
    parser.add_argument("--prepared-run", type=Path, required=True)
    parser.add_argument("--patch-header", action="store_true")
    parser.add_argument("--generate-mach", action="store_true", help="Use real qualified MIG for selected source client headers plus an explicit typed-address pthread source correction")
    parser.add_argument("--typed-interfaces", action="store_true", help="Apply explicit integer user-address zeros and opaque wait-queue callback casts, preserving actual prototypes and width checks")
    args = parser.parse_args()
    if args.generate_mach and not args.patch_header:
        raise ValueError("Generate/compile only after the source header target correction is selected")
    if args.typed_interfaces and not args.generate_mach:
        raise ValueError("Typed source correction requires the genuine generated-header profile")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Use a new canonical run name")
    for tool in [args.clang, args.host_cxx]:
        if not tool.is_absolute() or not tool.is_file() or not os.access(tool, os.X_OK):
            raise ValueError("Select explicit installed compiler executables")
    prepared = args.prepared_run.resolve()
    if not prepared.is_relative_to(ROOT / "artifacts/xnu-prepare"):
        raise ValueError("Use an actual isolated E1S prepared-source run")
    prior = json.loads((prepared / "report.json").read_text())
    pins = {p["id"]: p["revision"] for p in prior["provenance"]}
    if prior["outcome"] != "pass" or pins.get("apple-xnu") != "c54f35ca767986246321eb901baf8f5ff7923f6a" or pins.get("s24-port") != "c8860decc62c6d6180e609036d027a2997972420":
        raise ValueError("Prepared source is not the selected exact E1S kernel")
    kernel = prepared / "xnu"
    manifest_path = ROOT / "artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json"
    parent_report = json.loads((ROOT / "fixtures/public/xnu-dependencies/firehose-session1.json").read_text())
    if sha(manifest_path) != parent_report["kernel_tree_manifest_sha256"]:
        raise ValueError("Prepared tree witness changed")
    tree = json.loads(manifest_path.read_text())
    actual_names = {str(p.relative_to(kernel)) for p in kernel.rglob("*")
                    if p.is_file() and ".git" not in p.relative_to(kernel).parts}
    if actual_names != set(tree) or sha(prepared / "report.json") != parent_report["prepared_report_sha256"]:
        raise ValueError("Prepared source file inventory/report differs from actual prior witness")
    for name, digest in tree.items():
        if sha(kernel / name) != digest:
            raise ValueError("Actual E1S prepared bytes changed: " + name)
    entries = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    provenance = []
    for identifier, pin in PINS.items():
        entry = next(e for e in entries if e["id"] == identifier)
        if entry["revision"] != pin:
            raise ValueError("Use the exact reviewed candidate pin")
        provenance.append(sources.verify(ROOT, entry))
    out = ROOT / "artifacts/open-kernel-inputs" / args.run
    if out.resolve() != out:
        raise ValueError("Run cannot use symlink aliases")
    out.mkdir(parents=True, exist_ok=False)
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    pd = ROOT / "references/puredarwin-build-inputs"
    iig_src = ROOT / "references/puredarwin-iig"
    pd_name = "src/Libraries/AvailabilityVersions/include/TargetConditionals.h"
    header = out / "header-tree" / pd_name
    header.parent.mkdir(parents=True)
    shutil.copyfile(pd / pd_name, header)
    shutil.copyfile(pd / "APPLE_LICENSE.txt", out / "APPLE_LICENSE.txt")
    shutil.copyfile(iig_src / "LICENSE", out / "IIG_LICENSE")
    report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commands": [],
              "provenance": provenance, "builder_sha256": sha(Path(__file__)),
              "kernel_tree_manifest_sha256": sha(manifest_path), "prepared_report_sha256": sha(prepared / "report.json"),
              "header_patched": args.patch_header, "header_profiles": {}, "generated_interfaces": [],
              "pthread_translation_units": [], "pthread_archive": None, "apple_iig_abi_qualified": False,
              "full_exporthdrs_performed": False, "sdk_used": False, "sdk_standins_used": False, "device_executed": False,
              "limits": ["PureDarwin's source SDK targets a different kernel/OS; it is not the selected Apple SDK",
                         "IIG generator explicitly uses non-Apple FNV method IDs and kernel-side subset only",
                         "Header macro/component compilation does not establish complete SDK/private ABI or native support"]}
    deadline = time.monotonic() + 300

    def run(argv, label, stdin=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Open-input experiment command budget exhausted")
        result = subprocess.run(list(map(str, argv)), input=stdin, capture_output=True, text=True, timeout=min(60, remaining))
        so, se = out / (label + ".stdout.txt"), out / (label + ".stderr.txt")
        so.write_text(result.stdout)
        se.write_text(result.stderr)
        report["commands"].append({"argv": list(map(str, argv)), "exit_code": result.returncode,
                                   "stdout": str(so.relative_to(ROOT)), "stderr": str(se.relative_to(ROOT))})
        if stdin is not None:
            report["commands"][-1]["stdin_sha256"] = hashlib.sha256(stdin.encode()).hexdigest()
        print(json.dumps({"label": label, "exit_code": result.returncode}), flush=True)
        return result

    try:
        for label, tool in [("clang", args.clang), ("host-cxx", args.host_cxx)]:
            version = run([tool, "--version"], label)
            if version.returncode:
                raise RuntimeError("Installed compiler version check failed")
            report[label] = {"version": version.stdout.splitlines()[0], "sha256": sha(tool)}
        if args.patch_header:
            patch = ROOT / "patches/open-kernel-inputs/0001-open-header-native-ios-target.patch"
            report["header_patch_sha256"] = sha(patch)
            for flags, label in [(["init", "--quiet"], "header-init"),
                                 (["apply", "--check", str(patch)], "header-patch-check"),
                                 (["apply", str(patch)], "header-patch")]:
                if run(["git", "-c", "core.hooksPath=/dev/null", "-C", out / "header-tree", *flags], label).returncode:
                    raise RuntimeError("Private source header patch failed")
        report["tested_header_sha256"] = sha(header)
        probe = out / "header-probe.c"
        probe.write_text("/* Owned macro observation, no SDK or runtime code. */\n")
        cases = [("ios-device", "arm64-apple-ios16.5", [1, 1, 0, 0, 1]),
                 ("ios-arm-simulator", "arm64-apple-ios16.5-simulator", [1, 1, 0, 1, 1]),
                 ("ios-x86-simulator", "x86_64-apple-ios16.5-simulator", [1, 1, 0, 1, 0]),
                 ("macos-control", "arm64-apple-macos13.3", [0, 0, 1, 0, 1]),
                 ("macabi-control", "arm64-apple-ios16.5-macabi", [1, 1, 0, 0, 1]),
                 ("driverkit-control", "arm64-apple-driverkit19.0", [0, 0, 0, 0, 1])]
        macro_names = ["TARGET_OS_IOS", "TARGET_OS_IPHONE", "TARGET_OS_OSX", "TARGET_OS_SIMULATOR", "TARGET_CPU_ARM64"]
        carbon = ROOT / "references/apple-carbon-headers/TargetConditionals.h"
        for candidate, path in [("puredarwin", header), ("carbon", carbon), ("carbon-configured", carbon)]:
            report["header_profiles"][candidate] = {}
            for name, target, expected in cases:
                if candidate == "carbon-configured":
                    # Exactly the three substitutions in the reviewed Makefile,
                    # isolated from its install/symlink/removal recipe. This is
                    # the old source's real build step, not new API declarations.
                    text = carbon.read_text()
                    parameters = {"CONFIG_EMBEDDED": int(name == "ios-device"),
                                  "CONFIG_IPHONE": int(name.startswith("ios-") or name == "macabi-control"),
                                  "CONFIG_IPHONE_SIMULATOR": int("simulator" in name)}
                    for key, value in parameters.items():
                        text = text.replace("@" + key + "@", str(value))
                    if "@CONFIG_" in text:
                        raise ValueError("Old Carbon template configuration is incomplete")
                    path = out / ("carbon-configured-" + name + ".h")
                    path.write_text(text)
                result = run([args.clang, "-target", target, "-nostdinc", "-include", path, "-E", "-dM", probe], candidate + "-" + name)
                macros = dict(re.findall(r"^#define ([A-Za-z0-9_]+)[ \t]+([^\n]*)$", result.stdout, re.MULTILINE))
                actual = {key: macros.get(key) for key in macro_names}
                report["header_profiles"][candidate][name] = {"target": target, "exit_code": result.returncode,
                    "macros": actual, "expected": dict(zip(macro_names, expected)),
                    "matches_target_profile": result.returncode == 0 and [actual[k] for k in macro_names] == list(map(str, expected))}
                report["header_profiles"][candidate][name]["header_sha256"] = sha(path)
                if candidate == "carbon-configured":
                    report["header_profiles"][candidate][name]["source_template_parameters"] = parameters
        iig = out / "iig"
        built = run([args.host_cxx, "-std=c++17", "-O2", "-Wall", "-Wno-unused-function", "-I", iig_src / "include",
                     *[iig_src / "src" / (name + ".cpp") for name in ["main", "parse", "codegen"]], "-o", iig], "iig-build")
        if built.returncode:
            raise RuntimeError("Actual open IIG build failed")
        report["iig_sha256"] = sha(iig)
        defs = sorted((kernel / "iokit/DriverKit").glob("*.iig"))
        if len(defs) != 17:
            raise ValueError("Selected kernel's actual DriverKit interface inventory differs")
        generated = out / "generated"
        generated.mkdir()
        for source in defs:
            h, impl = generated / (source.stem + ".h"), generated / (source.stem + ".iig.cpp")
            result = run([iig, "--def", source, "--header", h, "--impl", impl, "--framework-name", "DriverKit"], "iig-" + source.stem)
            report["generated_interfaces"].append({"source": str(source.relative_to(kernel)), "source_sha256": sha(source),
                "exit_code": result.returncode, "header_sha256": sha(h) if h.is_file() else None,
                "implementation_sha256": sha(impl) if impl.is_file() else None})
        fixture = ROOT / "fixtures/public/open-kernel-inputs/ConditionalProbe.iig"
        variants = []
        for flag in [0, 1]:
            h, impl = generated / ("ConditionalProbe-" + str(flag) + ".h"), generated / ("ConditionalProbe-" + str(flag) + ".cpp")
            result = run([iig, "--def", fixture, "--header", h, "--impl", impl, "--", "-DENABLE_OPTION=" + str(flag)], "iig-conditional-" + str(flag))
            oracle = run([args.clang, "-target", "arm64-apple-ios16.5", "-nostdinc", "-E", "-P", "-x", "c++",
                          "-DENABLE_OPTION=" + str(flag), fixture], "real-preprocessor-" + str(flag))
            variants.append({"flag": flag, "generator_exit_code": result.returncode, "preprocessor_exit_code": oracle.returncode,
                "header_sha256": sha(h) if h.is_file() else None, "implementation_sha256": sha(impl) if impl.is_file() else None,
                "generated_method_ids": re.findall(r"^#define (ConditionalProbe_\w+_ID)\b", h.read_text(), re.MULTILINE) if h.is_file() else [],
                "oracle_enabled_present": " Enabled(" in oracle.stdout, "oracle_disabled_present": " Disabled(" in oracle.stdout})
        report["conditional_probe"] = variants
        good = all(v["matches_target_profile"] for v in report["header_profiles"]["puredarwin"].values())
        if args.patch_header and good:
            pthread = ROOT / "references/xnu-kernel-pthread"
            generated_mach = out / "mach-headers"
            if args.generate_mach:
                private = out / "pthread"
                shutil.copytree(pthread, private, ignore=shutil.ignore_patterns(".git"))
                pthread = private
                patch = ROOT / "patches/open-kernel-inputs/0002-pthread-explicit-vm-address-conversion.patch"
                report["pthread_patch_sha256"] = sha(patch)
                for flags, label in [(["init", "--quiet"], "pthread-init"),
                                     (["apply", "--check", str(patch)], "pthread-patch-check"),
                                     (["apply", str(patch)], "pthread-patch")]:
                    if run(["git", "-c", "core.hooksPath=/dev/null", "-C", pthread, *flags], label).returncode:
                        raise RuntimeError("Private typed-address source correction failed")
                report["patched_trace_header_sha256"] = sha(pthread / "kern/kern_trace.h")
                if args.typed_interfaces:
                    patch = ROOT / "patches/open-kernel-inputs/0003-pthread-typed-user-addresses-and-waitq-keys.patch"
                    report["typed_interfaces_patch_sha256"] = sha(patch)
                    for flags, label in [(["apply", "--check", str(patch)], "pthread-types-check"),
                                         (["apply", str(patch)], "pthread-types")]:
                        if run(["git", "-c", "core.hooksPath=/dev/null", "-C", pthread, *flags], label).returncode:
                            raise RuntimeError("Private explicit source interface correction failed")
                    report["typed_source_sha256"] = {name: sha(pthread / name) for name in ["kern/kern_trace.h", "kern/kern_support.c", "kern/kern_synch.c"]}
            dirs = [pthread, header.parent, *[kernel / n for n in ["osfmk", "bsd", "libkern", "pexpert", "iokit", "security", "osfmk/libsa", "EXTERNAL_HEADERS"]],
                    pthread / "include", pthread / "private"]
            compat = ROOT / "references/hakios-e1s-tools/xnu-deps/hostinc/xnu_clang_compat.h"
            common = [args.clang, "-target", "arm64-apple-ios16.5", "-mkernel", "-nostdinc", "-fno-builtin", "-Os",
                      "-DKERNEL=1", "-DKERNEL_PRIVATE=1", "-DPRIVATE=1", "-D__DARWIN_64_BIT_INO_T=1", "-DARM64_BOARD_CONFIG_E1S",
                      "-D__PTHREAD_EXPOSE_INTERNALS__=1", "-Dpthread_kern=pthread_kext_kern", "-Dcurrent_uthread=pthread_kext_current_uthread",
                      "-include", compat, *[arg for d in dirs for arg in ["-I", d]]]
            if args.generate_mach:
                manifest_file = ROOT / "fixtures/public/xnu-host-tools/qualified-inputs.json"
                manifest = json.loads(manifest_file.read_text())
                report["host_tools_manifest_sha256"] = sha(manifest_file)
                prefix = (ROOT / manifest["generator_prefix"]).resolve()
                if not prefix.is_relative_to(ROOT / "artifacts/xnu-host-tools"):
                    raise ValueError("MIG prefix escapes qualified project namespace")
                migcom = prefix / "bin/migcom"
                if sha(migcom) != manifest["generator_binary_sha256"]["migcom"]:
                    raise ValueError("Qualified real MIG compiler bytes changed")
                report["migcom_sha256"] = sha(migcom)
                makefile = kernel / "osfmk/mach/Makefile"
                block = re.search(r"MIG_UUHDRS\s*=\s*\\\n(.*?)\n\nMIGINCLUDES", makefile.read_text(), re.DOTALL)
                if not block:
                    raise ValueError("Actual selected Mach client-header recipe not recognized")
                names = re.findall(r"\b([A-Za-z0-9_]+)\.h\b", block.group(1))
                if not {"mach_port", "task"}.issubset(names) or len(names) != len(set(names)):
                    raise ValueError("Selected source client-header list differs")
                (generated_mach / "mach").mkdir(parents=True)
                report["mach_header_recipe_sha256"] = sha(makefile)
                report["mach_user_headers_generated"] = []
                for name in names:
                    source = kernel / "osfmk/mach" / (name + ".defs")
                    preprocessed = run([*common, "-D__MACH30__", "-E", "-x", "c", source], "mig-cpp-" + name)
                    item = {"name": name, "source_sha256": sha(source), "preprocessor_exit_code": preprocessed.returncode}
                    report["mach_user_headers_generated"].append(item)
                    if preprocessed.returncode:
                        continue
                    h = generated_mach / "mach" / (name + ".h")
                    result = run([migcom, "-novouchers", "-server", "/dev/null", "-user", "/dev/null", "-header", h], "mig-" + name, stdin=preprocessed.stdout)
                    item.update(generator_exit_code=result.returncode, header_sha256=sha(h) if h.is_file() else None)
                common += ["-I", generated_mach]
            objects = []
            for name in ["kern_init", "kern_support", "kern_synch"]:
                source, obj = pthread / "kern" / (name + ".c"), out / (name + ".o")
                result = run([*common, "-c", source, "-o", obj], "pthread-" + name)
                report["pthread_translation_units"].append({"name": name, "exit_code": result.returncode,
                    "missing_headers": sorted(set(re.findall(r"fatal error: ['<]([^'>]+)['>] file not found", result.stderr))),
                    "source_sha256": sha(source), "object_sha256": sha(obj) if obj.is_file() else None})
                if result.returncode == 0:
                    if macho(obj)["filetype"] != 1:
                        raise ValueError("Pthread output is not actual arm64 Mach-O")
                    objects.append(obj)
            if len(objects) == 3:
                manifest = json.loads((ROOT / "fixtures/public/xnu-host-tools/qualified-inputs.json").read_text())
                prefix = (ROOT / manifest["macho_prefix"]).resolve()
                if not prefix.is_relative_to(ROOT / "artifacts/xnu-macho-tools"):
                    raise ValueError("Mach-O prefix escapes the qualified project namespace")
                report["macho_manifest_sha256"] = sha(ROOT / "fixtures/public/xnu-host-tools/qualified-inputs.json")
                tools = {}
                for name in ["libtool", "nm"]:
                    relative = "bin/aarch64-apple-darwin-" + name
                    tool = prefix / relative
                    if sha(tool) != manifest["macho_files_sha256"][relative]:
                        raise ValueError("Qualified Mach-O tool bytes changed")
                    tools[name] = tool
                archive = out / "libpthread_kext.a"
                if run([tools["libtool"], "-static", "-o", archive, *objects], "pthread-archive").returncode:
                    raise RuntimeError("Actual pthread archive creation failed")
                symbols = run([tools["nm"], "-gUj", archive], "pthread-definitions")
                required = {"_pthread_start", "_pthread_stop", "_pthread_internal_functions", "_pthread_kext_kern"}
                if symbols.returncode or not required.issubset(symbols.stdout.splitlines()):
                    raise ValueError("Actual defined pthread exports differ")
                report["pthread_archive"] = {"path": str(archive.relative_to(ROOT)), "sha256": sha(archive), "required_defined_exports": sorted(required)}
        report.update(outcome="pass" if good and (not args.patch_header or report["pthread_archive"] is not None) else "fail",
                      summary="Actual open-source candidate measurements completed; IIG Apple ABI and complete SDK/export/native acceptance remain unqualified")
    except Exception as error:
        report.update(outcome="fail", error=str(error))
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "header_patched": args.patch_header,
                      "generated": len(report["generated_interfaces"]), "pthread_archive": report["pthread_archive"]}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
