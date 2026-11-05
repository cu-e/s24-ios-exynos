#!/usr/bin/env python3
"""Measure real E1S dependency components/profiles without fabricating SDK inputs."""
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
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sources
from xnu_macho_tools import macho

PINS = {"xnu-availability": "5d9baee345b3bc72b26c71adc65f94f2d5e9ced2",
        "xnu-kernel-firehose": "a641558f447659d90ad002ef0ee6f0212273fbfc",
        "xnu-kernel-pthread": "a6c70ca0e544347a0377babf748f831577ec24f9",
        "hakios-e1s-tools": "d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c"}
KERNEL_PINS = {"s24-port": "c8860decc62c6d6180e609036d027a2997972420",
               "apple-xnu": "c54f35ca767986246321eb901baf8f5ff7923f6a"}
ABI_FIELDS = ["max_cpus", "max_clusters", "pointer_bytes", "header_bytes", "buffer_bytes",
              "stream_bytes", "tracepoint_bytes", "tracepoint_data_offset", "header_unused_offset"]


def read_abi(path):
    parsed = macho(path)
    if parsed["filetype"] != 1:
        raise ValueError("Expected an actual arm64 relocatable ABI probe")
    data = path.read_bytes()
    commands_end = 32 + struct.unpack_from("<I", data, 20)[0]
    at = 32
    count = struct.unpack_from("<I", data, 16)[0]
    found = []
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, at)
        if command == 0x19:
            fileoff, filesize = struct.unpack_from("<QQ", data, at + 40)
            nsections = struct.unpack_from("<I", data, at + 64)[0]
            for i in range(nsections):
                section = at + 72 + i * 80
                name = data[section:section + 16].split(b"\0")[0]
                segment = data[section + 16:section + 32].split(b"\0")[0]
                if (name, segment) == (b"__s24abi", b"__DATA_CONST"):
                    length = struct.unpack_from("<Q", data, section + 40)[0]
                    offset = struct.unpack_from("<I", data, section + 48)[0]
                    relocations = struct.unpack_from("<I", data, section + 60)[0]
                    flags = struct.unpack_from("<I", data, section + 64)[0]
                    if (length != 8 * len(ABI_FIELDS) or offset > len(data) - length or relocations
                            or flags & 0xff or offset < commands_end or offset < fileoff
                            or offset + length > fileoff + filesize):
                        raise ValueError("Invalid ABI data extent or nonconstant relocated values")
                    found.append(dict(zip(ABI_FIELDS, struct.unpack_from("<" + "Q" * len(ABI_FIELDS), data, offset))))
        at += size
    if len(found) != 1:
        raise ValueError("Expected exactly one compiled ABI record")
    return found[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--clang", type=Path, required=True)
    p.add_argument("--prepared-run", type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit-includes", action="store_true", help="Raw-source syntax audit only, not exporthdrs")
    mode.add_argument("--build-firehose", action="store_true", help="Build the genuine firehose component and measured ABI only; pthread/full dependency acceptance remains separate")
    mode.add_argument("--verify-profile", action="store_true", help="Apply the guarded donor patch privately and qualify actual explicit compiler C/C++ behavior; never run setup")
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Invalid unique run name")
    if not args.clang.is_absolute() or not args.clang.is_file() or not os.access(args.clang, os.X_OK):
        raise ValueError("Use an explicit installed Clang executable")
    prepared = args.prepared_run.resolve()
    if not prepared.is_relative_to(ROOT / "artifacts/xnu-prepare"):
        raise ValueError("Use an actual project prepared-source run")
    prior = json.loads((prepared / "report.json").read_text())
    pins = {x["id"]: x["revision"] for x in prior["provenance"]}
    if prior.get("outcome") != "pass" or any(pins.get(k) != v for k, v in KERNEL_PINS.items()):
        raise ValueError("Prepared kernel source pins/outcome differ")
    kernel = prepared / "xnu"
    for name, digest in prior["required_files"].items():
        if hashlib.sha256((kernel / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Prepared required source bytes changed")
    entries = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    provenance = []
    for identifier, pin in PINS.items():
        entry = next(e for e in entries if e["id"] == identifier)
        if entry["revision"] != pin:
            raise ValueError("Audit recipe requires its exact reviewed source pins")
        provenance.append(sources.verify(ROOT, entry))
    out = ROOT / "artifacts/xnu-dependencies" / args.run
    if out.resolve() != out:
        raise ValueError("Run path cannot use symlinks")
    out.mkdir(parents=True, exist_ok=False)
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provenance": provenance,
              "commands": [], "profiles": {}, "translation_units": [], "sdk_used": False, "sdk_standins_used": False,
              "exporthdrs_performed": False, "archives_built": [], "full_dependency_archives_built": False, "device_executed": False,
              "prepared_report_sha256": hashlib.sha256((prepared / "report.json").read_bytes()).hexdigest(),
              "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "limits": ["Raw genuine source include directories are not the complete exported-header/SDK ABI",
                         "The donor's minimal pthread TargetConditionals stand-in is deliberately not included",
                         "Syntax/preprocessor observations alone do not establish compiled object/layout/archive or hardware support",
                         "Pinned donor type-builtin compatibility maps unavailable Apple builtins conservatively; this is not a security proof"]}
    tree = {str(f.relative_to(kernel)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in kernel.rglob("*") if f.is_file() and ".git" not in f.relative_to(kernel).parts}
    tree_file = out / "kernel-source-files.json"
    tree_file.write_text(json.dumps(tree, indent=2) + "\n")
    report["kernel_tree_manifest_sha256"] = hashlib.sha256(tree_file.read_bytes()).hexdigest()
    compat = ROOT / "references/hakios-e1s-tools/xnu-deps/hostinc/xnu_clang_compat.h"
    firehose = ROOT / "references/xnu-kernel-firehose"
    pthread = ROOT / "references/xnu-kernel-pthread"
    common_dirs = [kernel / name for name in ["osfmk", "bsd", "libkern", "pexpert", "iokit", "security"]]
    # osfmk/libsa/Makefile exports genuine string.h at the root of the osfmk
    # header set. Expose that source directory; never substitute libc headers.
    common_dirs += [kernel / "osfmk/libsa", kernel / "EXTERNAL_HEADERS"]
    common = [str(args.clang), "-target", "arm64-apple-ios16.5", "-mkernel", "-nostdinc", "-fno-builtin",
              "-DKERNEL=1", "-DKERNEL_PRIVATE=1", "-DPRIVATE=1", "-D__DARWIN_64_BIT_INO_T=1", "-include", str(compat)]
    deadline = time.monotonic() + 300

    def run(argv, label, env=None):
        index = len(report["commands"])
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Include-audit command budget exhausted")
        x = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=min(30, remaining), env=env)
        so, se = out / (label + ".stdout.txt"), out / (label + ".stderr.txt")
        so.write_text(x.stdout)
        se.write_text(x.stderr)
        item = {"argv": list(map(str, argv)), "exit_code": x.returncode,
                "stdout": str(so.relative_to(ROOT)), "stderr": str(se.relative_to(ROOT))}
        report["commands"].append(item)
        print(json.dumps({"command": index, "label": label, "exit_code": x.returncode}), flush=True)
        return x

    try:
        report["compiler"] = run([args.clang, "--version"], "compiler").stdout.splitlines()[0]
        report["compiler_sha256"] = hashlib.sha256(args.clang.read_bytes()).hexdigest()
        tools = {}
        if args.build_firehose or args.verify_profile:
            manifest_path = ROOT / "fixtures/public/xnu-host-tools/qualified-inputs.json"
            manifest = json.loads(manifest_path.read_text())
            report["tool_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            prefix = (ROOT / manifest["macho_prefix"]).resolve()
            if not prefix.is_relative_to(ROOT / "artifacts/xnu-macho-tools"):
                raise ValueError("Tool prefix escapes qualified project namespace")
            for name in (["ld"] if args.verify_profile else ["libtool", "nm"]):
                relative = "bin/aarch64-apple-darwin-" + name
                tool = prefix / relative
                if hashlib.sha256(tool.read_bytes()).hexdigest() != manifest["macho_files_sha256"][relative]:
                    raise ValueError("Qualified Mach-O tool bytes changed")
                tools[name] = tool
        if args.verify_profile:
            donor = out / "donor"
            shutil.copytree(ROOT / "references/hakios-e1s-tools", donor, ignore=shutil.ignore_patterns(".git"), symlinks=True)
            patch = ROOT / "patches/build-inputs/0001-explicit-e1s-dependency-profile.patch"
            report["profile_patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
            for argv, label in [(["git", "-c", "core.hooksPath=/dev/null", "-C", donor, "init", "--quiet"], "profile-init"),
                                (["git", "-c", "core.hooksPath=/dev/null", "-C", donor, "apply", "--check", patch], "profile-patch-check"),
                                (["git", "-c", "core.hooksPath=/dev/null", "-C", donor, "apply", patch], "profile-patch")]:
                if run(argv, label).returncode:
                    raise RuntimeError("Guarded donor profile patch failed")
            bindir = donor / "xnu-deps/host/bin"
            (bindir / "ld64").symlink_to(tools["ld"])
            wrapper = bindir / "xnu-clang"
            wrapper.chmod(0o755)
            cpp_wrapper = bindir / "xnu-clang++"
            cpp_wrapper.symlink_to("xnu-clang")
            cpp = args.clang.parent / "clang++"
            if not cpp.is_file() or not os.access(cpp, os.X_OK):
                raise ValueError("Explicit matching clang++ executable is missing")
            c_source = out / "profile.c"
            cpp_source = out / "profile.cpp"
            c_source.write_text("#include <pexpert/arm64/board_config.h>\nint s24_profile_c(void) { return MAX_CPUS; }\n")
            cpp_source.write_text('#include <pexpert/arm64/board_config.h>\nextern "C" int s24_profile_cpp(void) { return MAX_CPU_CLUSTERS; }\n')
            env = {**os.environ, "S24_XNU_CLANG": str(args.clang), "S24_XNU_CLANGXX": str(cpp), "XNU_SDK_VERSION": "16.5"}
            inc = [arg for directory in common_dirs for arg in ["-I", str(directory)]]
            report["compiler_profile_checks"] = []
            for name, executable, source in [("c", wrapper, c_source), ("cpp", cpp_wrapper, cpp_source)]:
                output = out / ("profile-" + name + ".o")
                # The upstream wrapper selects a target, not kernel semantics.
                # Use genuine source headers in freestanding kernel mode, as in
                # the component experiment; never fall through to host libc.
                flags = [executable, "-mkernel", "-nostdinc", "-fno-builtin",
                         "-DKERNEL=1", "-DKERNEL_PRIVATE=1", "-DPRIVATE=1",
                         "-DARM64_BOARD_CONFIG_E1S", *inc, "-c", source, "-o", output]
                missing = dict(env)
                missing.pop("S24_XNU_CLANGXX" if name == "cpp" else "S24_XNU_CLANG")
                negative = run(flags, "profile-" + name + "-missing", env=missing)
                if negative.returncode == 0 or output.exists():
                    raise RuntimeError("Wrapper silently used a fallback compiler")
                if run(flags, "profile-" + name, env=env).returncode or macho(output)["filetype"] != 1:
                    raise RuntimeError("Actual explicit compiler profile did not emit arm64 Mach-O")
                report["compiler_profile_checks"].append({"language": name, "missing_compiler_rejected": True,
                    "actual_arm64_object": True, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
            modified = ["xnu-deps/host/bin/xnu-clang", "xnu-deps/setup.sh", "xnu-deps/build/pthread/build.sh"]
            report["patched_source_sha256"] = {name: hashlib.sha256((donor / name).read_bytes()).hexdigest() for name in modified}
            report.update(outcome="pass", summary="Guarded donor patch applies; actual C/C++ wrappers reject missing compiler paths and emit arm64 Mach-O with explicit compilers. Setup/pthread workflow not executed.", upstream_setup_executed=False)
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({k: report[k] for k in ["outcome", "summary", "compiler_profile_checks"]}, indent=2))
            return 0
        probe = out / "board-probe.c"
        probe.write_text("#include <pexpert/arm64/board_config.h>\n")
        for machine in ["E1S", "BCM2837"]:
            board = ["-DARM64_BOARD_CONFIG_" + machine]
            inc = [arg for directory in common_dirs for arg in ["-I", str(directory)]]
            macros = run([*common, *board, *inc, "-E", "-dM", probe], machine + "-macros")
            parsed = {key: value or "" for key, value in re.findall(r"^#define ([A-Za-z0-9_]+)(?:[ \t]+(.*))?$", macros.stdout, re.MULTILINE)}
            report["profiles"][machine] = {"exit_code": macros.returncode,
                "macros": {name: parsed.get(name) for name in ["MAX_CPUS", "MAX_CPU_CLUSTERS", "MAX_CPU_CLUSTER_PHY_ID", "__SIZEOF_POINTER__", "__LP64__", "E1S", "BCM2837"]}}
            for name, source in [("firehose", firehose / "src/firehose/firehose_buffer.c"),
                                 *[(name, pthread / "kern" / (name + ".c")) for name in ["kern_init", "kern_support", "kern_synch"]]]:
                if args.build_firehose and name != "firehose":
                    continue
                flags = []
                dirs = common_dirs
                if name == "firehose":
                    flags = ["-DXNU_KERNEL_PRIVATE=0", "-DDISPATCH_USE_DTRACE=0", "-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1",
                             "-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0", "-DOS_FIREHOSE_SPI=1"]
                    dirs = [firehose, firehose / "src", firehose / "src/firehose", *common_dirs,
                            kernel / "libkern/firehose", kernel / "libkern/os"]
                else:
                    flags = ["-D__PTHREAD_EXPOSE_INTERNALS__=1", "-Dpthread_kern=pthread_kext_kern", "-Dcurrent_uthread=pthread_kext_current_uthread"]
                    dirs = [pthread, *common_dirs, pthread / "include", pthread / "private"]
                includes = [arg for directory in dirs for arg in ["-I", str(directory)]]
                output = out / (machine + "-firehose.o")
                phase = ["-Os", "-c", source, "-o", output] if args.build_firehose else ["-fsyntax-only", "-H", source]
                actual = run([*common, *board, *flags, *includes, *phase], machine + "-" + name)
                report["translation_units"].append({"machine": machine, "name": name, "exit_code": actual.returncode,
                    "missing_headers": sorted(set(re.findall(r"fatal error: ['<]([^'>]+)['>] file not found", actual.stderr))),
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
                if args.build_firehose and actual.returncode == 0:
                    if macho(output)["filetype"] != 1:
                        raise ValueError("Firehose output is not a real arm64 relocatable object")
                    archive = out / (machine + "-libfirehose_kernel.a")
                    archived = run([tools["libtool"], "-static", "-o", archive, output], machine + "-archive")
                    if archived.returncode:
                        raise RuntimeError("Actual firehose archive creation failed")
                    symbols = run([tools["nm"], "-gUj", archive], machine + "-symbols")
                    # C __firehose_buffer_tracepoint_reserve gains the Mach-O
                    # leading underscore. Require an exact defined name, not
                    # a substring that also accepts the _slow variant.
                    if symbols.returncode or "___firehose_buffer_tracepoint_reserve" not in symbols.stdout.splitlines():
                        raise RuntimeError("Actual firehose archive definition missing")
                    report["archives_built"].append({"machine": machine, "path": str(archive.relative_to(ROOT)),
                                                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                                    "object_sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
                    abi_source = out / (machine + "-abi.c")
                    abi_source.write_text('#include "' + str(source) + '"\n__attribute__((used,section("__DATA_CONST,__s24abi"))) const unsigned long long s24_firehose_abi[] = { MAX_CPUS, MAX_CPU_CLUSTERS, sizeof(void *), sizeof(struct firehose_buffer_header_s), sizeof(union firehose_buffer_u), sizeof(struct firehose_buffer_stream_s), sizeof(struct firehose_tracepoint_s), __builtin_offsetof(struct firehose_tracepoint_s,ft_data), __builtin_offsetof(struct firehose_buffer_header_s,fbh_unused) };\n')
                    abi_obj = out / (machine + "-abi.o")
                    built = run([*common, *board, *flags, *includes, "-Os", "-c", abi_source, "-o", abi_obj], machine + "-abi")
                    if built.returncode:
                        raise RuntimeError("Actual firehose ABI probe did not compile")
                    report["profiles"][machine]["compiled_abi"] = read_abi(abi_obj)
                    report["profiles"][machine]["abi_object_sha256"] = hashlib.sha256(abi_obj.read_bytes()).hexdigest()
        passed = all(t["exit_code"] == 0 for t in report["translation_units"]) and all(p["exit_code"] == 0 for p in report["profiles"].values())
        if args.build_firehose and passed:
            left, right = [report["profiles"][name]["compiled_abi"] for name in ["E1S", "BCM2837"]]
            report["measured_abi_differences"] = {key: {"E1S": left[key], "BCM2837": right[key]} for key in ABI_FIELDS if left[key] != right[key]}
        report.update(outcome="pass" if passed else "fail", summary="Actual firehose component/archive and measured ABI build completed; pthread/full dependency acceptance remains separate" if args.build_firehose else "Actual source-only dependency syntax/profile audit completed; no exporthdrs or archives produced")
    except Exception as error:
        report.update(outcome="fail", error=str(error), summary="Dependency source/include audit retained its actual failure")
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["outcome", "profiles", "translation_units"]}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sources.SourceError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
